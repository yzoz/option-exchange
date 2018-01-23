var express = require('express')
var router = express.Router()

var Sentencer = require('sentencer')

router.get('/', (req, res) => {
	s = Sentencer.make("{{ noun }} {{ a_noun }} {{ nouns }} {{ adjective }} {{ an_adjective }} {{ nouns }} {{ noun }} {{ adjective }} {{ a_noun }}")
	res.send(s);
})

module.exports = router