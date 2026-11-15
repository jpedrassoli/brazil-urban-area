"""Tarefas do Earth Engine: acompanhamento e fila de exportação.

- `status` / `summary`: tabela das tarefas de uma conta.
- `run_queue`: recebe uma lista de tarefas (nome, asset de destino, função que cria a tarefa),
  pula as que já têm asset gravado ou já estão na fila, e inicia as demais respeitando o limite
  de tarefas simultâneas da conta. Com `wait=True`, fica acompanhando até terminar tudo,
  reenviando as que falharem (até `retries` vezes). Cada evento é registrado em `logs/`.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import ee
import pandas as pd

from . import auth, config

LOG_DIR = config.PACKAGE_ROOT / "logs"
# subpastas gravadas como ImageCollection (lidas depois como coleção pelas etapas seguintes)
COLLECTION_FOLDERS = {"mosaicos", "probabilidades"}

_STATES = ["RUNNING", "READY", "COMPLETED", "FAILED", "CANCELLED"]


def _ts(ms) -> str | None:
    return dt.datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M") if ms else None


def status(account: str = "default", limit: int = 200) -> pd.DataFrame:
    """Tabela com as tarefas mais recentes da conta."""
    auth.init(account)
    rows = []
    for t in ee.data.getTaskList()[:limit]:
        rows.append({
            "conta": account,
            "descricao": t.get("description"),
            "estado": t.get("state"),
            "criada": _ts(t.get("creation_timestamp_ms")),
            "inicio": _ts(t.get("start_timestamp_ms")),
            "fim": _ts(t.get("update_timestamp_ms")) if t.get("state") in ("COMPLETED", "FAILED") else None,
            "erro": t.get("error_message"),
        })
    return pd.DataFrame(rows)


def summary(accounts: list[str]) -> pd.DataFrame:
    """Contagem de tarefas por estado em cada conta."""
    frames = [status(a) for a in accounts]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["conta", "estado"])
    table = df.pivot_table(index="conta", columns="estado", values="descricao", aggfunc="count", fill_value=0)
    return table.reindex(columns=[s for s in _STATES if s in table.columns])


# ---------------------------------------------------------------------------------------------
# fila de exportação
# ---------------------------------------------------------------------------------------------
def asset_exists(asset_id: str) -> bool:
    try:
        ee.data.getAsset(asset_id)
        return True
    except ee.EEException:
        return False


def ensure_folder(asset_id: str) -> None:
    """Cria (se faltar) a pasta que vai receber o asset e as pastas acima. Não apaga nem sobrescreve nada."""
    parent = asset_id.rsplit("/", 1)[0]
    if parent.endswith("/assets") or asset_exists(parent):
        return
    ensure_folder(parent)
    ee.data.createAsset({"type": "FOLDER"}, parent)


def ensure_collection(path: str) -> None:
    """Cria (se faltar) uma ImageCollection vazia e as pastas acima dela."""
    if not asset_exists(path):
        ensure_folder(path)
        ee.data.createAsset({"type": "IMAGE_COLLECTION"}, path)


def _log(event: dict, log_name: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    event = {"quando": dt.datetime.now().isoformat(timespec="seconds"), **event}
    with open(LOG_DIR / f"{log_name}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# O projeto do Cloud pode ser compartilhado por muita gente, e a lista de tarefas do projeto não diz
# quem criou cada uma. Por isso a fila registra localmente as tarefas que ELA iniciou em cada conta
# (logs/registro_<conta>.json) e só conta essas no limite de tarefas simultâneas da conta.
def _registry_path(account: str) -> Path:
    return LOG_DIR / f"registro_{account}.json"


def _load_registry(account: str) -> dict[str, dict]:
    p = _registry_path(account)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save_registry(account: str, reg: dict[str, dict]) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    _registry_path(account).write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")


def _refresh(account: str) -> dict[str, dict]:
    """Atualiza o estado das tarefas registradas desta conta."""
    reg = _load_registry(account)
    open_ids = [tid for tid, r in reg.items() if r["estado"] in ("READY", "RUNNING", "INICIADA")]
    for st in (ee.data.getTaskStatus(open_ids) if open_ids else []):
        r = reg.get(st["id"])
        if r is not None:
            r["estado"] = st.get("state", r["estado"])
            r["erro"] = st.get("error_message")
    _save_registry(account, reg)
    return reg


def my_tasks(account: str = "default") -> pd.DataFrame:
    """Tarefas iniciadas pela fila nesta conta, com o estado atual."""
    auth.init(account)
    reg = _refresh(account)
    return pd.DataFrame([{"id": k, **v} for k, v in reg.items()])


def run_queue(specs, account: str = "default", max_concurrent: int | None = None,
              wait: bool = False, poll_seconds: int = 120, retries: int = 1,
              log_name: str = "fila", cfg: dict | None = None) -> pd.DataFrame:
    """Envia as tarefas respeitando o limite da conta. `specs`: [(nome, asset_id, criar_tarefa)]."""
    cfg = cfg or config.load()
    auth.init(account, cfg)
    limit = max_concurrent or cfg["accounts"][account]["max_concurrent"]
    pending = list(specs)
    attempts: dict[str, int] = {}
    started: dict[str, str] = {}   # nome -> id da tarefa
    rows = []

    while pending or (wait and started):
        reg = _refresh(account)
        active = {r["tarefa"]: r["estado"] for r in reg.values() if r["estado"] in ("READY", "RUNNING", "INICIADA")}
        # acompanha as que este processo iniciou
        if started:
            states = {tid: {"state": reg[tid]["estado"], "error_message": reg[tid].get("erro")}
                      for tid in started.values() if tid in reg}
            for name, tid in list(started.items()):
                t = states.get(tid, {})
                if t.get("state") in ("COMPLETED", "FAILED", "CANCELLED"):
                    _log({"tarefa": name, "estado": t["state"], "erro": t.get("error_message")}, log_name)
                    rows.append({"tarefa": name, "estado": t["state"], "erro": t.get("error_message")})
                    del started[name]
                    if t["state"] == "FAILED" and attempts.get(name, 0) <= retries:
                        pending.append(next(s for s in specs if s[0] == name))
        free = limit - len(active)
        while free > 0 and pending:
            name, asset_id, make = pending.pop(0)
            if name in active:
                rows.append({"tarefa": name, "estado": "JÁ NA FILA", "erro": None})
                continue
            if asset_exists(asset_id):
                rows.append({"tarefa": name, "estado": "JÁ EXISTE", "erro": None})
                continue
            parent = asset_id.rsplit("/", 1)[0]
            if parent.rsplit("/", 1)[-1] in COLLECTION_FOLDERS:
                ensure_collection(parent)
            else:
                ensure_folder(asset_id)
            task = make()
            task.start()
            attempts[name] = attempts.get(name, 0) + 1
            started[name] = task.id
            reg = _load_registry(account)
            reg[task.id] = {"tarefa": name, "asset": asset_id, "estado": "INICIADA", "erro": None,
                            "criada": dt.datetime.now().isoformat(timespec="seconds")}
            _save_registry(account, reg)
            _log({"tarefa": name, "estado": "INICIADA", "id": task.id, "asset": asset_id,
                  "conta": account, "tentativa": attempts[name]}, log_name)
            rows.append({"tarefa": name, "estado": "INICIADA", "erro": None})
            free -= 1
        if not wait:
            break
        if pending or started:
            time.sleep(poll_seconds)

    if pending and not wait:
        rows += [{"tarefa": s[0], "estado": "AGUARDANDO VAGA", "erro": None} for s in pending]
    return pd.DataFrame(rows)
