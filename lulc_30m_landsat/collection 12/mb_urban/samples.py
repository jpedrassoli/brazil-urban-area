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
    """Janelas de anos: {'1985_to_2020': [1985..2020], '1993_to_2020': [...], ...}.

    Com `samples.recent_window` ({start, end, used_from}), acrescenta a janela recente (ex.: 2017_to_2025),
    usada pelos anos >= used_from (veja `classify.window_for_year`)."""
    cfg = cfg or config.load()
    s = cfg["samples"]
    start, end, step = s["window_start"], s["window_end"], s["window_step"]
    out = {}
    i = start + step
    while i <= end:
        years = list(range(i - step, end + 1))
        out[f"{years[0]}_to_{years[-1]}"] = years
        i += step
    r = s.get("recent_window")
    if r:
        out[f"{r['start']}_to_{r['end']}"] = list(range(r["start"], r["end"] + 1))
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


def carta_table_id(carta: str, cfg: dict) -> str:
    return config.asset_path(cfg["samples"]["build_folder"], f"amostras_{carta}", cfg=cfg)


def carta_export_spec(carta: str, cfg: dict | None = None):
    """Tarefa que sorteia as amostras de uma carta (todas as janelas) e separa treino/validação.

    Na Col 11, a tabela final juntava as amostras de todas as cartas; a classificação de uma carta usa
    as amostras da super carta (ela e as vizinhas). Por isso, gere as cartas de interesse E as vizinhas
    (`cartas_for_build`) e depois junte tudo com `merge_export_spec`."""
    cfg = cfg or config.load()
    fc = split_train_validation(ee.FeatureCollection([create(carta, w, cfg) for w in windows(cfg)]).flatten(), cfg)
    name = f"amostras_{carta}"
    asset_id = carta_table_id(carta, cfg)
    # alternativa se faltar tempo/memória (cartas grandes da Amazônia): uma tarefa por janela, mesmo resultado
    alternativa = lambda: [window_export_spec(carta, w, cfg) for w in windows(cfg)]
    return (name, asset_id, lambda: ee.batch.Export.table.toAsset(
        collection=fc, description=config.task_description(name, cfg), assetId=asset_id), alternativa)


def window_table_id(carta: str, window: str, cfg: dict) -> str:
    return config.asset_path(cfg["samples"]["build_folder"], f"amostras_{carta}__{window}", cfg=cfg)


def window_export_spec(carta: str, window: str, cfg: dict):
    """Amostras de uma carta numa janela só (parte da alternativa de `carta_export_spec`).

    O sorteio é o mesmo da tarefa inteira (mesma semente por janela); a separação treino/validação usa
    randomColumn() por janela, como na tarefa inteira."""
    fc = split_train_validation(create(carta, window, cfg), cfg)
    name = f"amostras_{carta}__{window}"
    asset_id = window_table_id(carta, window, cfg)
    return (name, asset_id, lambda: ee.batch.Export.table.toAsset(
        collection=fc, description=config.task_description(name, cfg), assetId=asset_id))


def carta_sources(carta: str, cfg: dict) -> list[str] | None:
    """Tabelas que compõem as amostras da carta: a tabela inteira, ou todas as partes por janela.
    None se ainda não estiver completa."""
    from .tasks import asset_exists
    if asset_exists(carta_table_id(carta, cfg)):
        return [carta_table_id(carta, cfg)]
    parts = [window_table_id(carta, w, cfg) for w in windows(cfg)]
    return parts if all(asset_exists(p) for p in parts) else None


def cartas_for_build(cartas: list[str], cfg: dict | None = None) -> list[str]:
    """As cartas e todas as vizinhas das suas super cartas (cartas cujas amostras entram no treino)."""
    cfg = cfg or config.load()
    field = cfg["grids"]["grid_field"]
    names = ee.FeatureCollection([grids.context_fc(c, cfg) for c in cartas]).flatten().aggregate_array(field)
    return sorted(set(names.getInfo()))


def merge_export_spec(cartas: list[str], cfg: dict | None = None):
    """Tarefa que junta as tabelas por carta na tabela final (`samples.table`)."""
    cfg = cfg or config.load()
    sources = [src for c in cartas for src in (carta_sources(c, cfg) or [])]
    fc = ee.FeatureCollection([ee.FeatureCollection(src) for src in sources]).flatten()
    asset_id = cfg["samples"]["table"]
    name = asset_id.rsplit("/", 1)[-1]
    return (name, asset_id, lambda: ee.batch.Export.table.toAsset(
        collection=fc, description=config.task_description(name, cfg), assetId=asset_id))


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
