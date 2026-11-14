// var batchFilters = require('users/edimilsonrodriguessantos/mapbiomas:Col11/filters/batchFilters.js')

// require with the block with collections
var batchCollections = require('users/edimilsonrodriguessantos/mapbiomas:mb_batch/collections.js')

// require with the block for prob
var resultsBatch = require('users/edimilsonrodriguessantos/mapbiomas:Col11/results/batchResults.js')
/*
mosaicClassificationByYear (year) --> gets the prob classification by year (col11)
*/

// This will be used in the next few lines.
var join = ee.Join.saveAll({matchesKey: 'images'})

// here is a filter that we considered to combine the images 
// the "difference" refers to a quantity of years that were considered as temporal range
// for example: difference is 2, then the range is [years-2, years+2]
var filter = ee.Filter.maxDifference({
  difference: 2, 
  leftField: 'year',  
  rightField: 'year'
})

function getImageYear (year) {
  return ee.Image(resultsBatch.mosaicClassificationByYear (year)).rename('classification').unmask()
}

// this is the key part of the probability "harmonization" 
function temporalHarmonization (year){
    
    var years = yearsDict[year]
    
    // function to create a set of images considering the temporal range
    // and calculate the mean probability value
    function meanWithinMatchingImages (image){
      
      var year = image.get('year')
      
      var imgs = ee.ImageCollection.fromImages(image.get('images'))
      
      var meanResult = imgs.reduce(ee.Reducer.mean())
      
      return ee.Image(meanResult).toByte().set('year', year)
      
    }
    
    // 1) we create a colllection of images covering all the years
    var colToApplyAFilter = ee.ImageCollection(years.map(getImageYear))
    
    // 2) we combined this collection with itself to enable us to calculate the average
    // probability value in a time window.
    var joinedColl = join.apply(colToApplyAFilter, colToApplyAFilter, filter)
    
    // 3) here is the harmonized image collection
    var smoothedColl = ee.ImageCollection(joinedColl.map(meanWithinMatchingImages))
    
    return ee.Image(smoothedColl.filter(ee.Filter.eq('year', year)).first())
}

function neighborhoodFilter (image){
  
  var kernel = ee.Kernel.circle(6)
  
  var image = image.updateMask(image.gte(threshold.select('percentil').multiply(0.7)))
  
  var filtered = image.reduceNeighborhood({
    reducer: ee.Reducer.mean(),
    kernel: kernel
  }).reproject('EPSG:4326', null, 30);
  
  return filtered
}


var yearsDict = {
    1985: [1985, 1986, 1987,],
    1986: [1985, 1986, 1987, 1988,],
    1987: [1985, 1986, 1987, 1988, 1989,],
    1988: [1986, 1987, 1988, 1989, 1990,],
    1989: [1987, 1988, 1989, 1990, 1991,],
    1990: [1988, 1989, 1990, 1991, 1992,],
    1991: [1989, 1990, 1991, 1992, 1993,],
    1992: [1990, 1991, 1992, 1993, 1994,],
    1993: [1991, 1992, 1993, 1994, 1995,],
    1994: [1992, 1993, 1994, 1995, 1996,],
    1995: [1993, 1994, 1995, 1996, 1997,],
    1996: [1994, 1995, 1996, 1997, 1998,],
    1997: [1995, 1996, 1997, 1998, 1999,],
    1998: [1996, 1997, 1998, 1999, 2000,],
    1999: [1997, 1998, 1999, 2000, 2001,],
    2000: [1998, 1999, 2000, 2001, 2002,],
    2001: [1999, 2000, 2001, 2002, 2003,],
    2002: [2000, 2001, 2002, 2003, 2004,],
    2003: [2001, 2002, 2003, 2004, 2005,],
    2004: [2002, 2003, 2004, 2005, 2006,],
    2005: [2003, 2004, 2005, 2006, 2007,],
    2006: [2004, 2005, 2006, 2007, 2008,],
    2007: [2005, 2006, 2007, 2008, 2009,],
    2008: [2006, 2007, 2008, 2009, 2010,],
    2009: [2007, 2008, 2009, 2010, 2011,],
    2010: [2008, 2009, 2010, 2011, 2012,],
    2011: [2009, 2010, 2011, 2012, 2013,],
    2012: [2010, 2011, 2012, 2013, 2014,],
    2013: [2011, 2012, 2013, 2014, 2015,],
    2014: [2012, 2013, 2014, 2015, 2016,],
    2015: [2013, 2014, 2015, 2016, 2017,],
    2016: [2014, 2015, 2016, 2017, 2018,],
    2017: [2015, 2016, 2017, 2018, 2019,],
    2018: [2016, 2017, 2018, 2019, 2020,],
    2019: [2017, 2018, 2019, 2020, 2021,],
    2020: [2018, 2019, 2020, 2021, 2022,],
    2021: [2019, 2020, 2021, 2022, 2023,],
    2022: [2020, 2021, 2022, 2023, 2024,],
    2023: [2021, 2022, 2023, 2024, 2025,],
    2024: [2022, 2023, 2024, 2025,],
    2025: [2023, 2024, 2025,],
}

