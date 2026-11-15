"""Pré-filtro: da probabilidade urbana anual para um mapa binário por ano.

Porte de `Col11/filters/batchFilters.js`, versão de produção da Col 11
(`collection 11/codes_producao/04_pos_processamento/...`, commit 5f5433a7). Para cada ano:

1. média da probabilidade urbana numa janela de ±2 anos (harmonização temporal);
2. média de vizinhança (círculo de 6 pixels), ignorando pixels abaixo de 0,7 × limiar da carta;
3. urbano onde essa média >= 0,9 × limiar da carta;
4. remove urbano onde água, vegetação ou "outros" dominam e a probabilidade urbana é <= 20;
5. até 2023, mantém urbano só onde o índice de infraestrutura (IRS) >= 400.
"""
from __future__ import annotations

import ee

from . import col11, config

PROB_NAMES = ["urban", "veg", "water", "other"]
CLASS_BANDS = ["class1_prob", "class2_prob", "class3_prob", "class4_prob"]


# --- fontes de probabilidade --------------------------------------------------------------------
def _classification_collection(cfg: dict) -> ee.ImageCollection:
    """Probabilidades da versão configurada (`classification.version`): versões diferentes gravadas na
    mesma coleção nunca se misturam."""
    c = cfg["classification"]
    return (ee.ImageCollection(config.asset_path(c["folder"], cfg=cfg))
            .filter(ee.Filter.eq("version", c.get("version", 1))))


def urban_probability(year: int, cfg: dict) -> ee.Image:
    """Probabilidade urbana do ano (0-100), segundo `postprocess.probability_source`."""
    src = cfg["postprocess"]["probability_source"]
    band = f"classification_{year}"
    if src == "col11":
        return col11.urban_probability(year)
    if src != "classification":
        raise ValueError("postprocess.probability_source deve ser 'classification' ou 'col11'")
    col = _classification_collection(cfg)
    if cfg["classification"]["output"] == "multiband":
        img = col.select(f"class1_prob_{year}").mosaic()
    else:
        img = col.filter(ee.Filter.eq("year", year)).select("class1_prob").mosaic()
    return img.toByte().selfMask().rename(band).set("year", year)


def all_probabilities(year: int, cfg: dict) -> ee.Image:
    """As 4 probabilidades do ano, com nomes urban/veg/water/other."""
    if cfg["postprocess"]["probability_source"] == "col11":
        return col11.all_probabilities(year)
    col = _classification_collection(cfg)
    if cfg["classification"]["output"] == "multiband":
        return col.select([f"{b}_{year}" for b in CLASS_BANDS], PROB_NAMES).mosaic()
    return col.filter(ee.Filter.eq("year", year)).select(CLASS_BANDS, PROB_NAMES).mosaic()


# --- etapas --------------------------------------------------------------------------------------
def _threshold(cfg: dict) -> ee.Image:
    return ee.Image(cfg["postprocess"]["threshold_image"]).select("percentil")


def temporal_mean(year: int, cfg: dict) -> ee.Image:
    """Média da probabilidade em ±N anos dentro do intervalo da coleção (temporalHarmonization)."""
    first, last = cfg["years"]
    w = cfg["postprocess"]["temporal_window"]
    yrs = [y for y in range(year - w, year + w + 1) if first <= y <= last]
    imgs = [urban_probability(y, cfg).rename("classification").unmask() for y in yrs]
    return ee.ImageCollection(imgs).reduce(ee.Reducer.mean()).toByte()


def neighborhood(image: ee.Image, cfg: dict) -> ee.Image:
    p = cfg["postprocess"]
    masked = image.updateMask(image.gte(_threshold(cfg).multiply(p["neighborhood_factor"])))
    return (masked.reduceNeighborhood(reducer=ee.Reducer.mean(), kernel=ee.Kernel.circle(p["kernel_radius_px"]))
            .reproject("EPSG:4326", None, 30))


def apply(year: int, cfg: dict | None = None) -> ee.Image:
    """Mapa binário pré-filtrado do ano (1 urbano; 0 ou mascarado não urbano)."""
    cfg = cfg or config.load()
    p = cfg["postprocess"]
    r = p["rules"]
    urban = neighborhood(temporal_mean(year, cfg), cfg).gte(_threshold(cfg).multiply(p["final_factor"]))
    probs = all_probabilities(year, cfg)
    weak = probs.select("urban").lte(r["urban_max"])
    out = (urban
           .where(probs.select("water").gte(r["water_min"]).And(weak), 0)
           .where(probs.select("veg").gte(r["veg_min"]).And(weak), 0)
           .where(probs.select("other").gte(r["other_min"]).And(weak), 0)
           .selfMask())
    if year <= p["irs_last_year"]:
        irs = ee.ImageCollection(p["irs_asset"]).sum()
        out = out.multiply(irs.gte(p["irs_min"]))
    return out.rename(f"classification_{year}")
