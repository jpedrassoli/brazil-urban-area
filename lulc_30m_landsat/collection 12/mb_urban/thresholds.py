"""Limiar ótimo de probabilidade urbana por carta (a imagem `postprocess.threshold_image`).

Porte da cadeia da Col 10/11 (versões publicadas em `collection 11/codes/` e de produção em
`collection 11/codes_producao/03_limiares/`):

1. `bestProb_preProcessingByGridByYear.js`: valor da probabilidade urbana em pontos de validação
   (urbanos e não urbanos) da super carta, para cada ano;
2. `accPreProcessingThreshold.ipynb` (só a versão da Col 10 foi publicada): para cada carta e ano,
   - `threshold`: limiar que maximiza o índice J de Youden (sensibilidade + especificidade - 1) na curva ROC;
   - `cutPercentile`: percentil 15 da probabilidade nos pontos urbanos × 0,95;
   lacunas de `threshold` preenchidas com `cutPercentile / 1,25`;
3. agregação por carta: média na Col 10; **mediana** na Col 11, com p10, p90, anos disponíveis e
   completude (campos da tabela `col11/thresholdMedianByCarta`); cartas sem dados recebem a mediana nacional;
4. `meanThresholdsByGridAsImage.js` (produção da Col 11): imagem com as bandas `percentil` e `threshold`.
   O pré-filtro da Col 11 usa a banda `percentil`.

O que a versão da Col 11 do notebook fazia além disso não é conhecido (lacuna da auditoria); a
conferência é reproduzir a tabela da Col 11 a partir das probabilidades da Col 11.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import ee

from . import config, grids, prefilter, samples

DEFAULTS = {
    "folder": "limiares",
    "version": 1,
    "probability": "raw",          # raw = probabilidade do ano; temporal_mean = média ±N anos do pré-filtro
    "validation": "table",         # table = amostras de validação da tabela de amostras (janela do ano)
    "urban_points": 220,           # por super carta e ano (Col 10: 220)
    "balance": 2,                  # não urbanos = urban_points × balance (Col 10: 2)
    "percentile": 0.15,            # cutPercentile = quantil 15% dos urbanos × factor
    "percentile_factor": 0.95,
    "fill_divisor": 1.25,          # threshold ausente = cutPercentile / 1,25
    "aggregate": "median",         # median (Col 11) ou mean (Col 10)
}


def _cfg(cfg: dict) -> dict:
    return {**DEFAULTS, **cfg.get("thresholds", {})}


# --- 1. valores nos pontos de validação (Earth Engine) --------------------------------------------
def _probability(year: int, cfg: dict) -> ee.Image:
    t = _cfg(cfg)
    if t["probability"] == "temporal_mean":
        return prefilter.temporal_mean(year, cfg).rename("classification")
    return prefilter.urban_probability(year, cfg).unmask(0).rename("classification")


def _validation_points(year: int, context: ee.Geometry, cfg: dict) -> ee.FeatureCollection:
    from .classify import window_for_year
    t = _cfg(cfg)
    if t["validation"] != "table":
        raise ValueError("thresholds.validation: só 'table' está implementado")
    val = (samples.table(cfg).filter(ee.Filter.eq("range", window_for_year(year, cfg)))
           .filter(ee.Filter.eq("type", "validation")).filterBounds(context))
    n = t["urban_points"]
    urb = val.filter(ee.Filter.eq("class", 1)).sort("random").limit(n)
    other = val.filter(ee.Filter.neq("class", 1)).sort("random").limit(n * t["balance"])
    return urb.merge(other).map(lambda f: f.set("value", ee.Number(f.get("class")).eq(1)))


def values_fc(carta: str, cfg: dict, years: list[int] | None = None) -> ee.FeatureCollection:
    """Probabilidade urbana (`classification`) e rótulo (`value`, 1 urbano) nos pontos, por ano."""
    years = years or config.years(cfg)
    context = grids.context_fc(carta, cfg).geometry().bounds(10)
    parts = [_probability(y, cfg).sampleRegions(collection=_validation_points(y, context, cfg),
                                                 properties=["value"], scale=30, tileScale=16)
             .map(lambda f, y=y: f.set("year", y)) for y in years]
    return ee.FeatureCollection(parts).flatten().select(["classification", "value", "year"])


def values_table_id(carta: str, cfg: dict) -> str:
    t = _cfg(cfg)
    return config.asset_path(t["folder"], f"v{t['version']}_valores", f"valores_{carta}", cfg=cfg)


def values_export_spec(carta: str, cfg: dict | None = None):
    cfg = cfg or config.load()
    name = f"limiar_valores_{carta}"
    asset_id = values_table_id(carta, cfg)
    fc = values_fc(carta, cfg)
    return (name, asset_id, lambda: ee.batch.Export.table.toAsset(
        collection=fc, description=config.task_description(name, cfg), assetId=asset_id))


def read_values(carta: str, cfg: dict) -> pd.DataFrame:
    df = ee.data.computeFeatures({"expression": ee.FeatureCollection(values_table_id(carta, cfg)),
                                  "fileFormat": "PANDAS_DATAFRAME"})
    return df[["classification", "value", "year"]].assign(carta=carta)


# --- 2. limiar por carta e ano (local) ----------------------------------------------------------
def _roc(y_true: np.ndarray, score: np.ndarray):
    """Curva ROC como sklearn.metrics.roc_curve (drop_intermediate=True não importa para o máximo de J)."""
    order = np.argsort(-score, kind="mergesort")
    s, y = score[order], y_true[order]
    distinct = np.r_[np.where(np.diff(s))[0], len(s) - 1]
    tps = np.cumsum(y)[distinct]
    fps = (1 + distinct) - tps
    thr = s[distinct]
    tpr = np.r_[0, tps / max(tps[-1], 1)]
    fpr = np.r_[0, fps / max(fps[-1], 1)]
    return fpr, tpr, np.r_[np.inf, thr]


def by_year(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Limiar de Youden, cutPercentile, AUC e acurácias por carta e ano."""
    t = _cfg(cfg)
    rows = []
    for (carta, year), d in df.groupby(["carta", "year"]):
        y, s = d["value"].to_numpy().astype(int), d["classification"].to_numpy().astype(float)
        urb = s[y == 1]
        cut = np.quantile(urb, t["percentile"]) * t["percentile_factor"] if len(urb) else np.nan
        thr = auc = sens = spec = oa = np.nan
        if 0 < y.sum() < len(y):
            fpr, tpr, th = _roc(y, s)
            auc = float(np.trapz(tpr, fpr))
            thr = float(th[np.argmax(tpr - fpr)])
            pred = s >= thr
            sens = (pred & (y == 1)).sum() / (y == 1).sum()
            spec = (~pred & (y == 0)).sum() / (y == 0).sum()
            oa = (pred == (y == 1)).mean()
        rows.append({"carta": carta, "year": year, "n": len(y), "n_urban": int(y.sum()), "auc": auc,
                     "threshold": thr, "sensitivity": sens, "specificity": spec, "oa": oa, "cutPercentile": cut})
    out = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan)
    out["threshold"] = out["threshold"].fillna((out["cutPercentile"] / t["fill_divisor"]).round(0))
    return out