// ----------------------
// imagem com o irs
var irs = ee.ImageCollection('users/efjustiniano/IRS2023/IRS2023_v2').sum()
// Map.addLayer(irs)

var threshold = ee.Image('projects/ee-ers/assets/mapbiomas/col11/thresholdMedianByCartaImg')
var mask = threshold.select('percentil').multiply(0.9)

function applyPreFilter (year){
  
    var imgYear = getImageYear(year) 
    // Map.addLayer(imgYear, {min:0, max:100}, 'original')
    
    var avgYear = imgYear.gte(mask)
    // Map.addLayer(avgYear, {}, 'avgYear')
    
    var imgYearAvg = temporalHarmonization (year)
    // Map.addLayer(imgYearAvg, {min:0, max:100}, 'average')
    
    // var avgMasked = imgYearAvg.gte(mask)
    // // Map.addLayer(avgMasked, {}, 'avgMasked')
    
    // // ----------------------
    // // with neighborhood rule
    var imgYearAvgNeighb = neighborhoodFilter (imgYearAvg)
    // Map.addLayer(imgYearAvgNeighb, {min:0, max:100, palette:['yellow', 'orange', 'red']}, 'imgYearAvgNeighb')
    
    var avgMaskedNeighb = imgYearAvgNeighb.gte(mask)
    // Map.addLayer(avgMaskedNeighb, {}, 'avgMaskedNeighb')
    
    // ----------------------
    var imgProb = ee.Image(resultsBatch.getImgAllProbCol11 (year))
    // Map.addLayer(imgProb, {}, 'imgProb')
    
    var avgMaskedNeighb_opened = avgMaskedNeighb
        
        // rule for water
        .where(imgProb.select('water').gte(50).and(imgProb.select('urban').lte(20)), 0)
        
        // rule for vegetation
        .where(imgProb.select('veg').gte(60).and(imgProb.select('urban').lte(20)), 0)
        
        // rule for others
        .where(imgProb.select('other').gte(60).and(imgProb.select('urban').lte(20)), 0)
        
        .selfMask()
    
    if (year <= 2023){avgMaskedNeighb_opened = avgMaskedNeighb_opened.multiply(irs.gte(400))}
    
    return avgMaskedNeighb_opened.rename('classification_' + year)
}

exports.applyPreFilter = applyPreFilter

// // here are variables that we used in memory. For us, they were necessary to 
// // rename bands according to years
// var firstYear = 1985
// var yearsList = ee.List.sequence(firstYear, 2025).getInfo()
// var bandsNamesByYear = []
// var bandsIds = ee.List.sequence(0, yearsList.length-1).getInfo()

// for (var i =0; i < yearsList.length; i++){
//   var y = firstYear + i
//   var newBandName = 'classification_' + y
//   bandsNamesByYear.push(newBandName)
// }

// var years = ee.List.sequence(1985, 2025).getInfo()
// var img = ee.ImageCollection(years.map(applyPreFilter))
//               .toBands().select(bandsIds, bandsNamesByYear)

// var year = 2023
// Map.addLayer(applyPreFilter (year), {palette:['red'], }, 'avgMaskedNeighb_opened') 

// // without neighborhood rule
// var year = 1985


// var coln = 10
// var col = ee.Image(batchCollections.collection (coln)).select('classification_' + year).eq(24).selfMask()
// Map.addLayer(col, {min:0, max:1, palette: ['purple']}, 'Col ' + coln + ' ' + year)

// var coln = 6
// var col = ee.Image(batchCollections.collection (coln)).select('classification_' + year).eq(24).selfMask()
// Map.addLayer(col, {min:0, max:1, palette: ['#3dff0e']}, 'Col ' + coln + ' ' + year)

// var asset_spatialMask = "projects/ee-mburb-land-c10/assets/Testes/Mask_Spatial_v9";
// Map.addLayer(ee.Image(asset_spatialMask).selfMask(), {palette:['blue']}, 'spatial mask')


