"""Cartas 1:250.000 do IBGE: lista, vizinhança (super carta) e divisão em fatias.

Substitui as listas fixas da Col 11 (inclusive a `cartasParaClassificacao`, que não existia
em listsAndDicts.js): a lista agora vem do próprio asset de cartas.
"""
from __future__ import annotations

import ee

from . import config


def cartas_fc(cfg: dict | None = None) -> ee.FeatureCollection:
    cfg = cfg or config.load()
    return ee.FeatureCollection(cfg["grids"]["cartas"])


def cartas_hex_fc(cfg: dict | None = None) -> ee.FeatureCollection:
    cfg = cfg or config.load()
    return ee.FeatureCollection(cfg["grids"]["cartas_hex"])


def list_cartas(cfg: dict | None = None, only_hex: bool = True) -> list[str]:
    """Nomes das cartas, ordenados. `only_hex` restringe às cartas da grade hexagonal válida."""
    cfg = cfg or config.load()
    field = cfg["grids"]["grid_field"]
    fc = cartas_hex_fc(cfg) if only_hex else cartas_fc(cfg)
    return sorted(fc.aggregate_array(field).distinct().getInfo())


def context_fc(carta: str, cfg: dict | None = None) -> ee.FeatureCollection:
    """Super carta como coleção: a carta e as vizinhas que tocam um buffer de 2 m (getContext da Col 11)."""
    cfg = cfg or config.load()
    field = cfg["grids"]["grid_field"]
    fc = cartas_fc(cfg)
    carta_ft = ee.Feature(fc.filter(ee.Filter.eq(field, carta)).first())
    return fc.filterBounds(carta_ft.geometry().buffer(cfg["grids"]["context_buffer_m"], 1))


def context(carta: str, cfg: dict | None = None) -> ee.Geometry:
    """Super carta como retângulo envolvente (usado no mosaico e na classificação da Col 11)."""
    return context_fc(carta, cfg).geometry().bounds(10)


def region(carta: str, cfg: dict | None = None) -> ee.Geometry:
    """Área a classificar/exportar: o hexágono da carta."""
    cfg = cfg or config.load()
    field = cfg["grids"]["grid_field"]
    return cartas_hex_fc(cfg).filter(ee.Filter.eq(field, carta)).geometry()


def shard(items: list[str], index: int, total: int) -> list[str]:
    """Fatia `index` (1..total) de uma lista, intercalada para equilibrar regiões entre contas."""
    if not 1 <= index <= total:
        raise ValueError("index deve estar entre 1 e total")
    return items[index - 1::total]
