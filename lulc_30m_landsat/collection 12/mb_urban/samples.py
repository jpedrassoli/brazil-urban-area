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


def stable_by_year(year: int, cfg: dict | None = None) -> ee.Image:
    """Classe da coleção de referência onde todas as coleções concordam no ano (stableCollectionByYear)."""
    cfg = cfg or config.load()
    s = cfg["samples"]
    band = f"classification_{year}"
    ref = _lulc(s["reference_collection"], cfg).select(band)
    cols = s["stability_collections"]
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
