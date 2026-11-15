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


def config_hash(cfg: dict | None = None) -> str:
    """Resumo (sha256, 16 caracteres) da configuração usada: identifica exatamente os parâmetros de uma rodada."""
    import hashlib
    import json
    cfg = cfg or load()
    return hashlib.sha256(json.dumps(cfg, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def input_assets(cfg: dict | None = None) -> dict[str, str]:
    """Insumos lidos pelo pipeline (chave da config → asset)."""
    cfg = cfg or load()
    p, m = cfg["postprocess"], cfg["mosaic"]
    out = {
        "samples.table": cfg["samples"]["table"],
        "grids.cartas": cfg["grids"]["cartas"],
        "grids.cartas_hex": cfg["grids"]["cartas_hex"],
        "postprocess.threshold_image": p["threshold_image"],
        "postprocess.spatial_mask": p["spatial_mask"],
        "postprocess.irs_asset": p["irs_asset"],
        "postprocess.cartas_export": p["cartas_export"],
        "mosaic.collection": m.get("asset") or asset_path("mosaicos", cfg=cfg),
    }
    for i, c in enumerate(m.get("extra_collections") or []):
        out[f"mosaic.extra_collections.{i}"] = c
    return out


_INPUTS_CACHE: dict[str, str] = {}


def inputs_manifest(cfg: dict | None = None) -> str:
    """Texto com cada insumo e a data da última atualização do asset (para saber se mudou depois da rodada)."""
    import ee
    cfg = cfg or load()
    key = config_hash(cfg)
    if key not in _INPUTS_CACHE:
        parts = []
        for k, a in input_assets(cfg).items():
            try:
                t = ee.data.getAsset(a).get("updateTime", "?")[:19]
            except Exception:
                t = "inacessível"
            parts.append(f"{k}={a}@{t}")
        _INPUTS_CACHE[key] = "; ".join(parts)
    return _INPUTS_CACHE[key]


def check_production_code(cfg: dict | None = None) -> None:
    """Na produção, não aceita código com alterações locais sem commit (o asset não teria versão rastreável)."""
    cfg = cfg or load()
    if cfg.get("destination") == "producao" and code_version().endswith("-modificado"):
        raise RuntimeError("Destino de produção com código modificado sem commit: faça commit antes de rodar.")
