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


def _validation_points(carta: str, cfg: dict) -> ee.FeatureCollection:
    """Amostras de validação da carta + pontos extras do início da série, se já tiverem sido gerados."""
    from . import tasks
    region = grids.region(carta, cfg)
    val = samples.table(cfg).filter(ee.Filter.eq("type", "validation")).filterBounds(region)
    if cfg.get("thresholds", {}).get("calibration_split"):     # (1) em teste: a outra metade calibrou o limiar
        val = val.filter(ee.Filter.gt("random", 0.9))
    indep = cfg.get("evaluation", {}).get("independent_points")
    if indep:                                                  # (7) em teste: pontos independentes (ex.: visuais)
        val = val.merge(ee.FeatureCollection(indep).filterBounds(region))
    extra_id = samples.validation_extra_table_id(carta, cfg)
    if tasks.asset_exists(extra_id):
        val = val.merge(ee.FeatureCollection(extra_id))
    return val


def _sample_values(image: ee.Image, carta: str, cfg: dict) -> pd.DataFrame:
    years = config.years(cfg)
    bands = [f"classification_{y}" for y in years]
    pts = image.select(bands).sampleRegions(collection=_validation_points(carta, cfg),
                                            properties=["class", "range", "type"], scale=30, tileScale=8)
    df = pd.DataFrame([f["properties"] for f in pts.getInfo()["features"]])
    if not df.empty:
        df["ref"] = (df["class"] == 1).astype(int)
        df["id"] = range(len(df))
    return df


def _metrics(pred: pd.Series, ref: pd.Series) -> dict:
    tp = int(((pred == 1) & (ref == 1)).sum()); fp = int(((pred == 1) & (ref == 0)).sum())
    fn = int(((pred == 0) & (ref == 1)).sum()); tn = int(((pred == 0) & (ref == 0)).sum())
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
    return {"acuracia_global": (tp + tn) / len(pred) if len(pred) else None,
            "precisao_urbano": prec, "recall_urbano": rec, "f1_urbano": f1}


