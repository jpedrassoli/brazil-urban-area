"""Amostras de treino a partir de áreas estáveis nas coleções do MapBiomas.

Porte das versões de produção da Col 11 (`collection 11/codes_producao/01_amostras/...`):
  - `mb_batch/collections.js` (commit be5b5c69): estabilidade entre coleções e reagrupamento de classes;
  - `Col11/preProcessing/samplesCreation_v4.js` (commit b0f79ab8): sorteio estratificado por super carta;
  - `Col11/preProcessing/visSamplesByGrid_v2.js` (commit 543526ff): separação treino/validação.

Classes reagrupadas: 1 urbano, 2 vegetação (florestal e campestre), 3 água, 4 agropecuária.
"""
from __future__ import annotations

import ee

from . import config, grids

# Reagrupamento das classes do MapBiomas (remapMapBiomas). Classes fora da lista ficam mascaradas.
REMAP_FROM = [3, 4, 5, 6, 49,                 # floresta
              11, 12, 32, 29, 50,             # vegetação campestre/arbustiva
              15, 18, 19, 39, 20, 40, 62, 41, 36, 46, 47, 35, 48, 9, 21,  # agropecuária
              23, 24, 30, 75, 25,             # não vegetado (só 24 = urbano é mantido)
              33, 31, 27]                     # água
REMAP_TO = [2, 2, 2, 2, 2,
            2, 2, 2, 2, 2,
            4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4,
            0, 1, 0, 0, 0,
            3, 3, 3]
CLASSES = [1, 2, 3, 4]


def _lulc(col: int, cfg: dict) -> ee.Image:
    return ee.Image(cfg["samples"]["lulc_assets"][col])


def remap(image: ee.Image) -> ee.Image:
    return image.remap(REMAP_FROM, REMAP_TO).rename("class")


def collections_for_year(year: int, cfg: dict) -> list[int]:
    """Coleções usadas na estabilidade do ano.

    `samples.stability_mode`:
      - "all" (Col 11): todas as `stability_collections`, que precisam cobrir o ano;
      - "available": só as que cobrem o ano (`samples.lulc_last_year`), para janelas que passam do
        último ano da coleção mais antiga. Em anos cobertos por todas, é igual a "all".
    """
    s = cfg["samples"]
    cols = list(s["stability_collections"])
    if s.get("stability_mode", "all") == "available":
        last = {int(k): v for k, v in s.get("lulc_last_year", {}).items()}
        cols = [c for c in cols if last.get(c, 0) >= year]
        if len(cols) < s.get("min_collections", 1):
            raise ValueError(f"{year}: só {len(cols)} coleção(ões) cobrem o ano (mínimo {s.get('min_collections', 1)})")
    return cols


def stable_by_year(year: int, cfg: dict | None = None) -> ee.Image:
    """Classe da coleção de referência onde todas as coleções concordam no ano (stableCollectionByYear).

    A referência é `samples.reference_collection`; se ela não cobrir o ano (modo "available"), usa a
    coleção mais recente entre as que cobrem."""
    cfg = cfg or config.load()
    s = cfg["samples"]
    band = f"classification_{year}"
    cols = collections_for_year(year, cfg)
    ref_col = s["reference_collection"] if s["reference_collection"] in cols else max(cols)
    ref = _lulc(ref_col, cfg).select(band)
    mean = ee.ImageCollection([_lulc(c, cfg).select(band) for c in cols]).sum().divide(len(cols))
    return ref.where(ref.eq(mean), ref).where(ref.neq(mean), 0).selfMask()


def stable_by_years(years: list[int], cfg: dict | None = None) -> ee.Image:
    """Estável entre coleções E ao longo dos anos da janela (stableCollectionByKYears)."""
    cfg = cfg or config.load()
    first = stable_by_year(years[0], cfg).rename("stable").toByte()
    mean = (ee.ImageCollection([stable_by_year(y, cfg).rename("stable").toByte() for y in years])
            .sum().divide(len(years)))
    return first.where(first.eq(mean), first).where(first.neq(mean), 0).selfMask()


