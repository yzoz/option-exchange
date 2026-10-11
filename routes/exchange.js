var express = require('express'),
	router = express.Router(),
	instruments = require('../lib/instruments')

// Разбор каталога инструментов вынесен в lib/instruments.js (задача ТЗ #23) —
// здесь остаётся только HTTP-логика страницы торгового стола.

router.get('/', (req, res) => {
	res.redirect('/exchange/eth/btc/' + instruments.firstExp('ETH_BTC'))
})

router.get('/:token/:unit/:exp', (req, res) => {
	var exp = req.params.exp
	var token = req.params.token
	var unit = req.params.unit
	var ticker = (token + '_' + unit).toUpperCase()

	var series = instruments.series(ticker, exp)
	if (!series) {
		return res.status(404).render('error', {
			message: 'Unknown instrument/expiry: ' + ticker + ' / ' + exp,
			error: { status: 404 }
		})
	}

	var date = new Date(parseInt(exp) * 1000)
	var month = ('0' + (date.getMonth() + 1)).substr(-2)
	var day = ('0' + date.getDate()).substr(-2)
	var hours = date.getHours()
	var minutes = date.getMinutes()
	var seconds = date.getSeconds()
	date = day + '.' + month + ' | ' + hours + ':' + minutes + ':' + seconds

	res.render('exchange', {
		title: 'Crypto Assets Options Exchange',
		ticker: ticker,
		name: series.name,
		size: series.size,
		measure: series.measure,
		date: date,
		exp: exp,
		strikes: series.strikes
	})
})

module.exports = router