def by_carta(yearly: pd.DataFrame, cartas: list[str], cfg: dict) -> pd.DataFrame:
    """Agregação por carta, com os campos da tabela da Col 11."""
    t = _cfg(cfg)
    n_years = len(config.years(cfg))
    agg = t["aggregate"]
    rows = []
    for carta in cartas:
        d = yearly[yearly["carta"] == carta].dropna(subset=["threshold", "cutPercentile"], how="all")
        r = {"carta": carta, "n_years_available": int(d["year"].nunique()),
             "data_completeness": round(100 * d["year"].nunique() / n_years, 1)}
        for col in ("threshold", "cutPercentile"):
            v = d[col].dropna()
            r[col] = (v.median() if agg == "median" else v.mean()) if len(v) else np.nan
            r[f"{col}_p10"] = v.quantile(0.1) if len(v) else np.nan
            r[f"{col}_p90"] = v.quantile(0.9) if len(v) else np.nan
        rows.append(r)
    out = pd.DataFrame(rows)
    for col in ("threshold", "cutPercentile"):            # sem dados: mediana nacional
        out[col] = out[col].fillna(out[col].median())
    return out.round(1)


# --- 3. imagem -----------------------------------------------------------------------------------
def image_id(cfg: dict) -> str:
    t = _cfg(cfg)
    return config.asset_path(t["folder"], f"limiares_v{t['version']}", cfg=cfg)


def image_export_spec(table: pd.DataFrame, cfg: dict | None = None):
    """Imagem com as bandas `percentil` e `threshold` (meanThresholdsByGridAsImage)."""
    cfg = cfg or config.load()
    field = cfg["grids"]["grid_field"]
    cartas = grids.cartas_fc(cfg)
    feats = [ee.Feature(cartas.filter(ee.Filter.eq(field, r.carta)).first())
             .set("threshold", float(r.threshold), "percentil", float(r.cutPercentile))
             for r in table.itertuples()]
    fc = ee.FeatureCollection(feats)
    img = (fc.reduceToImage(["percentil"], ee.Reducer.first()).toByte().rename("percentil")
           .addBands(fc.reduceToImage(["threshold"], ee.Reducer.first()).toByte().rename("threshold")))
    t = _cfg(cfg)
    img = img.set({"collection_id": cfg["collection"], "theme": "Urban Area", "product_type": "threshold",
                   "version": t["version"], "probability": t["probability"], "aggregate": t["aggregate"],
                   "code_version": config.code_version()})
    asset_id = image_id(cfg)
    name = asset_id.rsplit("/", 1)[-1]
    return (name, asset_id, lambda: ee.batch.Export.image.toAsset(
        image=img, description=config.task_description(name, cfg), assetId=asset_id,
        region=fc.geometry().bounds(), scale=30, crs="EPSG:4326", maxPixels=1e13))


def col11_table() -> pd.DataFrame:
    """Tabela de limiares da Col 11 (para conferência)."""
    fc = ee.FeatureCollection("projects/ee-ers/assets/mapbiomas/col11/thresholdMedianByCarta")
    return ee.data.computeFeatures({"expression": fc, "fileFormat": "PANDAS_DATAFRAME"}).drop(columns=["geo"], errors="ignore")
