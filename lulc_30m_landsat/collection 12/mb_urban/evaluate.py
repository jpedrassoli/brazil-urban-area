"""Avaliação de uma rodada: acurácia, área urbana e comparação com a Coleção 11, por carta.

- Acurácia: usa as amostras de VALIDAÇÃO (type = validation, 20% que não entram no treino). Cada
  amostra vale para os anos da sua janela de estabilidade (ex.: 2009_to_2020 → 2009 a 2020),
  porque ela foi sorteada onde a classe não mudou nesse período. Como são áreas estáveis, a acurácia
  tende a ser otimista em relação às áreas de transição.
- Área: km² de urbano por ano dentro da região da carta (hexágono).
- Comparação com a Col 11: área por ano e concordância pixel a pixel, na mesma região.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import ee
import pandas as pd

from . import col11, config, grids, samples

REPORT_DIR = config.PACKAGE_ROOT / "logs" / "relatorios"


def map_asset(carta: str, cfg: dict, suffix: str = "") -> ee.Image:
    p = cfg["postprocess"]
    return ee.Image(config.asset_path(p["folder"], f"mapa_{carta}{suffix}", cfg=cfg))


def _window_years(window: str) -> list[int]:
    a, b = window.split("_to_")
    return list(range(int(a), int(b) + 1))


def accuracy(image: ee.Image, carta: str, cfg: dict) -> pd.DataFrame:
    """Acurácia por ano com as amostras de validação dentro da carta."""
    years = config.years(cfg)
    val = samples.table(cfg).filter(ee.Filter.eq("type", "validation")).filterBounds(grids.region(carta, cfg))
    bands = [f"classification_{y}" for y in years]
    pts = image.select(bands).sampleRegions(collection=val, properties=["class", "range"], scale=30, tileScale=8)
    feats = pd.DataFrame([f["properties"] for f in pts.getInfo()["features"]])
    rows = []
    if feats.empty:
        return pd.DataFrame(columns=["carta", "ano", "n", "acuracia_global", "precisao_urbano", "recall_urbano", "f1_urbano"])
    feats["ref"] = (feats["class"] == 1).astype(int)
    for y in years:
        sel = feats[feats["range"].map(lambda r: y in _window_years(r))]
        if sel.empty:
            continue
        pred, ref = sel[f"classification_{y}"].astype(int), sel["ref"]
        tp = int(((pred == 1) & (ref == 1)).sum()); fp = int(((pred == 1) & (ref == 0)).sum())
        fn = int(((pred == 0) & (ref == 1)).sum()); tn = int(((pred == 0) & (ref == 0)).sum())
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
        rows.append({"carta": carta, "ano": y, "n": len(sel), "n_urbano": int(ref.sum()),
                     "acuracia_global": (tp + tn) / len(sel), "precisao_urbano": prec,
                     "recall_urbano": rec, "f1_urbano": f1})
    return pd.DataFrame(rows)


def urban_area(image: ee.Image, carta: str, cfg: dict) -> pd.Series:
    """Área urbana (km²) por ano na região da carta."""
    years = config.years(cfg)
    bands = [f"classification_{y}" for y in years]
    res = (image.select(bands).eq(1).multiply(ee.Image.pixelArea()).divide(1e6)
           .reduceRegion(ee.Reducer.sum(), grids.region(carta, cfg), cfg["evaluation"]["area_scale_m"],
                         maxPixels=1e11, tileScale=8).getInfo())
    return pd.Series({int(k[-4:]): v for k, v in res.items()}).sort_index()


def agreement(image: ee.Image, reference: ee.Image, carta: str, cfg: dict) -> pd.Series:
    """Fração de pixels iguais por ano na região da carta."""
    years = config.years(cfg)
    bands = [f"classification_{y}" for y in years]
    res = (image.select(bands).eq(reference.select(bands))
           .reduceRegion(ee.Reducer.mean(), grids.region(carta, cfg), 30, maxPixels=1e11, tileScale=8).getInfo())
    return pd.Series({int(k[-4:]): v for k, v in res.items()}).sort_index()


def evaluate_carta(carta: str, cfg: dict | None = None, image: ee.Image | None = None, suffix: str = "") -> dict:
    """Todas as métricas de uma carta. `image` padrão: o mapa final da rodada no destino."""
    cfg = cfg or config.load()
    image = image if image is not None else map_asset(carta, cfg, suffix)
    ref = col11.final_map(carta, cfg["evaluation"]["final_col11_version"].split("_")[1])
    area = pd.DataFrame({"col12": urban_area(image, carta, cfg), "col11": urban_area(ref, carta, cfg)})
    area["dif_km2"] = area["col12"] - area["col11"]
    return {"carta": carta, "acuracia": accuracy(image, carta, cfg),
            "acuracia_col11": accuracy(ref, carta, cfg), "area": area,
            "concordancia_col11": agreement(image, ref, carta, cfg)}


def summary(results: list[dict]) -> pd.DataFrame:
    """Uma linha por carta: médias de acurácia (Col 12 e Col 11), áreas e concordância."""
    rows = []
    for r in results:
        a, a11, ar = r["acuracia"], r["acuracia_col11"], r["area"]
        last = ar.index.max()
        rows.append({
            "carta": r["carta"],
            "f1_urbano_col12": a["f1_urbano"].mean() if not a.empty else None,
            "f1_urbano_col11": a11["f1_urbano"].mean() if not a11.empty else None,
            "acuracia_col12": a["acuracia_global"].mean() if not a.empty else None,
            "acuracia_col11": a11["acuracia_global"].mean() if not a11.empty else None,
            f"area_{last}_col12_km2": ar.loc[last, "col12"], f"area_{last}_col11_km2": ar.loc[last, "col11"],
            "concordancia_media_col11": r["concordancia_col11"].mean(),
        })
    return pd.DataFrame(rows)


def html_report(results: list[dict], cfg: dict, title: str = "Avaliação da rodada") -> Path:
    """Relatório HTML simples (tabelas) salvo em logs/relatorios/. Não é publicado automaticamente."""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now()
    parts = [f"<h1>{title}</h1>",
             f"<p>{now:%Y-%m-%d %H:%M} · código {config.code_version()} · escopo {cfg.get('scope')}</p>",
             "<h2>Resumo por carta</h2>", summary(results).round(3).to_html(index=False)]
    for r in results:
        parts += [f"<h2>{r['carta']} — {cfg.get('cartas_teste', {}).get(r['carta'], '')}</h2>",
                  "<h3>Área urbana (km²)</h3>", r["area"].round(1).to_html(),
                  "<h3>Acurácia (Col 12)</h3>", r["acuracia"].round(3).to_html(index=False)]
    path = REPORT_DIR / f"avaliacao_{now:%Y%m%d_%H%M}.html"
    path.write_text("<html><meta charset='utf-8'><body>" + "\n".join(parts) + "</body></html>", encoding="utf-8")
    return path
