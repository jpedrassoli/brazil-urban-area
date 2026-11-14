/**** Start of imports. If edited, may not auto-convert in the playground. ****/
var geometry = /* color: #d63000 */ee.Geometry.MultiPoint(
        [[-53.28722907137456, -26.4804641266542],
         [-51.57336188387456, -24.417199975770348],
         [-50.12316657137456, -22.60392759673431],
         [-48.45324469637456, -20.437367587166687],
         [-51.92492438387456, -30.268611215387228],
         [-47.04699469637456, -17.319237164559127],
         [-48.98058844637456, -1.3732231692891577],
         [-50.56261969637456, 0.6481158946270439],
         [-62.03234625887456, -11.361630356123872],
         [-54.42980719637456, -17.445052582359498],
         [-54.64953375887456, -15.464330422735618],
         [-51.52941657137456, -17.319237164559127],
         [-49.11242438387456, -13.549943318105454],
         [-48.80480719637456, -10.62827866332507],
         [-48.67297125887456, -8.505033146166177],
         [-54.78136969637456, -21.50424471325963],
         [-47.26672125887456, -22.482165041768226],
         [-39.79601813387456, -10.62827866332507],
         [-47.26672125887456, -4.532681837531636],
         [-43.88293219637456, -18.490088931243573],
         [-41.20226813387456, -13.678075094413376],
         [-54.86926032137456, -28.31410908652476],
         [-57.63781500887456, -16.478291156403294],
         [-53.24328375887456, -19.280095869545192],
         [-52.05676032137456, -10.649873602103714],
         [-35.44543219637456, -6.500962371379607],
         [-35.81896735262456, -8.374624949457036]]);
/***** End of imports. If edited, may not auto-convert in the playground. *****/
// var batchCollections = require('users/edimilsonrodriguessantos/mapbiomas:mb_batch/collections.js')

// batch to get collections
var collectionInfo = {
  /*
  n : {
    'asset':,
    'function':,
    'level1':,
    'level12:,
  }
  */
  6:{
    'asset': 'projects/mapbiomas-public/assets/brazil/lulc/collection6/mapbiomas_collection60_integration_v1',
    'function': '', 
  },
  7:{
    'asset': 'projects/mapbiomas-public/assets/brazil/lulc/collection7_1/mapbiomas_collection71_integration_v1',
    'function': '', 
  },
  8:{
    'asset': 'projects/mapbiomas-public/assets/brazil/lulc/collection8/mapbiomas_collection80_integration_v1',
    'function': '', 
  },
  9:{
    'asset': 'projects/mapbiomas-public/assets/brazil/lulc/collection9/mapbiomas_collection90_integration_v1',
    'function': '', 
  },
  10:{
    'asset': 'projects/mapbiomas-public/assets/brazil/lulc/collection10_1/mapbiomas_brazil_collection10_1_coverage_v1',
    'function': '', 
  },
}

function collection (col){
  return ee.Image(collectionInfo[col]['asset'])
}

// print(collection (10))
exports.collection = collection

var colList = [
  // 10
  6, 7, 8, 9, 10
  ]

function stableCollectionByYear (refCol, year){
  
  var referenceImage = collection (refCol).select('classification_' + year)
  
  var collections = ee.ImageCollection(
    
      colList.map(function (col){
        
        return collection (col).select('classification_' + year)
        
      })).sum().divide(5)
  
  return referenceImage
  .where(referenceImage.eq(collections), referenceImage)
  .where(referenceImage.neq(collections), 0)
  .selfMask()
  
}
exports.stableCollectionByYear = stableCollectionByYear
// Map.addLayer(stableCollectionByYear (10, 2020))

function stableCollectionBy5Years (refCol, years){
  
  var referenceImage = stableCollectionByYear (refCol, years[0]).select('classification_' + years[0])
  .rename('stable').toByte()
  
  var collections = ee.ImageCollection(
    
      years.map(function (year){
        
        return stableCollectionByYear (refCol, year).select('classification_' + year)
        .rename('stable').toByte()
        
      })).sum().divide(5)
  
  return referenceImage
  .where(referenceImage.eq(collections), referenceImage)
  .where(referenceImage.neq(collections), 0)
  .selfMask()
  
  return referenceImage
  
}

exports.stableCollectionBy5Years = stableCollectionBy5Years