def windows(cfg: dict | None = None) -> dict[str, list[int]]:
    """Janelas de anos: {'1985_to_2020': [1985..2020], '1993_to_2020': [...], ...}."""
    cfg = cfg or config.load()
    s = cfg["samples"]
    start, end, step = s["window_start"], s["window_end"], s["window_step"]
    out = {}
    i = start + step
    while i <= end:
        years = list(range(i - step, end + 1))
        out[f"{years[0]}_to_{years[-1]}"] = years
        i += step
    return out


def stable_classes(window: str, cfg: dict | None = None) -> ee.Image:
    """Imagem de classes 1-4 estáveis na janela (o que é sorteado)."""
    cfg = cfg or config.load()
    return remap(stable_by_years(windows(cfg)[window], cfg)).selfMask()


def create(carta: str, window: str, cfg: dict | None = None) -> ee.FeatureCollection:
    """Sorteio estratificado na super carta: N pontos por classe (createSamples)."""
    cfg = cfg or config.load()
    s = cfg["samples"]
    n = s["points_per_class"]
    region = grids.context_fc(carta, cfg).geometry().simplify(5)
    pts = stable_classes(window, cfg).stratifiedSample(
        numPoints=n, classBand="class", region=region, scale=30, geometries=True,
        seed=s["seed"], classValues=CLASSES, classPoints=[n] * len(CLASSES),
        dropNulls=True, tileScale=16)
    return pts.map(lambda f: f.set("range", window, "grid_name", carta))


def split_train_validation(samples: ee.FeatureCollection, cfg: dict | None = None) -> ee.FeatureCollection:
    """Separa treino/validação por janela e por urbano/não urbano (visSamplesByGrid_v2)."""
    cfg = cfg or config.load()
    frac = cfg["samples"]["train_fraction"]

    def by_window(window):
        s = samples.filter(ee.Filter.eq("range", window))
        parts = []
        for flt in (ee.Filter.eq("class", 1), ee.Filter.eq("class", 1).Not()):
            r = s.filter(flt).randomColumn()
            parts.append(r.filter(ee.Filter.lte("random", frac)).map(lambda f: f.set("type", "classification")))
            parts.append(r.filter(ee.Filter.gt("random", frac)).map(lambda f: f.set("type", "validation")))
        merged = parts[0]
        for p in parts[1:]:
            merged = merged.merge(p)
        return merged

    return ee.FeatureCollection([by_window(w) for w in windows(cfg)]).flatten()


def table(cfg: dict | None = None) -> ee.FeatureCollection:
    """Tabela de amostras usada pela classificação (config `samples.table`)."""
    cfg = cfg or config.load()
    return ee.FeatureCollection(cfg["samples"]["table"])


def create_validation_extra(carta: str, cfg: dict | None = None) -> ee.FeatureCollection:
    """Pontos de validação EXTRAS para o início da série, só para avaliação (nunca usados no treino).

    Sorteio estratificado dentro da carta (hexágono), em áreas estáveis numa janela curta do início
    (config `evaluation.extra_validation`), com semente própria.
    """
    cfg = cfg or config.load()
    e = cfg["evaluation"]["extra_validation"]
    years = list(range(e["window_start"], e["window_end"] + 1))
    window = f"{years[0]}_to_{years[-1]}"
    n = e["points_per_class"]
    stable = remap(stable_by_years(years, cfg)).selfMask()
    pts = stable.stratifiedSample(
        numPoints=n, classBand="class", region=grids.region(carta, cfg), scale=30, geometries=True,
        seed=e["seed"], classValues=CLASSES, classPoints=[n] * len(CLASSES), dropNulls=True, tileScale=16)
    return pts.map(lambda f: f.set("range", window, "grid_name", carta, "type", "validation_extra"))


def validation_extra_table_id(carta: str, cfg: dict) -> str:
    return config.asset_path(cfg["evaluation"]["extra_validation"]["folder"], f"validacao_extra_{carta}", cfg=cfg)


def validation_extra_export_spec(carta: str, cfg: dict | None = None):
    cfg = cfg or config.load()
    name = f"validacao_extra_{carta}"
    asset_id = validation_extra_table_id(carta, cfg)
    fc = create_validation_extra(carta, cfg)
    return (name, asset_id, lambda: ee.batch.Export.table.toAsset(
        collection=fc, description=config.task_description(name, cfg), assetId=asset_id))
