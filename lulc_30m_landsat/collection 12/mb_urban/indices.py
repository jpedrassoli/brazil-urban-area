"""Índices espectrais e mistura espectral.

Porte fiel de `collection 11/codes_producao/02_classificacao/users/edimilsonrodriguessantos/mapbiomas/Col10/classificacao/index_lib.js`
(versão de produção da Col 11, commit 671895e5). As bandas de entrada têm os nomes
padronizados BLUE, GREEN, RED, NIR, SWIR1, SWIR2 (reflectância) ou NIR, MIR, TIR (Landsat bruto).
Cada função recebe uma ee.Image e devolve uma imagem com a(s) nova(s) banda(s).
"""
from __future__ import annotations

import ee


def _expr(image: ee.Image, expression: str, bands: list[str], name: str) -> ee.Image:
    return image.expression(expression, {b: image.select(b) for b in bands}).rename(name)


# --- vegetação ---------------------------------------------------------------
def ndvi(img):  return _expr(img, "(NIR - RED) / (NIR + RED)", ["NIR", "RED"], "NDVI")
def evi(img):   return _expr(img, "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))", ["NIR", "RED", "BLUE"], "EVI")
def evi2(img):  return _expr(img, "2.5 * ((NIR - RED) / (NIR + 2.4 * RED + 1))", ["NIR", "RED"], "EVI2")
def savi(img):  return _expr(img, "((NIR - RED) / (NIR + RED + 0.5)) * 1.5", ["NIR", "RED"], "SAVI")


# --- água --------------------------------------------------------------------
def mndwi(img):  return _expr(img, "(GREEN - SWIR1) / (GREEN + SWIR1)", ["GREEN", "SWIR1"], "MNDWI")   # Xu, 2005
def ndwim(img):  return _expr(img, "(GREEN - NIR) / (GREEN + NIR)", ["GREEN", "NIR"], "NDWIm")         # McFeeters, 1996
def aweish(img): return _expr(img, "BLUE + 2.5 * GREEN - 1.5 * (NIR + SWIR1) - 0.25 * SWIR2",
                              ["BLUE", "GREEN", "NIR", "SWIR1", "SWIR2"], "AWEIsh")


# --- áreas construídas / solo ---------------------------------------------------
def ndbi(img): return _expr(img, "(SWIR1 - NIR) / (SWIR1 + NIR)", ["SWIR1", "NIR"], "NDBI")   # Zha et al., 2003
def ui(img):   return _expr(img, "(SWIR2 - NIR) / (SWIR2 + NIR)", ["SWIR2", "NIR"], "UI")
def ndui(img): return _expr(img, "(NIR - SWIR1) / (NIR + SWIR1)", ["NIR", "SWIR1"], "NDUI")
def nbr(img):  return _expr(img, "(NIR - SWIR2) / (NIR + SWIR2)", ["NIR", "SWIR2"], "NBR")
def ndri(img): return _expr(img, "(RED - BLUE) / (RED + BLUE)", ["RED", "BLUE"], "NDRI")      # De Pinho et al., 2011
def bai(img):  return _expr(img, "(BLUE - NIR) / (BLUE + NIR)", ["BLUE", "NIR"], "BAI")       # Santos et al., 2022
def bsi(img):  return _expr(img, "((SWIR1 + RED) - (NIR + BLUE)) / ((SWIR1 + RED) + (NIR + BLUE))",
                            ["SWIR1", "RED", "NIR", "BLUE"], "BSI")


def bu(img):
    """NDBI - NDVI. Exige que NDBI e NDVI já estejam na imagem."""
    return _expr(img, "NDBI - NDVI", ["NDBI", "NDVI"], "BU")


# --- Landsat bruto (números digitais) -------------------------------------------
def ebbi(img):
    return _expr(img, "((MIR - NIR) / (10 * ((MIR + TIR) ** 0.5)))", ["MIR", "NIR", "TIR"], "EBBI")


# --- mistura espectral ---------------------------------------------------------
_SR_BANDS = ["BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2"]

_ENDMEMBERS_SMA = [
    [0.0119, 0.0475, 0.0169, 0.6250, 0.2399, 0.0675],  # gv
    [0.1514, 0.1597, 0.1421, 0.3053, 0.7707, 0.1975],  # npv
    [0.1799, 0.2479, 0.3158, 0.5437, 0.7707, 0.6646],  # soil
    [0.4031, 0.8714, 0.7900, 0.8989, 0.7002, 0.6607],  # cloud
]

_ENDMEMBERS_SMALL = [
    [0.178, 0.337, 0.458, 0.559, 0.683, 0.645],  # substrate
    [0.030, 0.060, 0.031, 0.669, 0.240, 0.096],  # vegetation
    [0.019, 0.010, 0.005, 0.007, 0.003, 0.002],  # dark
]


def sma(img):
    """Frações GV, NPV, SOIL, CLOUD (0-100) + GVS e SHADE."""
    fractions = (ee.Image(img).select(_SR_BANDS).unmix(_ENDMEMBERS_SMA)
                 .max(0).multiply(100).byte()
                 .rename(["GV", "NPV", "SOIL", "CLOUD"]))
    summed = fractions.expression('b("GV") + b("NPV") + b("SOIL")')
    shade = summed.subtract(100).abs().byte()
    gvs = fractions.select("GV").divide(summed).multiply(100).toUint16().byte()
    return fractions.addBands(gvs.rename("GVS")).addBands(shade.rename("SHADE"))


def ndfi(img):
    """NDFI reescalado para byte (0-200). Exige GVS, NPV e SOIL na imagem."""
    npv_soil = img.expression('b("NPV") + b("SOIL")')
    value = ee.Image.cat(img.select("GVS"), npv_soil).normalizedDifference().rename("NDFI")
    return value.expression('byte(b("NDFI") * 100 + 100)')


def sma_small(img):
    """Frações SUBS, VEG, DARK (0-100), mistura com soma restrita a 1."""
    return (ee.Image(img).select(_SR_BANDS).unmix(_ENDMEMBERS_SMALL, True, False)
            .max(0).multiply(100).byte()
            .rename(["SUBS", "VEG", "DARK"]))


# --- espaços de atributos usados no mosaico ------------------------------------------
def sr_feature_space(img: ee.Image) -> ee.Image:
    """Mesma sequência de srFeatureSpace (mosaic_production.js)."""
    for fn in (ndvi, evi, evi2, savi, mndwi, ndwim, aweish,
               ndbi, nbr, ui, bsi, ndri, bai, ndui):
        img = img.addBands(fn(img))
    img = img.addBands(bu(img))
    img = img.addBands(sma(img))
    img = img.addBands(ndfi(img))
    img = img.addBands(sma_small(img))
    return img


def raw_feature_space(img: ee.Image) -> ee.Image:
    return img.addBands(ebbi(img))
