"""Mosaico anual de 42 bandas usado pela classificação.

Duas fontes, escolhidas em config (`mosaic.source`), que entregam a MESMA imagem:
  - "on_the_fly": calculado do Landsat na hora — porte fiel de `mosaic_production.js` na versão de
    produção da Col 11 (`collection 11/codes_producao/02_classificacao/users/edimilsonrodriguessantos/mapbiomas/Col10/classificacao/mosaic_production.js`, commit bf9c98b0);
  - "asset":      lido de uma ImageCollection de mosaicos pré-processados (propriedade `year`).

O resto do pipeline só chama `get(year, roi)` e não sabe qual fonte foi usada.

Codificação das bandas (config `mosaic.encoding`):
  - "col11": igual à Col 11 — TODAS as bandas viram uint16 de (valor + 1) * 1000. Nas bandas que
    já vêm em 0-100 (frações de mistura) ou 0-200 (NDFI) isso passa de 65535 e satura, perdendo
    informação. Use só para conferir a reprodução da Col 11.
  - "col12" (padrão): índices e reflectâncias seguem (valor + 1) * 1000; frações e NDFI viram
    valor * 10 (0-1000 e 0-2000), sem saturar.
"""
from __future__ import annotations

import ee

from . import config, indices, landsat

MEDIAN_BANDS = [
    "BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2",
    "NDVI", "EVI", "EVI2", "SAVI",
    "MNDWI", "NDWIm", "AWEIsh",
    "NDBI", "NBR", "NDRI", "BAI", "UI", "NDUI", "BSI", "BU", "NDFI",
    "GV", "NPV", "SOIL", "CLOUD", "GVS", "SHADE",
    "SUBS", "VEG", "DARK",
]
P1090_BANDS = ["EVI", "EVI2"]
RAW_BANDS = ["EBBI"]

# Ordem final das 42 bandas (a mesma lista `bands` de classification_batch.js)
BANDS = MEDIAN_BANDS + [
    "EVI_p10", "EVI_p90", "EVI2_p10", "EVI2_p90", "EVI_dif9010", "EVI2_dif9010",
    "EBBI", "EBBI_p25", "EBBI_p75", "EBBI_dif7525", "EBBI_p90",
]


# Bandas que já saem em escala 0-100 (frações) ou 0-200 (NDFI)
BYTE_BANDS = ["NDFI", "GV", "NPV", "SOIL", "CLOUD", "GVS", "SHADE", "SUBS", "VEG", "DARK"]
ENCODINGS = ("col11", "col12")


def _scale(img: ee.Image) -> ee.Image:
    return img.add(1).multiply(1000).toUint16()


def _encode_median(median: ee.Image, encoding: str) -> ee.Image:
    if encoding == "col11":
        return _scale(median)
    if encoding != "col12":
        raise ValueError(f"mosaic.encoding deve ser um de {ENCODINGS}")
    continuous = [b for b in MEDIAN_BANDS if b not in BYTE_BANDS]
    encoded = _scale(median.select(continuous)).addBands(
        median.select(BYTE_BANDS).multiply(10).toUint16())
    return encoded.select(MEDIAN_BANDS)


def on_the_fly(year: int, roi: ee.Geometry, encoding: str = "col12") -> ee.Image:
    """Mosaico calculado a partir das coleções Landsat (mosaicGenByBandsLists da Col 11)."""
    sr = landsat.surface_reflectance(year, roi).map(indices.sr_feature_space)
    raw = landsat.raw(year, roi).map(indices.raw_feature_space)

    sr_median = _encode_median(sr.select(MEDIAN_BANDS).median(), encoding)

    sr_1090 = _scale(sr.select(P1090_BANDS).reduce(ee.Reducer.percentile([10, 90])))
    sr_dif = (sr_1090.select([1, 3]).subtract(sr_1090.select([0, 2]))
              .rename(["EVI_dif9010", "EVI2_dif9010"]))

    raw_median = _scale(raw.select(RAW_BANDS).median())
    raw_90 = _scale(raw.select(RAW_BANDS).reduce(ee.Reducer.percentile([90])))
    raw_2575 = _scale(raw.select(RAW_BANDS).reduce(ee.Reducer.percentile([25, 75])))
    raw_dif = raw_2575.select([1]).subtract(raw_2575.select([0])).rename(["EBBI_dif7525"])

    return (sr_median
            .addBands(sr_1090).addBands(sr_dif)
            .addBands(raw_median)
            .addBands(raw_2575).addBands(raw_dif)
            .addBands(raw_90)
            .select(BANDS))


def from_asset(year: int, roi: ee.Geometry, asset: str) -> ee.Image:
    """Mosaico pré-processado: imagens da coleção com `year` igual, recortadas pela região."""
    col = ee.ImageCollection(asset).filter(ee.Filter.eq("year", year)).filterBounds(roi)
    return col.mosaic().select(BANDS)


def get(year: int, roi: ee.Geometry, cfg: dict | None = None) -> ee.Image:
    """Ponto único de acesso ao mosaico, segundo `mosaic.source` da configuração."""
    cfg = cfg or config.load()
    m = cfg["mosaic"]
    if m["source"] == "on_the_fly":
        img = on_the_fly(year, roi, m.get("encoding", "col12"))
    elif m["source"] == "asset":
        if not m.get("asset"):
            raise ValueError("mosaic.source = asset, mas mosaic.asset está vazio na configuração")
        img = from_asset(year, roi, m["asset"])
    else:
        raise ValueError(f"mosaic.source desconhecido: {m['source']}")
    return img.set("year", year, "mosaic_source", m["source"], "mosaic_encoding", m.get("encoding", "col12"))


def export_to_asset(year: int, region: ee.Geometry, name: str, folder: str = "mosaics",
                    cfg: dict | None = None) -> ee.batch.Task:
    """Cria (sem iniciar) a tarefa que grava um mosaico on-the-fly como asset.

    Gera a coleção que depois pode ser usada com `mosaic.source: asset`.
    """
    cfg = cfg or config.load()
    encoding = cfg["mosaic"].get("encoding", "col12")
    img = on_the_fly(year, region, encoding).set(
        "year", year, "collection", cfg["collection"], "mosaic_encoding", encoding)
    asset_id = config.asset_path(folder, name, cfg=cfg)
    return ee.batch.Export.image.toAsset(
        image=img, description=config.task_description(name, cfg), assetId=asset_id, region=region,
        scale=30, maxPixels=1e13,
    )
