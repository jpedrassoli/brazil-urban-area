"""Acompanhamento de tarefas do Earth Engine por conta.

Nesta primeira versão: só consulta (status). O gestor de fila — manter N tarefas por conta,
pular assets que já existem, retomar falhas — entra junto com a classificação (Fase 2).
"""
from __future__ import annotations

import datetime as dt

import ee
import pandas as pd

from . import auth

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
