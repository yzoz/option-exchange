var express = require('express')
var router = express.Router()

router.get('/', (req, res) => {
	res.render('about/index', { title: 'About'})
})

router.get('/faq/', (req, res) => {
	res.render('about/faq', { title: 'FAQ'})
})

router.get('/ico/', (req, res) => {
	res.render('about/ico', { title: 'ICO'})
})

router.get('/roadmap/', (req, res) => {
	res.render('about/roadmap', { title: 'Roadmap'})
})
module.exports = router