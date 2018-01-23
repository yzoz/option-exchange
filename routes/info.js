var express = require('express')
var router = express.Router()

router.get('/', (req, res) => {
	res.redirect('/info/eth/btc/')
})

router.get('/eth/btc/', function(req, res) {
  res.render('info/index', { title: 'Ethereum/Bitcoin (ETH/BTC) Weekly Market Info', token: 'eth', unit: 'btc' })
})

router.get('/ac/:token/:unit', function(req, res) {
  period = 'week'
  token = req.params.token
  unit = req.params.unit
  res.render('info/ac', { title: 'Ethereum/Bitcoin (ETH/BTC) Accumulation/Distribution', period: period, token: token, unit: unit })
})

router.get('/ac/:token/:unit/:period', function(req, res) {
  period = req.params.period
  token = req.params.token
  unit = req.params.unit
  res.render('info/ac', { title: 'ETH/BTC A/D', period: period })
})

router.get('/bubbles/:token/:unit', function(req, res) {
  period = 'week'
  token = req.params.token
  unit = req.params.unit
  res.render('info/bubbles', { title: 'Ethereum/Bitcoin (ETH/BTC) Trading Volumes Bubbles', period: period, token: token, unit: unit })
})

router.get('/bubbles/:token/:unit/:period', function(req, res) {
  period = req.params.period
  token = req.params.token
  unit = req.params.unit
  res.render('info/bubbles', { title: 'ETH/BTC Bubbles', period: period })
})

router.get('/volatility/:token/:unit', function(req, res) {
  period = 7
  token = req.params.token
  unit = req.params.unit
  res.render('info/volatility', { title: 'Ethereum/Bitcoin (ETH/BTC) Historical Volatility', period: period, token: token, unit: unit })
})

router.get('/volatility/:token/:unit/:period', function(req, res) {
  period = req.params.period
  token = req.params.token
  unit = req.params.unit
  res.render('info/volatility', { title: 'ETH/BTC HV', period: period })
})

module.exports = router