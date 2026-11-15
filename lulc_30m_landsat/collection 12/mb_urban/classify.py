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


def training_samples(year: int, context: ee.Geometry, cfg: dict | None = None,
                     base: ee.FeatureCollection | None = None) -> ee.FeatureCollection:
    """N urbanas + N*balance não urbanas da super carta, só do conjunto de treino.

    `base`: de onde sortear (padrão: a tabela de amostras). Com a tabela de valores do mosaico de uma
    carta, o sorteio é o mesmo, porque ela guarda as mesmas amostras com as mesmas propriedades.
    """
    cfg = cfg or config.load()
    c = cfg["classification"]
    s = ((base if base is not None else samples.table(cfg))
         .filter(ee.Filter.eq("range", window_for_year(year)))
         .filterBounds(context))
    def draw(fc, n):
        # "column": ordena pela coluna `random` gravada na tabela — o mesmo sorteio em qualquer cópia
        #           ou upload da tabela (padrão da Col 12).
        # "ee_random_column": recalcula com randomColumn() como na Col 11; o sorteio muda se a tabela
        #           for copiada ou subida de novo. Use só com a tabela original para reproduzir a Col 11.
        order = c.get("sample_order", "column")
        if order == "ee_random_column":
            fc = fc.randomColumn()
        elif order != "column":
            raise ValueError("classification.sample_order deve ser 'column' ou 'ee_random_column'")
        return fc.sort("random").limit(n)

    train = s.filter(ee.Filter.eq("type", "classification"))
    urban = draw(train.filter(ee.Filter.eq("class", 1)), c["urban_samples"])
    other = draw(train.filter(ee.Filter.neq("class", 1)), c["urban_samples"] * c["balance"])
    return urban.merge(other)


def classify_year(carta: str, year: int, cfg: dict | None = None) -> ee.Image:
    """Probabilidades das 4 classes para uma carta e um ano (byte 0-100)."""
    cfg = cfg or config.load()
    c = cfg["classification"]
    context = grids.context(carta, cfg)
    region = grids.region(carta, cfg)
    img = mosaic.get(year, context, cfg, carta=carta)
    table = features_table(carta, cfg) if _use_features_table(carta, cfg) else None
    if table is not None:
        # mosaico gravado só na máscara: os valores nos pontos de treino vêm da tabela da carta
        train = training_samples(year, context, cfg, base=table.filter(ee.Filter.eq("year", year)))
    else:
        train = img.sampleRegions(collection=training_samples(year, context, cfg),
                                  scale=30, geometries=True, tileScale=16)
    # O Random Forest depende da ORDEM das amostras, e sampleRegions devolve uma ordem que muda com
    # o caminho de cálculo (mosaico na hora ou gravado). "sorted" ordena pela coluna `random` e torna o
    # resultado igual nos dois caminhos; "as_returned" mantém a ordem da Col 11 (reprodução).
    if c.get("training_order", "sorted") == "sorted":
        train = train.sort("random")
    rf = (ee.Classifier.smileRandomForest(numberOfTrees=c["trees"], minLeafPopulation=c["min_leaf_population"])
          .train(features=train, classProperty="class", inputProperties=mosaic.BANDS)
          .setOutputMode("MULTIPROBABILITY"))
    probs = img.clip(region).classify(rf).multiply(100).byte().toByte()
    return (probs.arrayPad([4]).arrayProject([0]).arrayFlatten([PROB_BANDS])
            .set("year", year, "grid", carta))


def features_table_id(carta: str, cfg: dict) -> str:
    return config.asset_path(cfg["mosaic"].get("features_table", "amostras_mosaico"), f"amostras_mosaico_{carta}", cfg=cfg)


def features_table(carta: str, cfg: dict) -> ee.FeatureCollection:
    return ee.FeatureCollection(features_table_id(carta, cfg))


def _use_features_table(carta: str, cfg: dict) -> bool:
    m = cfg["mosaic"]
    return (mosaic.source_for(carta, cfg) == "asset" and m.get("store_masked", True)
            and carta in m.get("stored_cartas", []))


