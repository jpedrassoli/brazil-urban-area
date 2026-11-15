"""Filtros temporais e espaciais sobre a série binária pré-filtrada.

Porte de `Col11/filters/spatialAndTemporalFilters.js`, versão de produção da Col 11
(`collection 11/codes_producao/04_pos_processamento/...`, commit 87fe224c), versão C11_v6_SF:

A. Preenchimento de lacunas: sem efeito (a série não tem pixels sem dado) — não aplicado.
B. Remove urbano isolado no tempo: urbano que aparece 1 vez numa janela de 5 anos vira não urbano
   (2025 não é filtrado).
C. Ponto de quebra: a partir do primeiro ano de transição para urbano que se sustenta (>= 50% dos anos
   restantes e >= min(5, anos restantes) anos urbanos), o pixel fica urbano até o fim da série.
D. Filtro espacial: máscara espacial; buracos < 280 px viram urbano; manchas < 10 px são removidas.

A ordem das janelas e das etapas reproduz exatamente a do script de produção.
"""
from __future__ import annotations

import ee

from . import config, prefilter


def raw_series(cfg: dict) -> dict[int, ee.Image]:
    """Série binária pré-filtrada, 0/1 sem máscara (SEÇÃO 0 e 8 do script de produção)."""
    return {y: prefilter.apply(y, cfg).rename("class").unmask(0) for y in config.years(cfg)}


def _tf5_unique(col: dict[int, ee.Image], years: list[int], offsets: list[int]) -> dict[int, ee.Image]:
    """TempFilter_wMask_5yearsunique: zera o urbano que é único na janela [ano + offsets]."""
    out = dict(col)
    for y in years:
        total = ee.ImageCollection([col[y]] + [col[y + o] for o in offsets if y + o in col]).sum()
        unique = col[y].multiply(total.eq(1).unmask())
        out[y] = col[y].where(unique.eq(1), 0)
    return out


def temporal_unique(col: dict[int, ee.Image], cfg: dict) -> dict[int, ee.Image]:
    first, last = cfg["years"]
    c = col                                                        # último ano: sem filtro
    c = _tf5_unique(c, [last - 1], [1, -1, -2, -3])
    c = _tf5_unique(c, list(range(last - 2, first, -1)), [2, 1, -1, -2])
    c = _tf5_unique(c, [first + 1], [-1, 1, 2, 3])
    c = _tf5_unique(c, [first], [1, 2, 3, 4])
    return c


def breakpoint(col: dict[int, ee.Image], cfg: dict) -> dict[int, ee.Image]:
    """Ponto de quebra + acúmulo para frente (getBreakpoints + accumulateForward)."""
    p = cfg["postprocess"]
    first, last = cfg["years"]
    years = config.years(cfg)
    acc = None
    out = {}
    for y in years:
        trans = col[y] if y == first else col[y].subtract(col[y - 1]).eq(1)
        remaining = last - y + 1
        urb_to_end = ee.ImageCollection([col[t] for t in years if t >= y]).sum()
        urb_to_end = trans.multiply(0).where(trans.eq(1), urb_to_end)
        bp = (trans.eq(1)
              .And(urb_to_end.gte(remaining * p["breakpoint_min_fraction"]))
              .And(urb_to_end.gte(1))
              .And(urb_to_end.gte(min(p["breakpoint_min_years"], remaining))))
        bp = bp.updateMask(bp).unmask(0)
        acc = bp if acc is None else acc.max(bp)
        out[y] = acc
    return out


def spatial(col: dict[int, ee.Image], cfg: dict) -> dict[int, ee.Image]:
    """Máscara espacial, preenchimento de buracos e remoção de ruído (Filtro D)."""
    p = cfg["postprocess"]
    mask = ee.Image(p["spatial_mask"]).gte(1)
    out = {}
    for y, img in col.items():
        au = img.multiply(mask)
        holes = au.eq(0).selfMask().connectedPixelCount(maxSize=p["hole_px"] + 1, eightConnected=False)
        no_hole = au.where(holes.lt(p["hole_px"]), 1).reproject(crs="EPSG:4326", scale=30)
        noise = no_hole.eq(1).selfMask().connectedPixelCount(maxSize=p["noise_px"] + 1, eightConnected=False)
        out[y] = no_hole.where(noise.lt(p["noise_px"]), 0).reproject(crs="EPSG:4326", scale=30)
    return out


def final_map(cfg: dict | None = None) -> ee.Image:
    """Mapa final: 41 bandas classification_AAAA, 1 urbano / 0 não urbano, dentro da grade hexagonal."""
    cfg = cfg or config.load()
    p = cfg["postprocess"]
    col = spatial(breakpoint(temporal_unique(raw_series(cfg), cfg), cfg), cfg)
    years = config.years(cfg)
    img = ee.Image.cat([col[y].rename(f"classification_{y}") for y in years])
    hexes = ee.FeatureCollection(p["cartas_hex"]).map(lambda f: f.set("territory", 3))
    territory = hexes.reduceToImage(properties=["territory"], reducer=ee.Reducer.first())
    return img.updateMask(territory.eq(3)).unmask(0)


def export_tasks(cartas: list[str], cfg: dict | None = None, suffix: str = ""):
    """Uma tarefa por carta (região da carta 1:250.000), como no script de produção."""
    cfg = cfg or config.load()
    p = cfg["postprocess"]
    img = final_map(cfg)
    cartas_fc = ee.FeatureCollection(p["cartas_export"])
    meta = {
        "collection_id": cfg["collection"], "theme": "Urban Area", "territory": "BRAZIL",
        "source": "GT URBANO", "version": p["version"], "product_type": "classification",
        "probability_source": p["probability_source"], "threshold_image": p["threshold_image"],
        "breakpoint_min_fraction": p["breakpoint_min_fraction"], "breakpoint_min_years": p["breakpoint_min_years"],
        "hole_px": p["hole_px"], "noise_px": p["noise_px"], "spatial_mask": p["spatial_mask"],
        "code_version": config.code_version(),
        "config_sha256": config.config_hash(cfg), "inputs": config.inputs_manifest(cfg),
    }
    specs = []
    for carta in cartas:
        name = f"mapa_{carta}{suffix}"
        asset_id = config.asset_path(p["folder"], name, cfg=cfg)
        region = cartas_fc.filter(ee.Filter.eq("grid_name", carta)).geometry()
        image = img.set(meta).set("grid_name", carta)
        specs.append((name, asset_id, lambda image=image, name=name, asset_id=asset_id, region=region:
                      ee.batch.Export.image.toAsset(
                          image=image, description=config.task_description(name, cfg), assetId=asset_id,
                          region=region, scale=30, maxPixels=1e13, pyramidingPolicy={".default": "mode"})))
    return specs
