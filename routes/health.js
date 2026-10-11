// Healthcheck веб-слоя (задача ТЗ #24).
//
// GET /health отдаёт JSON-состояние веб-сервера и зависимости — Python API.
// Всегда отвечает HTTP 200 (это liveness-проба Node-процесса); готовность
// зависимостей выражается полем `status` (`ok` / `degraded`), как и у /health
// API (см. api/app.py). Запрос к API ограничен таймаутом, чтобы зависший API
// не подвешивал healthcheck.

var express = require('express')
var http = require('http')
var https = require('https')
var urllib = require('url')

var router = express.Router()
var API_URL = process.env.API_URL || 'http://localhost:6969'

function probeApi(callback) {
	var target = urllib.parse(API_URL + '/health')
	var lib = target.protocol === 'https:' ? https : http
	var req = lib.get({
		hostname: target.hostname,
		port: target.port || (target.protocol === 'https:' ? 443 : 80),
		path: target.path,
		timeout: 3000
	}, function (res) {
		var body = ''
		res.on('data', function (chunk) { body += chunk })
		res.on('end', function () {
			try {
				callback(null, JSON.parse(body))
			} catch (e) {
				callback('API ответил не-JSON (HTTP ' + res.statusCode + ')')
			}
		})
	})
	req.on('timeout', function () { req.destroy(new Error('таймаут')) })
	req.on('error', function (err) { callback(err.message) })
}

router.get('/', function (req, res) {
	probeApi(function (err, api) {
		var status = err ? 'degraded' : (api.status || 'ok')
		res.json({
			status: status,
			web: { status: 'ok', port: req.socket.localPort },
			api: err ? { status: 'down', error: err } : api
		})
	})
})

module.exports = router