function stableCollectionByKYears (refCol, years, k){
  
  var referenceImage = stableCollectionByYear (refCol, years[0]).select('classification_' + years[0])
  .rename('stable').toByte()
  
  var collections = ee.ImageCollection(
    
      years.map(function (year){
        
        return stableCollectionByYear (refCol, year).select('classification_' + year)
        .rename('stable').toByte()
        
      })).sum().divide(k)
  
  return referenceImage
  .where(referenceImage.eq(collections), referenceImage)
  .where(referenceImage.neq(collections), 0)
  .selfMask()
  
  return referenceImage
  
}

exports.stableCollectionByKYears = stableCollectionByKYears

// Map.addLayer(stableCollectionBy5Years (10, [2015, 2016, 2017, 2018, 2019]), {}, 'stable areas')


var from = [

// forest
3, 4, 5, 6, 49,

// herbaceous and shrubby veg
11, 12, 32, 29, 50,

// farming
15, 18, 19, 39, 20, 40, 62, 41, 36, 46, 47, 35, 48, 9, 21,

// non veg areas
23, 24, 30, 75, 25, 

// agua
33, 31, 27

]

var to = [

// forest
2, 2, 2, 2, 2,

// herbaceous and shrubby veg
2, 2, 2, 2, 2,

// farming
4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4,

// non veg areas
0, 1, 0, 0, 0, 

// agua
3, 3, 3

]

function remapMapBiomas (image){
  return image.remap(
    from,
    to
    ).rename('class')
}

exports.remapMapBiomas = remapMapBiomas

function stableCollectionByYearRemmaped (refCol, year){
  
  var referenceImage = collection (refCol).select('classification_' + year)
  
  referenceImage = remapMapBiomas (referenceImage)
  
  var collections = ee.ImageCollection(
    
      colList.map(function (col){
        
        // return collection (col).select('classification_' + year)
        return remapMapBiomas(collection (col).select('classification_' + year))
        
      })).sum().divide(5)
  
  return referenceImage
  .where(referenceImage.eq(collections), referenceImage)
  .where(referenceImage.neq(collections), 0)
  .selfMask()
  
}
exports.stableCollectionByYearRemmaped = stableCollectionByYearRemmaped
// Map.addLayer(stableCollectionByYearRemmaped (10, 1985), {min:1, max: 4}, 'stable remapped')


function stableCollectionByKYearsRemapped (refCol, years, k){
  
  var referenceImage = stableCollectionByYearRemmaped (refCol, years[0])
  // .select('classification_' + years[0])
  .rename('stable').toByte()
  
  var collections = ee.ImageCollection(
    
      years.map(function (year){
        
        // return stableCollectionByYear (refCol, year).select('classification_' + year)
        return stableCollectionByYearRemmaped (refCol, year)
        // .select('classification_' + year)
        .rename('stable').toByte()
        
      })).sum().divide(k)
  
  return referenceImage
  .where(referenceImage.eq(collections), referenceImage)
  .where(referenceImage.neq(collections), 0)
  .selfMask()
  
  return referenceImage
  
}

exports.stableCollectionByKYearsRemapped = stableCollectionByKYearsRemapped

function listSequenceByStep (from, to, step){
    var list = []
    for (var k = from; k<=to; k=k+step){list.push(k)}
  return list
}

exports.listSequenceByStep = listSequenceByStep


// feature collections
var cartas = ee.FeatureCollection('projects/mapbiomas-workspace/AUXILIAR/cartas')
var cartasHex = ee.FeatureCollection('projects/ee-mburb-land/assets/LandsatCol9_Inputs/Cartas_250mil_Hex')
// Map.addLayer(cartas, {}, 'cartas')
Map.addLayer(cartasHex, {}, 'cartasHex')

// gridlist
var batchLists = require('users/edimilsonrodriguessantos/mapbiomas:mb_batch/listsAndDicts.js')
var gridList = 
    // // cartas para teste (col11)
    // batchLists.cartastest // somente para teste
    
    // // cartas para teste (col 10)
    // batchLists.cartasCompleteSetToClassify
    
    // cartas de classificacao
    batchLists.cartasParaClassificacao
Map.addLayer(cartas.filter(ee.Filter.inList('grid_name', gridList)), {}, 'cartas')

var years = listSequenceByStep (1985, 2020, 1)
var vis = {min:1, max:4, palette:['#9c0027', '#d6bc74', '#2532e4', '#ffefc3']}
Map.addLayer(remapMapBiomas (stableCollectionByKYears (10, years, 36)), vis, 'sem remap previo')
Map.addLayer(stableCollectionByKYearsRemapped (10, years, 36), vis, 'com remap previo')

print(cartas.filterBounds(geometry).aggregate_array('grid_name'))
