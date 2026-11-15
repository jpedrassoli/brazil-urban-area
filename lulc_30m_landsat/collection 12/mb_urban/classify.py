"""Classificação por Random Forest, por carta e ano: probabilidade de 4 classes.

Porte das versões de produção da Col 11 (`collection 11/codes_producao/02_classificacao/...`):
  - `Col11/classification/classification_batch_v3.js` (commit 0c0239bf);
  - `Col11/classification/class_lib.js` (commit e723977f).

Saída: bandas class1_prob (urbano), class2_prob (vegetação), class3_prob (água),
class4_prob (agropecuária), em 0-100 (byte).

Formatos de exportação (config `classification.output`):
  - "per_year": uma imagem por carta e ano, como na Col 11;
  - "multiband": uma imagem por carta com todos os anos (bandas class{k}_prob_{ano}).

Comportamento herdado da Col 11 (mantido para reprodutibilidade): se uma classe não tiver amostras
na super carta, o vetor de probabilidades fica mais curto e `arrayPad` completa com zeros NO FIM —
as probabilidades das classes seguintes ficam deslocadas para a posição errada.
"""
from __future__ import annotations

import ee

from . import config, grids, mosaic, samples

PROB_BANDS = ["class1_prob", "class2_prob", "class3_prob", "class4_prob"]


def window_for_year(year: int) -> str:
    """Janela de amostras usada para cada ano (dictOfRanges de classification_batch_v3)."""
    if year < 1993:
        return "1985_to_2020"
    if year < 2001:
        return "1993_to_2020"
    if year < 2009:
        return "2001_to_2020"
    return "2009_to_2020"


def training_samples(year: int, context: ee.Geometry, cfg: dict | None = None) -> ee.FeatureCollection:
    """N urbanas + N*balance não urbanas da super carta, só do conjunto de treino."""
    cfg = cfg or config.load()
    c = cfg["classification"]
    s = (samples.table(cfg)
         .filter(ee.Filter.eq("range", window_for_year(year)))
         .filterBounds(context))
    urban = (s.filter(ee.Filter.eq("class", 1)).filter(ee.Filter.eq("type", "classification"))
             .randomColumn().sort("random").limit(c["urban_samples"]))
    other = (s.filter(ee.Filter.neq("class", 1)).filter(ee.Filter.eq("type", "classification"))
             .randomColumn().sort("random").limit(c["urban_samples"] * c["balance"]))
    return urban.merge(other)


def classify_year(carta: str, year: int, cfg: dict | None = None) -> ee.Image:
    """Probabilidades das 4 classes para uma carta e um ano (byte 0-100)."""
    cfg = cfg or config.load()
    c = cfg["classification"]
    context = grids.context(carta, cfg)
    region = grids.region(carta, cfg)
    img = mosaic.get(year, context, cfg)
    train = img.sampleRegions(collection=training_samples(year, context, cfg),
                              scale=30, geometries=True, tileScale=16)
    rf = (ee.Classifier.smileRandomForest(numberOfTrees=c["trees"], minLeafPopulation=c["min_leaf_population"])
          .train(features=train, classProperty="class", inputProperties=mosaic.BANDS)
          .setOutputMode("MULTIPROBABILITY"))
    probs = img.clip(region).classify(rf).multiply(100).byte().toByte()
    return (probs.arrayPad([4]).arrayProject([0]).arrayFlatten([PROB_BANDS])
            .set("year", year, "grid", carta))


def classify_carta(carta: str, years: list[int] | None = None, cfg: dict | None = None) -> ee.Image:
    """Todos os anos numa imagem só: bandas class{k}_prob_{ano}."""
    cfg = cfg or config.load()
    years = years or config.years(cfg)
    imgs = [classify_year(carta, y, cfg).rename([f"{b}_{y}" for b in PROB_BANDS]) for y in years]
    out = imgs[0]
    for im in imgs[1:]:
        out = out.addBands(im)
    return out.set("grid", carta, "years", ee.List(years))


def _metadata(cfg: dict) -> dict:
    return {
        "collection_id": cfg["collection"], "theme": "Urban Area", "territory": "BRAZIL",
        "source": "GT URBANO", "mosaic_source": cfg["mosaic"]["source"],
        "mosaic_encoding": cfg["mosaic"].get("encoding", "col12"),
        "samples_table": cfg["samples"]["table"],
    }


def export_tasks(carta: str, years: list[int] | None = None, output: str | None = None,
                 cfg: dict | None = None, suffix: str = "") -> list[tuple[str, str, "callable"]]:
    """Lista de tarefas (nome, asset_id, função que cria a tarefa) — o gestor de fila decide quando iniciar."""
    cfg = cfg or config.load()
    years = years or config.years(cfg)
    output = output or cfg["classification"]["output"]
    folder = cfg["classification"]["folder"]
    region = grids.region(carta, cfg)
    meta = _metadata(cfg)

    def make(image, name):
        asset_id = config.asset_path(folder, name, cfg=cfg)
        return (name, asset_id, lambda: ee.batch.Export.image.toAsset(
            image=image.set(meta), description=name, assetId=asset_id,
            region=region, scale=30, maxPixels=1e13))

    if output == "per_year":
        return [make(classify_year(carta, y, cfg).set("year", y), f"prob_{carta}_{y}{suffix}") for y in years]
    if output == "multiband":
        return [make(classify_carta(carta, years, cfg), f"prob_{carta}{suffix}")]
    raise ValueError("classification.output deve ser 'per_year' ou 'multiband'")
