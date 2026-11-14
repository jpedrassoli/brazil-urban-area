"""Leitura da configuração central (config/col12.yaml)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PACKAGE_ROOT / "config" / "col12.yaml"


@lru_cache(maxsize=None)
def load(path: str | os.PathLike | None = None) -> dict:
    """Carrega o YAML. Ordem: argumento > variável MB_URBAN_CONFIG > config/col12.yaml."""
    path = Path(path or os.environ.get("MB_URBAN_CONFIG") or DEFAULT_CONFIG)
    with open(path, encoding="utf-8") as f:
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
