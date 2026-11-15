"""Acesso aos resultados da Coleção 11, para comparação.

As probabilidades da Col 11 foram exportadas em várias coleções (uma por conta/projeto de quem
rodou). A lista é a de `rawCol` em `Col11/results/batchResults.js`, versão de produção
(`collection 11/codes_producao/04_pos_processamento/...`, commit 8a208356).
"""
from __future__ import annotations

import ee

PROB_COLLECTIONS = [
    "projects/jpedrassoli/assets/MB-COLLECTION-11/PROB-COL11-V1",
    "users/joigenaro/MAPBIOMAS-COLLECTION-11/PROB-COL11-V1",
    "projects/ee-spatialeanalytics/assets/MAPBIOMAS-COLLECTION-11/PROB-COL11-V1",
    "projects/ee-jpedrassoli/assets/MAPBIOMAS-COLLECTION-11/PROB-COL11-V1",
    "projects/juliopedrassoli/assets/MB-COLLECTION-11/PROB-COL11-V1",
    "projects/bmm-mb-landsat/assets/col11/classification",
    "projects/bmm-mb-cl01/assets/landsat_col11/classification",
    "projects/bmm-mb-cl02/assets/landsat_col11/classification",
    "projects/bmm-mb-cl03/assets/landsat_col11/classification",
    "users/ers-mb-urb/col11/classification",
    "projects/ee-ers/assets/mapbiomas/col11/classification",
    "projects/ee-doc-environ/assets/classification",
    "projects/ee-oficina/assets/classification",
    "projects/ee-pb-fb/assets/mb/col11/classification",
    "users/breno/mb_landsat_11/classification",
    "users/brenomalheiros/mb_col11_classification",
]

FINAL = "projects/mapbiomas-brazil/assets/LAND-COVER/COLLECTION-11/URBAN/classification_sf"


def probabilities() -> ee.ImageCollection:
    col = ee.ImageCollection(PROB_COLLECTIONS[0])
    for c in PROB_COLLECTIONS[1:]:
        col = col.merge(ee.ImageCollection(c))
    return col


def probability(carta: str, year: int) -> ee.Image:
    """Probabilidades (4 bandas) da Col 11 para uma carta e ano (mediana, como em batchResults)."""
    return (probabilities().filter(ee.Filter.eq("grid", carta)).filter(ee.Filter.eq("year", year))
            .median().select(["class1_prob", "class2_prob", "class3_prob", "class4_prob"]))


def final_map(carta: str, version: str = "v6") -> ee.Image:
    """Mapa final binário da Col 11 (41 bandas classification_1985..2025)."""
    return ee.Image(f"{FINAL}/{carta}_{version}")


# --- entradas do pré-filtro da Col 11 (batchResults.js de produção, commit 8a208356) ---------------
import json as _json
from pathlib import Path as _Path

_EXCL = _json.loads((_Path(__file__).parent / "data" / "col11_cartas_excluidas.json").read_text(encoding="utf-8"))
PROBMEAN_COL10 = "projects/mapbiomas-workspace/TRANSVERSAIS/INFRAURBANA10/probMean/classification_{}_v1"
PROBMEAN_GRIDS = ["NA", "NB", "SA", "SB", "SC", "SD", "SE", "SF", "SG", "SH", "SI"]


def probabilities_filtered() -> ee.ImageCollection:
    """Probabilidades da Col 11 sem as cartas sem amostras estáveis (`list`) e sem as do Norte."""
    return (probabilities()
            .filter(ee.Filter.inList("grid", _EXCL["list"]).Not())
            .filter(ee.Filter.inList("grid", _EXCL["cartasNorte"]).Not()))


def _probmean_col10() -> ee.Image:
    return ee.ImageCollection([ee.Image(PROBMEAN_COL10.format(g)) for g in PROBMEAN_GRIDS]).mosaic()


def urban_probability(year: int) -> ee.Image:
    """Probabilidade urbana usada no pré-filtro da Col 11 (mosaicClassificationByYear):
    probMean da Col 10 por baixo e a probabilidade da Col 11 (filtrada) por cima. 2025 usa a Col 10 de 2024."""
    y10 = min(year, 2024)
    band = f"classification_{year}"
    img1 = _probmean_col10().select(f"classification_{y10}").rename(band)
    img2 = (probabilities_filtered().filter(ee.Filter.eq("year", year))
            .select("class1_prob").median().rename(band))
    return (ee.ImageCollection([img1.toByte(), img2.toByte()]).mosaic().toByte()
            .selfMask().rename(band).set("year", year))


def all_probabilities(year: int) -> ee.Image:
    """As 4 probabilidades da Col 11 (coleção filtrada), com os nomes usados nas regras do pré-filtro."""
    return (probabilities_filtered().filter(ee.Filter.eq("year", year)).median()
            .select(["class1_prob", "class2_prob", "class3_prob", "class4_prob"],
                    ["urban", "veg", "water", "other"]))
