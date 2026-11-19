"""Pré-voo: confere, ANTES de classificar, se cada carta tem o que a classificação precisa.

Para cada carta devolve uma linha com o estado ("ok", "classe_ausente", "sem_limiar", "sem_mosaico") e o motivo.
Uma classe ausente no treino de uma janela é o caso que desloca as bandas de probabilidade (corrigido em
`classify.classify_year`) e deixa o urbano em zero: por isso é alerta e nunca passa em silêncio.
Só LÊ o Earth Engine.
"""
from __future__ import annotations

import ee
import pandas as pd

from . import config, grids, mosaic, registry

CLASSES = ("1", "2", "3", "4")      # 1 urbano, 2 vegetação, 3 água, 4 agropecuária


def check_carta(carta: str, cfg: dict | None = None, table: ee.FeatureCollection | None = None) -> dict:
    """Pré-voo de uma carta. `table`: tabela de amostras alternativa (usada nos testes de falha injetada)."""
    cfg = cfg or config.load()
    contagem = registry.training_counts(carta, cfg, table)
    problemas, estado = [], "ok"
    for janela, h in contagem.items():
        faltam = [k for k in CLASSES if k not in h]
        if faltam:
            problemas.append(f"janela {janela}: sem classes {','.join(faltam)} no treino")
            estado = "classe_ausente"
    limiar = ee.Image(cfg["postprocess"]["threshold_image"]).select("percentil").reduceRegion(
        ee.Reducer.mean(), grids.region(carta, cfg), 1000, maxPixels=1e9).getInfo().get("percentil")
    if limiar is None:
        problemas.append("sem limiar na carta (imagem de limiares vazia)")
        estado = estado if estado != "ok" else "sem_limiar"
    fonte = mosaic.source_for(carta, cfg)
    if fonte == "asset":
        m = cfg["mosaic"]
        fontes = [m.get("asset") or config.asset_path("mosaicos", cfg=cfg)] + list(m.get("extra_collections") or [])
        col = ee.ImageCollection(fontes[0])
        for extra in fontes[1:]:
            col = col.merge(ee.ImageCollection(extra))
        anos = set(col.filter(ee.Filter.eq("mosaic_version", m.get("version", 1))).filterBounds(grids.region(carta, cfg))
                   .aggregate_array("year").getInfo())
        falta = [y for y in config.years(cfg) if y not in anos]
        if falta:
            problemas.append(f"mosaico gravado sem os anos {falta}")
            estado = estado if estado != "ok" else "sem_mosaico"
    return {"carta": carta, "estado": estado, "mosaico": fonte, "limiar_medio": limiar,
            "treino": contagem, "problemas": " | ".join(problemas)}


def check(cartas: list[str] | None = None, cfg: dict | None = None) -> pd.DataFrame:
    """Pré-voo das cartas do escopo (ou da lista dada)."""
    cfg = cfg or config.load()
    return pd.DataFrame([check_carta(c, cfg) for c in (cartas or grids.cartas_in_scope(cfg))])
