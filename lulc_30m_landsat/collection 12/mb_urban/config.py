"""Leitura da configuração central.

Ordem de procura: argumento de `load()` > variável de ambiente MB_URBAN_CONFIG >
`config/col12.yaml` (configuração local, não versionada) > `config/col12.exemplo.yaml` (exemplo público).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
LOCAL_CONFIG = PACKAGE_ROOT / "config" / "col12.yaml"
EXAMPLE_CONFIG = PACKAGE_ROOT / "config" / "col12.exemplo.yaml"


def config_path(path: str | os.PathLike | None = None) -> Path:
    if path or os.environ.get("MB_URBAN_CONFIG"):
        return Path(path or os.environ["MB_URBAN_CONFIG"])
    return LOCAL_CONFIG if LOCAL_CONFIG.exists() else EXAMPLE_CONFIG


@lru_cache(maxsize=None)
def load(path: str | os.PathLike | None = None) -> dict:
    """Carrega a configuração (veja a ordem de procura no topo do módulo)."""
    with open(config_path(path), encoding="utf-8") as f:
        return yaml.safe_load(f)


def years(cfg: dict | None = None) -> list[int]:
    cfg = cfg or load()
    first, last = cfg["years"]
    return list(range(first, last + 1))


def destination_root(cfg: dict | None = None) -> str:
    """Pasta raiz onde os assets são gravados (teste ou produção)."""
    cfg = cfg or load()
    return cfg["destinations"][cfg["destination"]].rstrip("/")


def asset_path(*parts: str, cfg: dict | None = None) -> str:
    """Monta um caminho de asset dentro do destino ativo."""
    return "/".join([destination_root(cfg), *[p.strip("/") for p in parts]])


def task_description(name: str, cfg: dict | None = None) -> str:
    """Nome da tarefa no Earth Engine: prefixo da configuração + nome (máx. 100 caracteres)."""
    cfg = cfg or load()
    return (cfg.get("task_prefix", "") + name)[:100]


def code_version() -> str:
    """Commit do código usado (gravado nos metadados). Marca '-modificado' se houver alterações locais."""
    import subprocess
    from . import __version__
    try:
        run = lambda *a: subprocess.run(["git", "-C", str(PACKAGE_ROOT), *a], capture_output=True,
                                        text=True, check=True).stdout.strip()
        commit = run("rev-parse", "--short", "HEAD")
        dirty = run("status", "--porcelain", "--", ".")
        return f"mb_urban {__version__} @ {commit}" + ("-modificado" if dirty else "")
    except Exception:
        return f"mb_urban {__version__}"
