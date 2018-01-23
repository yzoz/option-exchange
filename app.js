//SET DEBUG=yzoz:* & nodemon npm start
//export NODE_ENV=production
//kill -9 ID
//pkill gunicorn
//ps ax|grep gunicorn
//SET NODE_ENV=production
//SET NODE_ENV=development
//app.get('env')
/* 
	"python-shell": "latest",
	"q": "latest",
    "unix-timestamp": "latest",
	"node-cron": "latest"
*/

var express = require('express')
var path = require('path')
var favicon = require('serve-favicon')
var logger = require('morgan')
var cookieParser = require('cookie-parser')
var bodyParser = require('body-parser')

var index = require('./routes/index')
var info = require('./routes/info')
var exchange = require('./routes/exchange')
var about = require('./routes/about')
var seed = require('./routes/seed')

var app = express()

if (app.get('env') == 'production') {
  app.locals.appStatus = 'production'
}
else {
  app.locals.appStatus = 'development'
}

app.set('views', path.join(__dirname, 'views'))
app.set('view engine', 'pug')

app.use(favicon(path.join(__dirname, 'public', 'favicon.ico')))
app.use(logger('dev'))
app.use(bodyParser.json())
app.use(bodyParser.urlencoded({ extended: false }))
app.use(cookieParser())
app.use(require('less-middleware')(path.join(__dirname, 'public')))
app.use(express.static(path.join(__dirname, 'public')))

app.use('/', index)
app.use('/info', info)
app.use('/exchange', exchange)
app.use('/about', about)
app.use('/seed', seed)

// catch 404 and forward to error handler
app.use(function(req, res, next) {
  var err = new Error('Not Found')
  err.status = 404
  next(err)
})

// error handler
app.use(function(err, req, res, next) {
  // set locals, only providing error in development
  res.locals.message = err.message
  res.locals.error = req.app.get('env') === 'development' ? err : {}

  // render the error page
  res.status(err.status || 500)
  res.render('error')
})

module.exports = app