def _wilson(p: float | None, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """Intervalo de confiança de 95% (Wilson) para uma proporção."""
    if p is None or n == 0:
        return None, None
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    meia = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return centro - meia, centro + meia


def accuracy(image: ee.Image, carta: str, cfg: dict, df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Acurácia por ano. Cada amostra vale para os anos da sua janela de estabilidade."""
    df = _sample_values(image, carta, cfg) if df is None else df
    rows = []
    if df.empty:
        return pd.DataFrame(columns=["carta", "ano", "n", "n_urbano", "acuracia_global",
                                     "precisao_urbano", "recall_urbano", "f1_urbano"])
    for y in config.years(cfg):
        sel = df[df["range"].map(lambda r: y in _window_years(r))]
        if sel.empty:
            continue
        rows.append({"carta": carta, "ano": y, "n": len(sel), "n_urbano": int(sel["ref"].sum()),
                     **_metrics(sel[f"classification_{y}"].astype(int), sel["ref"])})
    return pd.DataFrame(rows)


def accuracy_by_period(image: ee.Image, carta: str, cfg: dict, df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Acurácia agregada por período, com intervalo de confiança de 95%.

    Junta todos os pares (amostra, ano) do período; o intervalo usa o número de AMOSTRAS distintas
    (não de pares), para não superestimar a confiança — a mesma amostra se repete em vários anos.
    """
    df = _sample_values(image, carta, cfg) if df is None else df
    rows = []
    for a, b in cfg["evaluation"]["periods"]:
        pares = []
        for y in range(a, b + 1):
            if f"classification_{y}" not in df:
                continue
            sel = df[df["range"].map(lambda r: y in _window_years(r))]
            pares.append(pd.DataFrame({"id": sel["id"], "pred": sel[f"classification_{y}"].astype(int), "ref": sel["ref"]}))
        if not pares:
            continue
        p = pd.concat(pares)
        n_amostras = p["id"].nunique()
        n_urb = p.loc[p["ref"] == 1, "id"].nunique()
        m = _metrics(p["pred"], p["ref"])
        lo, hi = _wilson(m["acuracia_global"], n_amostras)
        rlo, rhi = _wilson(m["recall_urbano"], n_urb)
        rows.append({"carta": carta, "periodo": f"{a}-{b}", "amostras": n_amostras, "amostras_urbanas": n_urb,
                     **m, "acuracia_ic95": (lo, hi), "recall_urbano_ic95": (rlo, rhi)})
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


def reference_map(carta: str, cfg: dict) -> ee.Image:
    """Mapa de referência para comparação (config `evaluation.reference`):
    - "col11": mapa final da Col 11 (assets internos da equipe);
    - "mapbiomas_publico": classe de área urbanizada (24) da coleção integrada pública do MapBiomas,
      acessível a qualquer pessoa. Anos fora da coleção ficam sem dado."""
    e = cfg["evaluation"]
    ref = e.get("reference", "col11")
    if ref == "col11":
        return col11.final_map(carta, e["final_col11_version"].split("_")[1])
    if ref != "mapbiomas_publico":
        raise ValueError("evaluation.reference deve ser 'col11' ou 'mapbiomas_publico'")
    pub = e["public_reference"]
    lulc = ee.Image(pub["asset"])
    first, last = pub["years"]
    bands = []
    for y in config.years(cfg):
        b = f"classification_{y}"
        bands.append(lulc.select(b).eq(pub.get("urban_class", 24)).rename(b) if first <= y <= last
                     else ee.Image(0).selfMask().rename(b))
    return ee.Image.cat(bands)


def evaluate_carta(carta: str, cfg: dict | None = None, image: ee.Image | None = None, suffix: str = "") -> dict:
    """Todas as métricas de uma carta. `image` padrão: o mapa final da rodada no destino.
    As colunas com sufixo "col11" referem-se ao mapa de referência (`evaluation.reference`)."""
    cfg = cfg or config.load()
    image = image if image is not None else map_asset(carta, cfg, suffix)
    ref = reference_map(carta, cfg)
    area = pd.DataFrame({"col12": urban_area(image, carta, cfg), "col11": urban_area(ref, carta, cfg)})
    area["dif_km2"] = area["col12"] - area["col11"]
    df, df11 = _sample_values(image, carta, cfg), _sample_values(ref, carta, cfg)
    return {"carta": carta, "acuracia": accuracy(image, carta, cfg, df),
            "acuracia_col11": accuracy(ref, carta, cfg, df11),
            "acuracia_periodo": accuracy_by_period(image, carta, cfg, df),
            "acuracia_periodo_col11": accuracy_by_period(ref, carta, cfg, df11),
            "area": area, "concordancia_col11": agreement(image, ref, carta, cfg)}


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
                  "<h3>Acurácia por período (Col 12), IC 95%</h3>", r["acuracia_periodo"].round(3).to_html(index=False),
                  "<h3>Acurácia por período (Col 11), IC 95%</h3>", r["acuracia_periodo_col11"].round(3).to_html(index=False),
                  "<h3>Acurácia por ano (Col 12)</h3>", r["acuracia"].round(3).to_html(index=False)]
    path = REPORT_DIR / f"avaliacao_{now:%Y%m%d_%H%M}.html"
    path.write_text("<html><meta charset='utf-8'><body>" + "\n".join(parts) + "</body></html>", encoding="utf-8")
    return path


# --- pontos externos de validação (conjunto independente do MapBiomas) --------------------------------------
# Os pontos do conjunto de 100 mil (interpretação visual, uma classe por ponto e por ano) são independentes das
# amostras estáveis usadas no treino. A acurácia oficial do mapa usa esse conjunto. Cobre 1985-2018 e tem poucos
# pontos urbanos por carta: use os resultados agrupados (várias cartas), não por carta.
EXTERNAL_DEFAULT = {
    "asset": "projects/mapbiomas-workspace/VALIDACAO/MAPBIOMAS_100K_POINTS_utf8",
    "urban_label": "Infraestrutura Urbana",
    "weight_property": "PESO_AMOS",       # peso amostral de cada ponto (desenho estratificado)
    "years": [1985, 2018],
}


def _external_cfg(cfg: dict) -> dict:
    return {**EXTERNAL_DEFAULT, **(cfg.get("evaluation", {}).get("external_points") or {})}


def external_values(image: ee.Image, carta: str, cfg: dict, tolerance_px: int = 0) -> pd.DataFrame:
    """Mapa e referência nos pontos externos que caem na carta: uma linha por ponto e ano.

    `tolerance_px` > 0 acrescenta a coluna `pred_tol`, a leitura com tolerância posicional: o ponto pode estar
    deslocado até `tolerance_px` pixels (vizinhança quadrada). Num ponto urbano da referência vale urbano se
    ALGUM pixel vizinho for urbano no mapa; num ponto não urbano vale não urbano se ALGUM vizinho for não urbano.
    É simétrica (não dilata o mapa): corrige só a incerteza de posição, e vale para qualquer mapa."""
    e = _external_cfg(cfg)
    first, last = e["years"]
    years = [y for y in config.years(cfg) if first <= y <= last]
    bands = [f"classification_{y}" for y in years]
    props = [f"CLASS_{y}" for y in years] + [e["weight_property"], "TARGET_FID"]
    pts = ee.FeatureCollection(e["asset"]).filterBounds(grids.region(carta, cfg))
    img = image.select(bands)
    if tolerance_px:
        mx = img.focalMax(tolerance_px, "square", "pixels").rename([f"mx_{b}" for b in bands])
        mn = img.focalMin(tolerance_px, "square", "pixels").rename([f"mn_{b}" for b in bands])
        img = img.addBands(mx).addBands(mn)
    got = img.sampleRegions(collection=pts, properties=props, scale=30, tileScale=8,
                            geometries=True).getInfo()
    rows = []
    for i, f in enumerate(got["features"]):
        p = f["properties"]
        try:
            w = float(p.get(e["weight_property"]) or 1)
        except ValueError:
            w = 1.0
        lon, lat = (f.get("geometry") or {}).get("coordinates", [None, None])
        for y in years:
            ref = int(p.get(f"CLASS_{y}") == e["urban_label"])
            row = {"carta": carta, "ponto": i, "id_ponto": p.get("TARGET_FID"), "lon": lon, "lat": lat,
                   "ano": y, "pred": int(p[f"classification_{y}"]), "ref": ref, "peso": w}
            if tolerance_px:
                row["pred_tol"] = int(p[f"mx_classification_{y}"]) if ref else int(p[f"mn_classification_{y}"])
            rows.append(row)
    cols = ["carta", "ponto", "id_ponto", "lon", "lat", "ano", "pred", "ref", "peso"] + (["pred_tol"] if tolerance_px else [])
    return pd.DataFrame(rows, columns=cols)


def _metrics_weighted(d: pd.DataFrame) -> dict:
    def s(mask):
        return float(d.loc[mask, "peso"].sum())
    tp, fp = s((d.pred == 1) & (d.ref == 1)), s((d.pred == 1) & (d.ref == 0))
    fn, tn = s((d.pred == 0) & (d.ref == 1)), s((d.pred == 0) & (d.ref == 0))
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
    tot = tp + fp + fn + tn
    return {"acuracia_ponderada": (tp + tn) / tot if tot else None, "precisao_urbano_pond": prec,
            "recall_urbano_pond": rec, "f1_urbano_pond": f1}


def external_accuracy(values: pd.DataFrame, cfg: dict, label: str = "", pred_col: str = "pred") -> pd.DataFrame:
    """Acurácia por período nos pontos externos, agrupando todas as cartas de `values`.
    Traz as métricas sem peso e com o peso amostral, e o IC 95% (Wilson) pelo número de PONTOS distintos."""
    first, last = _external_cfg(cfg)["years"]
    rows = []
    for a, b in cfg["evaluation"]["periods"]:
        a, b = max(a, first), min(b, last)
        if a > b or values.empty:
            continue
        d = values[(values.ano >= a) & (values.ano <= b)]
        if d.empty:
            continue
        ids = d[["carta", "ponto"]].drop_duplicates()
        urb = d.loc[d.ref == 1, ["carta", "ponto"]].drop_duplicates()
        d = d.assign(pred=d[pred_col])
        m = _metrics(d["pred"], d["ref"])
        lo, hi = _wilson(m["acuracia_global"], len(ids))
        rlo, rhi = _wilson(m["recall_urbano"], len(urb))
        rows.append({"mapa": label, "periodo": f"{a}-{b}", "pontos": len(ids), "pontos_urbanos": len(urb),
                     **m, "acuracia_ic95": (lo, hi), "recall_urbano_ic95": (rlo, rhi), **_metrics_weighted(d)})
    return pd.DataFrame(rows)


def evaluate_external(cartas: list[str], cfg: dict | None = None, suffix: str = "", tolerance_px: int = 0) -> dict:
    """Compara o mapa da Col 12 e o de referência (Col 11) nos pontos externos das cartas dadas.
    Com `tolerance_px` > 0, devolve também a acurácia com tolerância posicional (linhas "(tol N px)").
    Devolve {"col12": valores, "col11": valores, "acuracia": tabela agrupada, "pontos_por_carta": tabela}."""
    cfg = cfg or config.load()
    v12 = pd.concat([external_values(map_asset(c, cfg, suffix), c, cfg, tolerance_px) for c in cartas], ignore_index=True)
    v11 = pd.concat([external_values(reference_map(c, cfg), c, cfg, tolerance_px) for c in cartas], ignore_index=True)
    parts = [external_accuracy(v12, cfg, "Col 12"), external_accuracy(v11, cfg, "Col 11")]
    if tolerance_px:
        parts += [external_accuracy(v12, cfg, f"Col 12 (tol {tolerance_px} px)", "pred_tol"),
                  external_accuracy(v11, cfg, f"Col 11 (tol {tolerance_px} px)", "pred_tol")]
    acc = pd.concat(parts, ignore_index=True)
    n = (v12.groupby("carta").agg(pontos=("ponto", "nunique"))
         .join(v12[v12.ref == 1].groupby("carta").agg(pontos_urbanos_algum_ano=("ponto", "nunique"))).fillna(0))
    return {"col12": v12, "col11": v11, "acuracia": acc, "pontos_por_carta": n}


# --- métricas por carta, para registrar no próprio mapa e montar mapas regionais de acurácia ----------------
def carta_metrics(carta: str, result: dict, v12: pd.DataFrame, v11: pd.DataFrame, cfg: dict) -> dict:
    """Achata as métricas de UMA carta num dicionário de campos simples (texto/número), pronto para virar
    propriedades do asset ou uma linha de tabela. Prefixos: `int_` (amostras estáveis internas) e `ext_`
    (pontos externos do MapBiomas); depois `col12`/`col11`, o período e a métrica. Nunca guarda valor ausente.
    Os pontos externos de uma carta são poucos: sempre confira `ext_n_pts` e `ext_n_urb` antes de mapear."""
    out: dict = {"eval_carta": carta, "eval_data": dt.datetime.now().strftime("%Y-%m-%d"),
                 "eval_code_version": config.code_version(), "eval_config_sha256": config.config_hash(cfg)}

    def put(key, val):
        if val is not None and val == val:                     # descarta None e NaN
            out[key] = round(float(val), 4) if isinstance(val, float) else val

    for versao, per in (("col12", result["acuracia_periodo"]), ("col11", result["acuracia_periodo_col11"])):
        for _, r in per.iterrows():
            tag = f"int_{versao}_{r['periodo'].replace('-', '_')}"
            for m in ("acuracia_global", "precisao_urbano", "recall_urbano", "f1_urbano"):
                put(f"{tag}_{m}", r[m])
            put(f"{tag}_n_amostras", int(r["amostras"]))
            put(f"{tag}_n_urb", int(r["amostras_urbanas"]))
    for versao, vals in (("col12", v12), ("col11", v11)):
        for prefixo, col in (("ext", "pred"), ("exttol", "pred_tol")):
            if col not in vals.columns:
                continue
            acc = external_accuracy(vals[vals.carta == carta], cfg, versao, col)
            for _, r in acc.iterrows():
                tag = f"{prefixo}_{versao}_{r['periodo'].replace('-', '_')}"
                for m in ("acuracia_global", "precisao_urbano", "recall_urbano", "f1_urbano", "acuracia_ponderada"):
                    put(f"{tag}_{m}", r[m])
                put(f"{tag}_n_pts", int(r["pontos"]))
                put(f"{tag}_n_urb", int(r["pontos_urbanos"]))
    ar = result["area"]
    last = int(ar.index.max())
    put(f"area_{last}_col12_km2", float(ar.loc[last, "col12"]))
    put(f"area_{last}_col11_km2", float(ar.loc[last, "col11"]))
    put("concordancia_media_col11", float(result["concordancia_col11"].mean()))
    return out


def write_properties(carta: str, metrics: dict, cfg: dict, suffix: str = "") -> None:
    """Grava as métricas como propriedades do mapa final da carta (ESCREVE no Earth Engine: só acrescenta ou
    atualiza essas propriedades, não mexe nos pixels). Use depois de `carta_metrics`."""
    ee.data.setAssetProperties(config.asset_path(cfg["postprocess"]["folder"], f"mapa_{carta}{suffix}", cfg=cfg),
                               {k: v for k, v in metrics.items()})
