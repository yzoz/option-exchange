var express = require('express'),
	fs = require("fs"),
	router = express.Router()

router.get('/', (req, res) => {
	res.redirect('/exchange/eth/btc/1519862400')
})

router.get('/:token/:unit/:exp', (req, res) => {
	exp = req.params.exp
	token = req.params.token
	unit = req.params.unit
	ticker = token + '_' + unit
	ticker = ticker.toUpperCase()

	file = fs.readFileSync('./exchange/instruments.json')
	
	var intruments = JSON.parse(file)
	
	for (instrument in intruments) {
		ass = intruments[instrument][ticker]
		if (ass) {
			name = ass.name
			size = ass.size
			measure = ass.measure
			series = ass.series
			for (serie in series) {
				ser = series[serie][exp]
				if (ser) {
					strikes = ser.strikes
				}
			}
		}
	}

	date = new Date(parseInt(exp) * 1000)
	var month = ('0' + (date.getMonth() + 1)).substr(-2)
	var day = ('0' + date.getDate()).substr(-2)
	var hours = date.getHours()
	var minutes = date.getMinutes()
	var seconds = date.getSeconds()
	date = day + '.' + month + ' | ' + hours + ':' + minutes + ':' + seconds

	res.render('exchange', { 
	title: 'Crypto Assets Options Exchange',
	ticker: ticker,
	name: name,
	size: size,
	measure: measure,
	date: date,
	exp: exp,
	strikes: strikes
  })
})
module.exports = router