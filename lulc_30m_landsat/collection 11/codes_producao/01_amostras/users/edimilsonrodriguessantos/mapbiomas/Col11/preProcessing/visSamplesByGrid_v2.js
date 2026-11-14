/**** Start of imports. If edited, may not auto-convert in the playground. ****/
var geometry = 
    /* color: #d63000 */
    /* shown: false */
    /* displayProperties: [
      {
        "type": "rectangle"
      }
    ] */
    ee.Geometry.Polygon(
        [[[-46.88918349022799, -23.58730828483344],
          [-46.88918349022799, -23.929186938399695],
          [-46.34261366600924, -23.929186938399695],
          [-46.34261366600924, -23.58730828483344]]], null, false);
/***** End of imports. If edited, may not auto-convert in the playground. *****/
// feature collections
var cartas = ee.FeatureCollection('projects/mapbiomas-workspace/AUXILIAR/cartas')
var cartasHex = ee.FeatureCollection('projects/ee-mburb-land/assets/LandsatCol9_Inputs/Cartas_250mil_Hex')
Map.addLayer(cartas, {}, 'cartas')
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

var sampleYear = 1985
var batch_mosaic = require('users/edimilsonrodriguessantos/mapbiomas:Col10/classificacao/mosaic_production.js')
var gridToView = [
  'NA-22-V-B', // oiapoque
  'SA-22-X-B', // norte de belem
  ]
var context = cartas.filter(ee.Filter.inList('grid_name', gridToView))
var mosaic = batch_mosaic.mosaicGen (sampleYear, context)
Map.addLayer(mosaic, {bands:['RED', 'GREEN', 'BLUE'], min: 1016, max:1950, gamma:2.4}, 'mosaic ' + gridToView + ' ' + sampleYear, false)

// // -------------
// // old samples
// // -------------
// // var sampleYear = 1985

// // assets 
// var urbSamples = 'projects/mapbiomas-workspace/TRANSVERSAIS/INFRAURBANA9/SAMPLES/Urb'
// var notUrbSamples = 'projects/mapbiomas-workspace/TRANSVERSAIS/INFRAURBANA9/SAMPLES/NUrb'

// var urbSamplesFc = ee.FeatureCollection(urbSamples + "/Samples_Urb_Train_v5_" + sampleYear)
// Map.addLayer(urbSamplesFc, {color: '#980043'}, 'old urbSamplesFc ' + sampleYear)

// var notUrbSamplesFc = ee.FeatureCollection(notUrbSamples +"/Samples_NUrb_Train_v5_" + sampleYear)
// Map.addLayer(notUrbSamplesFc, {color: '#253494'}, 'old not urbSamplesFc ' + sampleYear)

// // -------------
// // new samples
// // -------------
// var klass = 1
// var range = 
//     // '1985_to_2020'
//     '1993_to_2020'
//     // '2001_to_2020'
//     // '2009_to_2020'

// samples created based on stable areas and collections
var allSamples = ee.FeatureCollection('projects/ee-ers/assets/mapbiomas/col11/samples/stable_samples_by_range_v2')
      .merge(ee.FeatureCollection('projects/ee-ers/assets/mapbiomas/col11/samples/stable_samples_by_range_v2_1'))
      .merge(ee.FeatureCollection('projects/ee-ers/assets/mapbiomas/col11/samples/stable_samples_by_range_v2_1_adhoc'))
      // .filterBounds(geometry)

// //      .filter(ee.Filter.eq('range', range))

// // get urban samples
// var urban = samples.filter(ee.Filter.eq('class', klass)).randomColumn()
// var urbanToClassify = urban.filter(ee.Filter.lte('random', 0.8)).map(function(f){return f.set('type', 'classification')})
// var urbanToValidate = urban.filter(ee.Filter.gt('random', 0.8)).map(function(f){return f.set('type', 'validation')})

// Map.addLayer(urbanToClassify, {color:'#a50f15'}, 'urbanToClassify (dark red)', false)
// // Map.addLayer(urbanToValidate, {color:'#fc9272'}, 'urbanToValidate (light red)')

// // get not urban samples
// var notUrban = samples.filter(ee.Filter.eq('class', klass).not()).randomColumn()
// var notUrbanToClassify = notUrban.filter(ee.Filter.lte('random', 0.8)).map(function(f){return f.set('type', 'classification')})
// var notUrbanToValidate = notUrban.filter(ee.Filter.gt('random', 0.8)).map(function(f){return f.set('type', 'validation')})

// Map.addLayer(notUrbanToClassify, {color:'#08306b'}, 'notUrbanToClassify', false)
// // // Map.addLayer(notUrbanToValidate, {color:'#4292c6'}, 'notUrbanToValidate')

var rangeList = [
    '1985_to_2020',
    '1993_to_2020',
    '2001_to_2020',
    '2009_to_2020',
  ]

