// Verificação do mosaico: valores do mosaico da Col 11 (JS original) num ponto.
// Cole no Code Editor do Earth Engine, rode e copie o dicionário impresso no Console
// para a célula de comparação do notebook 01_mosaico.ipynb.
//
// O require abaixo é o módulo usado na produção da Col 11. Cópia pública da mesma versão (commit bf9c98b0):
// collection 11/codes_producao/02_classificacao/users/edimilsonrodriguessantos/mapbiomas/Col10/classificacao/mosaic_production.js

var mosaicBatch = require('users/edimilsonrodriguessantos/mapbiomas:Col10/classificacao/mosaic_production.js');

var carta = 'SF-23-Y-C';
var ano = 2020;
var ponto = ee.Geometry.Point([-46.633, -23.55]);

// mesma "super carta" usada na Col 11 (getContext em classification_batch.js)
var cartas = ee.FeatureCollection('projects/mapbiomas-workspace/AUXILIAR/cartas');
var cartaFt = ee.Feature(cartas.filter(ee.Filter.eq('grid_name', carta)).first());
var contexto = cartas.filterBounds(cartaFt.geometry().buffer(2, 1)).geometry().bounds(10);

var img = mosaicBatch.mosaicGen(ano, contexto);
print('bandas', img.bandNames().size());
print(img.reduceRegion(ee.Reducer.first(), ponto, 30));
