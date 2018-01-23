var express = require('express'),
	router = express.Router()

router.get('/', (req, res) => {
	res.render('index', { 
	title: 'Crypto Financial'
  })
})

module.exports = router