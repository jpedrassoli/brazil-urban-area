"""Tarefas do Earth Engine: acompanhamento e fila de exportação.

- `status` / `summary`: tabela das tarefas de uma conta.
- `run_queue`: recebe uma lista de tarefas (nome, asset de destino, função que cria a tarefa),
  pula as que já têm asset gravado ou já estão na fila, e inicia as demais respeitando o limite
  de tarefas simultâneas da conta. Com `wait=True`, fica acompanhando até terminar tudo e trata as
  falhas pelo tipo de erro (veja `run_queue`). Cada evento é registrado em `logs/`; falhas que precisam
  de atenção também em `logs/falhas.jsonl`.
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
            if st.get("batch_eecu_usage_seconds") is not None:      # custo de processamento
                r["eecu_h"] = round(float(st["batch_eecu_usage_seconds"]) / 3600, 3)
            if st.get("start_timestamp_ms") and st.get("update_timestamp_ms"):
                r["minutos"] = round((int(st["update_timestamp_ms"]) - int(st["start_timestamp_ms"])) / 60000, 1)
    _save_registry(account, reg)
    return reg


def my_tasks(account: str = "default") -> pd.DataFrame:
    """Tarefas iniciadas pela fila nesta conta, com o estado atual."""
    auth.init(account)
    reg = _refresh(account)
    return pd.DataFrame([{"id": k, **v} for k, v in reg.items()])


# --- tratamento de falhas ----------------------------------------------------------------------
# Falta de recurso: a mesma tarefa tende a falhar de novo; se houver alternativa (tarefas menores), usa ela.
RESOURCE_ERRORS = ("computation timed out", "memory limit", "too many pixels", "too many concurrent",
                   "capacity exceeded", "user memory")
# Passageiros: vale tentar de novo do mesmo jeito.
TRANSIENT_ERRORS = ("internal error", "service unavailable", "deadline", "unavailable", "backend error",
                    "an internal error", "try again")


def classify_error(msg: str | None) -> str:
    """'recurso', 'passageiro' ou 'codigo' (erro de código/dado: não adianta repetir; precisa de correção)."""
    m = (msg or "").lower()
    if any(k in m for k in RESOURCE_ERRORS):
        return "recurso"
    if any(k in m for k in TRANSIENT_ERRORS) or not m:
        return "passageiro"
    return "codigo"


def _falha(event: dict, log_name: str) -> None:
    """Registra falhas que precisam de atenção em logs/falhas.jsonl (lido na revisão diária)."""
    _log({**event, "fila": log_name}, "falhas")


def run_queue(specs, account: str = "default", max_concurrent: int | None = None,
              wait: bool = False, poll_seconds: int = 120, retries: int = 1,
              log_name: str = "fila", cfg: dict | None = None) -> pd.DataFrame:
    """Envia as tarefas respeitando o limite da conta.

    `specs`: [(nome, asset_id, criar_tarefa)] ou [(nome, asset_id, criar_tarefa, alternativa)], em que
    `alternativa()` devolve uma lista de specs menores que produzem o mesmo resultado (ex.: por janela).

    Falhas (com `wait=True`), conforme o tipo de erro (`classify_error`):
      - recurso (tempo/memória): usa a alternativa, se houver; senão tenta de novo até `retries` vezes;
      - passageiro: tenta de novo até `retries` vezes;
      - código/dado: não repete; registra em logs/falhas.jsonl para correção.
    Tarefas que já estavam na fila (de uma execução anterior) são acompanhadas do mesmo jeito.
    """
    cfg = cfg or config.load()
    config.check_production_code(cfg)
    auth.init(account, cfg)
    limit = max_concurrent or cfg["accounts"][account]["max_concurrent"]
    pending = list(specs)
    by_name = {s[0]: s for s in specs}
    attempts: dict[str, int] = {}
    started: dict[str, str] = {}   # nome -> id da tarefa
    rows = []
    adopted = False

    def handle_failure(name: str, err: str | None):
        kind = classify_error(err)
        spec = by_name.get(name)
        alt = spec[3] if spec is not None and len(spec) > 3 and spec[3] else None
        if kind == "recurso" and alt is not None:
            parts = list(alt())
            for sp in parts:
                by_name[sp[0]] = sp
            pending.extend(parts)
            _log({"tarefa": name, "acao": f"dividida em {len(parts)} tarefas menores", "erro": err}, log_name)
            _falha({"tarefa": name, "tipo": kind, "acao": "dividida", "partes": [sp[0] for sp in parts],
                    "erro": err, "conta": account}, log_name)
        elif kind in ("recurso", "passageiro") and attempts.get(name, 0) <= retries and spec is not None:
            pending.append(spec)
            _log({"tarefa": name, "acao": "reenviada", "erro": err}, log_name)
        else:
            _falha({"tarefa": name, "tipo": kind, "acao": "precisa de correção", "erro": err, "conta": account},
                   log_name)
            rows.append({"tarefa": name, "estado": "PRECISA DE CORREÇÃO", "erro": err})

    while pending or (wait and started):
        reg = _refresh(account)
        active_ids = {r["tarefa"]: tid for tid, r in reg.items() if r["estado"] in ("READY", "RUNNING", "INICIADA")}
        active = set(active_ids)
        if started:
            for name, tid in list(started.items()):
                r = reg.get(tid, {})
                if r.get("estado") in ("COMPLETED", "FAILED", "CANCELLED"):
                    _log({"tarefa": name, "estado": r["estado"], "erro": r.get("erro")}, log_name)
                    rows.append({"tarefa": name, "estado": r["estado"], "erro": r.get("erro")})
                    del started[name]
                    if r["estado"] == "FAILED":
                        handle_failure(name, r.get("erro"))
        if wait and not adopted:                           # tarefas já na fila (execução anterior): acompanha
            last = {}                                      # último estado registrado de cada nome
            for tid, r in sorted(reg.items(), key=lambda kv: kv[1].get("criada", "")):
                last[r["tarefa"]] = r
            for spec in list(pending):                     # falhou antes por recurso e tem alternativa: usa já
                r = last.get(spec[0])
                if (r and r["estado"] == "FAILED" and classify_error(r.get("erro")) == "recurso"
                        and len(spec) > 3 and spec[3] and spec[0] not in active_ids and not asset_exists(spec[1])):
                    pending.remove(spec)
                    handle_failure(spec[0], r.get("erro"))
            for spec in list(pending):
                if spec[0] in active_ids and spec[0] not in started:
                    started[spec[0]] = active_ids[spec[0]]
                    pending.remove(spec)
                    rows.append({"tarefa": spec[0], "estado": "JÁ NA FILA (acompanhando)", "erro": None})
            adopted = True
        free = limit - len(active)
        while free > 0 and pending:
            spec = pending.pop(0)
            name, asset_id, make = spec[0], spec[1], spec[2]
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


def cost_summary(account: str = "default") -> pd.DataFrame:
    """Custo (EECU-h) e duração por tipo de tarefa desta conta; completa no registro o custo que faltar."""
    import re
    auth.init(account)
    reg = _load_registry(account)
    missing = [tid for tid, r in reg.items()
               if r["estado"] in ("COMPLETED", "FAILED", "CANCELLED") and "eecu_h" not in r]
    for i in range(0, len(missing), 50):
        for st in ee.data.getTaskStatus(missing[i:i + 50]):
            r = reg.get(st["id"])
            if r is not None and st.get("batch_eecu_usage_seconds") is not None:
                r["eecu_h"] = round(float(st["batch_eecu_usage_seconds"]) / 3600, 3)
                if st.get("start_timestamp_ms") and st.get("update_timestamp_ms"):
                    r["minutos"] = round((int(st["update_timestamp_ms"]) - int(st["start_timestamp_ms"])) / 60000, 1)
    _save_registry(account, reg)
    df = pd.DataFrame([{"id": k, **v} for k, v in reg.items()])
    if df.empty or "eecu_h" not in df:
        return df
    df["tipo"] = df["tarefa"].map(lambda n: re.sub(r"_(\d{4}|[A-Z]{2}-\d\d-[A-Z]-[A-Z]).*$", "", n))
    return (df.groupby(["tipo", "estado"]).agg(tarefas=("tarefa", "count"), eecu_h=("eecu_h", "sum"),
                                              eecu_h_media=("eecu_h", "mean"), minutos_media=("minutos", "mean"))
            .round(2).reset_index())
