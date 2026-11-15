"""Coleções Landsat (Collection 2): seleção, renomeação de bandas, máscara de nuvem e escala.

Porte de `renameBands.js` e `preProcessing_lib.js` na versão de produção da Col 11
(`collection 11/codes_producao/02_classificacao/users/edimilsonrodriguessantos/mapbiomas/Col10/classificacao/`, commit 671895e5) — só o que o mosaico usa.
"""
from __future__ import annotations

import ee

SR_NAMES = ["BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2"]
RAW_NAMES = ["NIR", "MIR", "TIR"]

# sensor: (coleção SR, bandas SR, coleção bruta, bandas brutas)
SENSORS = {
    "LT04": ("LANDSAT/LT04/C02/T1_L2", ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"],
             "LANDSAT/LT04/C02/T1", ["B4", "B5", "B6"]),
    "LT05": ("LANDSAT/LT05/C02/T1_L2", ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"],
             "LANDSAT/LT05/C02/T1", ["B4", "B5", "B6"]),
    "LE07": ("LANDSAT/LE07/C02/T1_L2", ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"],
             "LANDSAT/LE07/C02/T1", ["B4", "B5", "B6_VCID_1"]),
    "LC08": ("LANDSAT/LC08/C02/T1_L2", ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"],
             "LANDSAT/LC08/C02/T1", ["B5", "B6", "B10"]),
    "LC09": ("LANDSAT/LC09/C02/T1_L2", ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"],
             "LANDSAT/LC09/C02/T1", ["B5", "B6", "B10"]),
}


def mask_clouds_qa(image: ee.Image) -> ee.Image:
    """Remove nuvem (bit 3) e sombra de nuvem (bit 4) do QA_PIXEL."""
    qa = image.select("QA_PIXEL")
    mask = qa.bitwiseAnd(1 << 4).eq(0).And(qa.bitwiseAnd(1 << 3).eq(0))
    return image.updateMask(mask)


def apply_scale_factors(image: ee.Image) -> ee.Image:
    """Fator de escala da reflectância de superfície (Collection 2, Level 2)."""
    optical = image.select("SR_B.").multiply(0.0000275).add(-0.2)
    return image.addBands(optical, None, True)


def _date_filter(year: int) -> ee.Filter:
    # Igual à Col 11: filterDate(ano-01-01, ano-12-31) — o fim é exclusivo (31/12 fica de fora).
    return ee.Filter.date(f"{year}-01-01", f"{year}-12-31")


def surface_reflectance(year: int, roi: ee.Geometry) -> ee.ImageCollection:
    """Landsat 4, 5, 7, 8 e 9 SR do ano, sem nuvem, escalado, bandas padronizadas."""
    # O filtro de data vem antes da máscara/escala (na Col 11 vinha depois): mesmas imagens, menos trabalho.
    cols = [ee.ImageCollection(sr).filter(_date_filter(year)).filterBounds(roi).map(mask_clouds_qa)
            .map(apply_scale_factors).select(bands, SR_NAMES)
            for sr, bands, _, _ in SENSORS.values()]
    merged = cols[0]
    for c in cols[1:]:
        merged = merged.merge(c)
    return merged


def raw(year: int, roi: ee.Geometry) -> ee.ImageCollection:
    """Landsat 4, 5, 7, 8 e 9 brutos (números digitais) do ano, sem nuvem: NIR, MIR, TIR."""
    cols = [ee.ImageCollection(col).filter(_date_filter(year)).filterBounds(roi).map(mask_clouds_qa)
            .select(bands, RAW_NAMES)
            for _, _, col, bands in SENSORS.values()]
    merged = cols[0]
    for c in cols[1:]:
        merged = merged.merge(c)
    return merged
