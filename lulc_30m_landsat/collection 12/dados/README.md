# Insumos vetoriais e tabelas usados pelo código

Cópias dos insumos pequenos que o pacote `mb_urban` lê do Earth Engine, guardadas aqui para o método
continuar reproduzível se o acesso a algum asset de origem mudar. Baixadas em 2026-11-15.

| Arquivo | Asset de origem | Chave na configuração | Conteúdo | sha256 |
|---|---|---|---|---|
| `cartas_ibge_250mil.geojson.gz` | `projects/mapbiomas-workspace/AUXILIAR/cartas` | `grids.cartas` | 558 cartas 1:250.000 do IBGE (`grid_name`); usadas para a super carta | `01b2b67aff926e767c948cdfbb7dd0b1199f4ca25ff7dfc0914beb1819b258d8` |
| `cartas_250mil_hex.geojson.gz` | `projects/ee-mburb-land/assets/LandsatCol9_Inputs/Cartas_250mil_Hex` e `projects/ee-mburb-land-c10/assets/Inputs/Cartas_250mil_Hex` (idênticos) | `grids.cartas_hex`, `postprocess.cartas_hex` | 522 cartas recortadas na grade hexagonal: área classificada de cada carta | `b0071e5598f64d5e9a5d13145d762b56832f01d741294bd1864801eb0753b2b9` |
| `cartas_250mil_c10.geojson.gz` | `projects/ee-mburb-land-c10/assets/Inputs/Cartas_250mil` | `postprocess.cartas_export` | 558 cartas (`grid_name`, `grid_name_1mi`); região de exportação do mapa final | `2749c09ec02a3c5e8c03c84b05e84cad7a2259bf24754cabad15b317d7c71438` |
| `col11_limiares_por_carta.csv` | `projects/ee-ers/assets/mapbiomas/col11/thresholdMedianByCarta` | origem de `postprocess.threshold_image` | Limiares da Col 11 por carta (`cutPercentile` = banda `percentil` usada no pré-filtro; `threshold` = Youden; p10, p90, anos, completude) | `01e49d823ddf1d3aad0b2e1610380366204df8487918ab0c9ffb6a027f339d49` |

Os GeoJSON estão em EPSG:4326, compactados com gzip. As amostras da Col 11 estão em `collection 11/dados/`.

## Se um asset de origem deixar de existir

1. Suba o arquivo como asset no seu projeto (Code Editor › Assets › New › Table upload, ou `earthengine upload table`;
   descompacte antes; para o CSV de limiares, suba como tabela).
2. Aponte a chave correspondente na sua configuração para o novo asset.
3. A imagem de limiares (`postprocess.threshold_image`, bandas `percentil` e `threshold`) é gerada da tabela de
   limiares + cartas por `mb_urban.thresholds.image_export_spec` (equivalente a `meanThresholdsByGridAsImage.js`).

## Fora daqui (rasters grandes)

A máscara espacial (`postprocess.spatial_mask`) e o IRS (`postprocess.irs_asset`) são rasters do Brasil a 30 m e
não cabem no repositório; continuam lidos dos assets de origem.