def features_export_spec(carta: str, years: list[int] | None = None, cfg: dict | None = None):
    """Tarefa que grava, numa tabela, os valores do mosaico (calculado na hora) em todas as amostras
    (treino e validação) da super carta, para todos os anos. Usada quando o mosaico é gravado só na
    máscara espacial e os pontos de amostra caem fora dela."""
    cfg = cfg or config.load()
    years = years or config.years(cfg)
    context = grids.context(carta, cfg)
    m = cfg["mosaic"]
    parts = []
    for y in years:
        pts = samples.table(cfg).filter(ee.Filter.eq("range", window_for_year(y))).filterBounds(context)
        img = mosaic.on_the_fly(y, context, m.get("encoding", "col12"), m.get("single_pass", True))
        parts.append(img.sampleRegions(collection=pts, scale=30, geometries=True, tileScale=16)
                     .map(lambda f, y=y: f.set("year", y)))
    fc = ee.FeatureCollection(parts).flatten()
    name = f"amostras_mosaico_{carta}"
    asset_id = features_table_id(carta, cfg)
    return (name, asset_id, lambda: ee.batch.Export.table.toAsset(
        collection=fc, description=config.task_description(name, cfg), assetId=asset_id))


def classify_carta(carta: str, years: list[int] | None = None, cfg: dict | None = None) -> ee.Image:
    """Todos os anos numa imagem só: bandas class{k}_prob_{ano}."""
    cfg = cfg or config.load()
    years = years or config.years(cfg)
    imgs = [classify_year(carta, y, cfg).rename([f"{b}_{y}" for b in PROB_BANDS]) for y in years]
    out = imgs[0]
    for im in imgs[1:]:
        out = out.addBands(im)
    return out.set("grid", carta, "years", ee.List(years))


def _metadata(cfg: dict, carta: str, years: list[int], output: str) -> dict:
    """Metadados gravados em cada asset: identificação, parâmetros e origem do código."""
    c = cfg["classification"]
    return {
        # identificação (mesmos campos da Col 11)
        "collection_id": cfg["collection"], "theme": "Urban Area", "territory": "BRAZIL",
        "source": "GT URBANO", "version": c.get("version", 1), "grid": carta,
        "product_type": "prob", "classes": "1 urbano; 2 vegetação; 3 água; 4 agropecuária",
        "description": (f"Col {cfg['collection']}; probabilidade de 4 classes (Random Forest, "
                        f"{c['trees']} árvores); {c['urban_samples']} amostras urbanas / "
                        f"{c['urban_samples'] * c['balance']} não urbanas; mosaico "
                        f"{mosaic.source_for(carta, cfg)} ({cfg['mosaic'].get('encoding', 'col12')}); "
                        f"saída {output}"),
        # parâmetros
        "output_format": output, "year_first": min(years), "year_last": max(years),
        "rf_trees": c["trees"], "rf_min_leaf_population": c["min_leaf_population"],
        "samples_urban": c["urban_samples"], "samples_balance": c["balance"],
        "samples_order": c.get("sample_order", "column"), "training_order": c.get("training_order", "sorted"),
        "samples_table": cfg["samples"]["table"],
        "mosaic_source": mosaic.source_for(carta, cfg), "mosaic_encoding": cfg["mosaic"].get("encoding", "col12"),
        # origem
        "code_version": config.code_version(),
        "exported_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }


def export_tasks(carta: str, years: list[int] | None = None, output: str | None = None,
                 cfg: dict | None = None, suffix: str = "") -> list[tuple[str, str, "callable"]]:
    """Lista de tarefas (nome, asset_id, função que cria a tarefa) — o gestor de fila decide quando iniciar."""
    cfg = cfg or config.load()
    years = years or config.years(cfg)
    output = output or cfg["classification"]["output"]
    folder = cfg["classification"]["folder"]
    region = grids.region(carta, cfg)

    def make(image, name, yrs):
        asset_id = config.asset_path(folder, name, cfg=cfg)
        meta = _metadata(cfg, carta, yrs, output)
        return (name, asset_id, lambda: ee.batch.Export.image.toAsset(
            image=image.set(meta), description=config.task_description(name, cfg), assetId=asset_id,
            region=region, scale=30, maxPixels=1e13))

    if output == "per_year":
        return [make(classify_year(carta, y, cfg)
                     .set("year", y, "system:time_start", ee.Date.fromYMD(y, 1, 1).millis()),
                     f"prob_{carta}_{y}{suffix}", [y]) for y in years]
    if output == "multiband":
        return [make(classify_carta(carta, years, cfg), f"prob_{carta}{suffix}", years)]
    raise ValueError("classification.output deve ser 'per_year' ou 'multiband'")