function separatingClassificationAndValidation (range){
  
  // get samples
  var samples = allSamples.filter(ee.Filter.eq('range', range))
  
  // get urban
  var urban = samples.filter(ee.Filter.eq('class', 1)).randomColumn()
  var urbanToClassify = urban.filter(ee.Filter.lte('random', 0.8)).map(function(f){return f.set('type', 'classification')})
  var urbanToValidate = urban.filter(ee.Filter.gt('random', 0.8)).map(function(f){return f.set('type', 'validation')})

  // get not urban samples
  var notUrban = samples.filter(ee.Filter.eq('class', 1).not()).randomColumn()
  var notUrbanToClassify = notUrban.filter(ee.Filter.lte('random', 0.8)).map(function(f){return f.set('type', 'classification')})
  var notUrbanToValidate = notUrban.filter(ee.Filter.gt('random', 0.8)).map(function(f){return f.set('type', 'validation')})
  
  return urbanToClassify.merge(urbanToValidate).merge(notUrbanToClassify).merge(notUrbanToValidate)
}

var result = ee.FeatureCollection(rangeList.map(separatingClassificationAndValidation)).flatten()

// Map.addLayer(samplesSeparated, {}, 'samplesSeparated')
var id = 'projects/ee-ers/assets/mapbiomas/col11/samples/'
// var version = '2' //initial version
// var version = '2_1' //with additional/corrected samples
// var version = '2_1_adhoc' //with additional/corrected samples

var version = 1
var description = 'stable_samples_by_range_merged_v' + version

Export.table.toAsset({
  collection: result, 
  description: description, 
  assetId:id + description
})



















// Map.addLayer(
//   // feature collection to plot
//   samples
//     .filter(ee.Filter.eq(
//       'range', '2009_to_2020'
//       ))
//     .filter(ee.Filter.eq('class', klass)),
  
//   // vis param
//   {color:'red'},
  
//   // name
//   'Samples - class ' + klass
  
//   )


  //   var range = '1985_to_2020'
  // } else if (year < 2001){
    
  //   var range = '1993_to_2020'
  // } else if (year < 2009){
    
  //   var range = '2001_to_2020'
  // } else {
    
  //   var range = '2009_to_2020'
  // }
  
// var ranges = [
//     '1985_to_2020',
//     '1993_to_2020',
//     '2001_to_2020',
//     '2009_to_2020',
//     ]

// // ---------
// // Load your rectangle feature collection
// var rectangles = cartas.filter(ee.Filter.inList('grid_name', gridList))
// // print(rectangles)

// function imgColByRange (range){
//   // Load your sample points feature collection
//   var points = samples.filter(ee.Filter.eq('range', range))
//   // print(points.filterBounds(geometry))
  
//   // Count points in each rectangle
//   var rectanglesWithCount = rectangles.map(function(rect) {
//     // Get the rectangle geometry
//     // var rectGeometry = rect.geometry();
    
//     var feature = rect.geometry().buffer(5, 5);
//     var rectGeometry = rectangles.filterBounds(feature)
    
//     // Filter points that intersect the rectangle
//     var pointsInRect = points.filterBounds(rectGeometry);
    
//     // Count the number of points
//     var pointCount = pointsInRect.size();
    
//     // Add the count as a new property
//     return rect.set('sample_count', pointCount);
//   });
  
//   // // Print the result to console (optional)
//   // print('Rectangles with point counts:', rectanglesWithCount);
  
//   var img = ee.Image().byte().paint({
//     featureCollection: rectanglesWithCount, 
//     color: 'sample_count'})
    
//   return img
//   // .rename(range)
//   .set('range', range).toByte()
// }

// var img = ee.ImageCollection(ranges.map(imgColByRange))

// // Visualization parameters for rectangles
// var rectVis = {
//   min: 0,
//   max: 50,  // Adjust based on your maximum point count
//   // color: ['white', 'yellow', 'orange', 'red', 'darkred']
// };

// // Add rectangles layer to map
// Map.addLayer(
//   // rectanglesWithCount,
//   img,
//   rectVis,
//   'Samples per Rectangle'
// );




// // Optional: Add points layer for reference
// Map.addLayer(points, {color: 'blue'}, 'Sample Points');

// // Optional: Add labels showing the count on the map
// var getLabeledFeatures = function(feature) {
//   var centroid = feature.geometry().centroid();
//   var count = feature.get('sample_count');
//   return ee.Feature(centroid, {label: count});
// };

// var labels = rectanglesWithCount.map(getLabeledFeatures);

// // Add labels to map (as text)
// Map.addLayer(
//   labels,
//   {color: 'black', pointSize: 12},
//   'Count Labels'
// );

// // Center the map on your area of study
// Map.centerObject(rectangles, 10);  // Adjust zoom level as needed

// // Create a chart (optional)
// var chart = ui.Chart.feature.byFeature({
//   features: rectanglesWithCount,
//   xProperty: 'grid_name',  // or another property to identify rectangles
//   yProperties: ['sample_count']
// })
// .setChartType('ColumnChart')
// .setOptions({
//   title: 'Samples per Rectangle',
//   hAxis: {title: 'Rectangle'},
//   vAxis: {title: 'Number of Samples'},
//   legend: {position: 'none'}
// });

// print(chart);