'use strict'

// Вся клиентская логика торгового стола. Файл подключается последним (layout.pug),
// функции вызываются из inline-обработчиков в шаблонах (onclick), поэтому они
// объявлены в глобальной области — но с 'use strict' любое обращение к
// необъявленной переменной падает, что закрывает прежние «липкие» глобалы
// (задача ТЗ #26): out, token, name, asset, key, hmac, question, ... больше не
// протекают в window.

// Адрес API инжектится Express из API_URL (.env). Fallback — локальная разработка.
var apiServer = window.API_SERVER || 'http://localhost:6969'
var stateTimer = 5000
window.apiServer = apiServer

var TICKER = $('#ticker').val()
var EXP = $('#exp').val()
var TRADE = 0
var ORDER = 0
var currencys = ['ETH', 'BTC']

jQuery.fn.center = function () {
  this.css('top', Math.max(0, ($(window).height() - $(this).outerHeight()) / 2 + $(window).scrollTop()) + 'px')
  this.css('left', Math.max(0, ($(window).width() - $(this).outerWidth()) / 2 + $(window).scrollLeft()) + 'px')
  return this
}

function doPosition() {
  var deskHeight = $('#desk .content').height()
  $('#main .reheight .content').css('height', deskHeight + 'px')
  var topHeight = $('#form .content').height()
  $('#signin .content').css('height', topHeight + 'px')
}

function showMe(el) {
  $(el).show()
}

function hideMe(el) {
  $(el).hide()
}

function assetTitle(asset) {
  var splited = asset.split('_')
  var strike = splited[3]
  var dude = splited[4]
  var title = strike + '_' + dude
  return title
}

function convertDate(inDate) {
  function subDate(inNum) {
    return ('0' + inNum).substr(-2)
  }
  var date = new Date(parseInt(inDate / 1000))
  var month = subDate(date.getMonth() + 1)
  var day = subDate(date.getDate())
  var hours = subDate(date.getHours())
  var minutes = subDate(date.getMinutes())
  var seconds = subDate(date.getSeconds())
  var out = day + '.' + month + '&nbsp;|&nbsp;' + hours + ':' + minutes + ':' + seconds
  return out
}

function getMyKey() {
  var key = $('#userKey').val()
  return key
}

function getMyPassword() {
  var password = $('#userPassword').val()
  return password
}

function getHMAC(question) {
  var password = getMyPassword()
  var shaObjHMAC = new jsSHA('SHA3-512', 'TEXT')
  shaObjHMAC.setHMACKey(password, 'TEXT')
  shaObjHMAC.update(question)
  var hmac = shaObjHMAC.getHMAC('HEX')
  return hmac
}

// Единый показ сообщения/ошибки пользователю (задачи #16, #33, #34).
function showMessage(html) {
  $('#log .content').html(html)
  $('#log').show()
  $('#log').center()
}

// Единый обработчик AJAX-ошибок: API отдаёт реальные HTTP-коды (задача #16),
// поэтому неуспешный ответ нужно показать, а не молча терять (задача #33).
function showAjaxError(xhr) {
  var msg
  try {
    msg = JSON.parse(xhr.responseText).error.message
  } catch (e) {
    msg = xhr && xhr.status ? xhr.status + ' ' + (xhr.statusText || 'Error') : 'нет соединения с API'
  }
  showMessage('Error: ' + msg)
}

function genKey() {
  var possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
  var mask = 'XXXXX-XXXXX-XXXXX-XXXXX-X'
  var key = mask.replace(/X/g, function (char) {
    char = possible.charAt(Math.floor(Math.random() * possible.length))
    return char
  })
  $('#regKey').val(key)
}

function genSeed() {
  $.get('/seed', function (data) {
    $('#regSeed').val(data)
  }).fail(showAjaxError)
}

function signUp() {
  var key = $('#regKey').val()
  var seed = $('#regSeed').val()
  var password = $('#regPassword').val()
  var email = $('#regEmail').val()

  // Клиентская валидация (задача #34): пустые поля отсекаем до запроса.
  if (!key || !key.trim()) {
    return showMessage('Error: укажите Key (Gen Key)')
  }
  if (!seed || !seed.trim()) {
    return showMessage('Error: укажите Seed (Gen Seed)')
  }
  if (!password) {
    return showMessage('Error: задайте пароль')
  }

  var data = {
    key: key,
    seed: seed,
    password: password,
    email: email
  }
  $.ajax({
    type: 'POST',
    url: apiServer + '/signup',
    data: JSON.stringify(data),
    contentType: 'application/json',
    success: function (out) {
      showMessage(out)
    },
    error: showAjaxError
  })
}

function updateBlocks() {
  if ($('#my-orders').is(':visible')) {
    userOrders()
  }
  if ($('#my-contracts').is(':visible')) {
    userContracts()
  }
  if ($('#my-trades').is(':visible')) {
    userTrades()
  }
  if ($('#balances').is(':visible')) {
    userBalances()
  }
  if ($('#order-book').is(':visible')) {
    var asset = $('#order-book .title').text()
    orderBook(TICKER + '_' + EXP + '_' + asset)
  }
}

function getCounters() {
  $.getJSON(apiServer + '/counters/' + TICKER, function (data) {
    $('#counters').html(
      'HV:  <a href="/info/volatility/eth/btc/">' +
        Number((data[0].vola * 100).toFixed(2)) +
        '</a> | Price: <a href="https://www.bybit.com/spot/ETHBTC">' +
        data[0].price +
        '</a>'
    )
  }).fail(showAjaxError)
}

function state() {
  $.getJSON(apiServer + '/state', function (data) {
    var lastTrade = data[0][TICKER + '_' + EXP + '_TRADE']
    var lastOrder = data[0][TICKER + '_' + EXP + '_ORDER']
    if (typeof lastTrade != 'undefined' && lastTrade > TRADE) {
      last()
      tradeRiver()
      TRADE = lastTrade
    }
    if (typeof lastOrder != 'undefined' && lastOrder > ORDER) {
      best()
      orderRiver()
      ORDER = lastOrder
    }
  }).fail(showAjaxError)
}

function userContracts() {
  var key = getMyKey()
  var question = 'contracts'
  var hmac = getHMAC(question)
  var data = {
    user: key,
    password: getMyPassword(),
    hmac: hmac,
    question: question
  }
  $.ajax({
    type: 'POST',
    url: apiServer + '/user',
    data: JSON.stringify(data),
    contentType: 'application/json',
    success: function (out, status, xhr) {
      var ct = xhr.getResponseHeader('content-type') || ''
      if (ct.indexOf('json') > -1) {
        var contracts = '<table><tr><td>Asset</td><td>Q</td><td>Price</td><td>Amount</td><td>P/L</td></tr>'
        out = JSON.parse(JSON.stringify(out))
        $.each(out, function (key, val) {
          var thisClass
          if (val.pl < 0) {
            thisClass = 'sell'
          } else {
            thisClass = 'buy'
          }
          var contract =
            '<tr class="' +
            thisClass +
            '"><td>' +
            val.asset +
            '</td><td>' +
            val.quant +
            '</td><td>' +
            val.price +
            '</td><td>' +
            val.amount +
            '</td><td>' +
            val.pl +
            '</td></tr>'
          contracts = contracts + contract
        })
        contracts = contracts + '</table>'
        $('#my-contracts .content').html(contracts)
        $('#my-contracts').show()
      }
      if (ct.indexOf('html') > -1) {
        showMessage(out)
      }
    },
    error: showAjaxError
  })
}

function userBalances() {
  var key = getMyKey()
  var question = 'balances'
  var hmac = getHMAC(question)
  var data = {
    user: key,
    password: getMyPassword(),
    hmac: hmac,
    question: question
  }
  $.ajax({
    type: 'POST',
    url: apiServer + '/user',
    data: JSON.stringify(data),
    contentType: 'application/json',
    success: function (out, status, xhr) {
      var ct = xhr.getResponseHeader('content-type') || ''
      if (ct.indexOf('json') > -1) {
        var balances =
          '<table><tr><td>Сurrency</td><td>Own</td><td>Sell Orders</td><td>Buy Orders</td><td>Sell Contracts</td><td>Buy Contracts</td><td>Prize</td><td>Realised</td><td>Available</td></tr>'
        out = JSON.parse(JSON.stringify(out))
        for (var currency in currencys) {
          var unit = currencys[currency]
          var balance =
            '<tr><td>' +
            unit +
            '</td><td>' +
            out.own[unit] +
            '</td><td>' +
            out.orders.sell[unit] +
            '</td><td>' +
            out.orders.buy[unit] +
            '</td><td>' +
            out.contracts.sell[unit] +
            '</td><td>' +
            out.contracts.buy[unit] +
            '</td><td>' +
            out.prize[unit] +
            '</td><td>' +
            out.realised[unit] +
            '</td><td>' +
            out.available[unit] +
            '</td></tr>'
          balances = balances + balance
        }
        balances = balances + '</table>'
        $('#balances .content').html(balances)
        $('#balances').show()
      }
      if (ct.indexOf('html') > -1) {
        showMessage(out)
      }
    },
    error: showAjaxError
  })
}

function userOrders() {
  var key = getMyKey()
  var question = 'orders'
  var hmac = getHMAC(question)
  var data = {
    user: key,
    password: getMyPassword(),
    hmac: hmac,
    question: question
  }
  $.ajax({
    type: 'POST',
    url: apiServer + '/user',
    data: JSON.stringify(data),
    contentType: 'application/json',
    success: function (out, status, xhr) {
      var ct = xhr.getResponseHeader('content-type') || ''
      if (ct.indexOf('json') > -1) {
        var orders = '<table><tr><td>Date</td><td>Asset</td><td>Q</td><td>Price</td><td>Amount</td><td></td></tr>'
        out = JSON.parse(JSON.stringify(out))
        $.each(out, function (key, val) {
          var order =
            '<tr class="' +
            val.type +
            '"><td>' +
            convertDate(val.time) +
            '</td><td>' +
            val.asset +
            '</td><td>' +
            +val.quant +
            '</td><td>' +
            val.price +
            '</td><td>' +
            val.price * val.quant +
            '</td><td><img src="/images/remove.png" alt="R" class="icon" title="Remove" onclick="orderRemove(\'' +
            val.id +
            '\')" /> <img src="/images/edit.png" alt="E" class="icon" title="Edit" onclick="orderEdit(\'' +
            val.id +
            "', " +
            val.quant +
            ', ' +
            val.price +
            ')" /></td></tr>'
          orders = orders + order
        })
        orders = orders + '</table>'
        $('#my-orders .content').html(orders)
        $('#my-orders').show()
      }
      if (ct.indexOf('html') > -1) {
        showMessage(out)
      }
    },
    error: showAjaxError
  })
}

function userTrades() {
  var key = getMyKey()
  var question = 'trades'
  var hmac = getHMAC(question)
  var data = {
    user: key,
    password: getMyPassword(),
    hmac: hmac,
    question: question
  }
  $.ajax({
    type: 'POST',
    url: apiServer + '/user',
    data: JSON.stringify(data),
    contentType: 'application/json',
    success: function (out, status, xhr) {
      var ct = xhr.getResponseHeader('content-type') || ''
      if (ct.indexOf('json') > -1) {
        var trades = '<table><tr><td>Date</td><td>Asset</td><td>Q</td><td>Price</td><td>Amount</td></tr>'
        out = JSON.parse(JSON.stringify(out))
        $.each(out, function (key, val) {
          var thisClass
          if (val.quant < 0) {
            thisClass = 'sell'
          } else {
            thisClass = 'buy'
          }
          var trade =
            '<tr class="' +
            thisClass +
            '"><td>' +
            convertDate(val.time) +
            '</td><td>' +
            val.asset +
            '</td><td>' +
            +val.quant +
            '</td><td>' +
            val.price +
            '</td><td>' +
            val.amount +
            '</td></tr>'
          trades = trades + trade
        })
        trades = trades + '</table>'
        $('#my-trades .content').html(trades)
        $('#my-trades').show()
      }
      if (ct.indexOf('html') > -1) {
        showMessage(out)
      }
    },
    error: showAjaxError
  })
}

// Разбор числового поля формы: целое > 0 либо null (невалидно).
function positiveInt(raw) {
  var n = parseInt(raw, 10)
  if (isNaN(n) || n <= 0) {
    return null
  }
  return n
}

function orderSend(type) {
  var key = getMyKey()
  var action = 'send'
  var dude = $('.type:checked').val()

  // Клиентская валидация ордера (задача #34): выбраны CALL/PUT, цена и объём
  // — положительные целые. Иначе запрос не отправляем.
  if (!dude) {
    return showMessage('Error: выберите CALL или PUT')
  }
  var price = positiveInt($('#price').val())
  if (price === null) {
    return showMessage('Error: цена должна быть целым числом > 0')
  }
  var quant = positiveInt($('#quant').val())
  if (quant === null) {
    return showMessage('Error: количество должно быть целым числом > 0')
  }

  var asset = TICKER + '_' + EXP + '_' + $('#strike').val() + '_' + dude
  var question = {
    action: action,
    type: type,
    quant: quant,
    asset: asset,
    price: price
  }
  var toHMAC = action + type + quant + asset + price
  var hmac = getHMAC(toHMAC)
  var data = {
    user: key,
    password: getMyPassword(),
    hmac: hmac,
    question: question
  }
  $.ajax({
    type: 'POST',
    url: apiServer + '/order',
    data: JSON.stringify(data),
    contentType: 'application/json',
    success: function (out) {
      showMessage(out.replace(/\n/g, '<br />'))
      updateBlocks()
    },
    error: showAjaxError
  })
}

function orderRemove(id) {
  var key = getMyKey()
  var action = 'remove'
  var question = {
    action: action,
    id: id
  }
  var toHMAC = action + id
  var hmac = getHMAC(toHMAC)
  var data = {
    user: key,
    password: getMyPassword(),
    hmac: hmac,
    question: question
  }
  $.ajax({
    type: 'POST',
    url: apiServer + '/order',
    data: JSON.stringify(data),
    contentType: 'application/json',
    success: function (out) {
      showMessage(out.replace(/\n/g, '<br />'))
      updateBlocks()
    },
    error: showAjaxError
  })
}

function orderEdit(id, quant, price) {
  var newQuant = prompt('New quantity:', quant)
  if (newQuant === null) {
    return
  }
  var newPrice = prompt('New price:', price)
  if (newPrice === null) {
    return
  }
  newQuant = positiveInt(newQuant)
  newPrice = positiveInt(newPrice)
  if (newQuant === null || newPrice === null) {
    return showMessage('Error: новые цена и количество должны быть целыми > 0')
  }
  var key = getMyKey()
  var action = 'edit'
  var question = {
    action: action,
    id: id,
    quant: newQuant,
    price: newPrice
  }
  // HMAC-подпись правки: action + id + quant + price (см. api/app.py).
  var toHMAC = action + id + newQuant + newPrice
  var hmac = getHMAC(toHMAC)
  var data = {
    user: key,
    password: getMyPassword(),
    hmac: hmac,
    question: question
  }
  $.ajax({
    type: 'POST',
    url: apiServer + '/order',
    data: JSON.stringify(data),
    contentType: 'application/json',
    success: function (out) {
      showMessage(out.replace(/\n/g, '<br />'))
      updateBlocks()
    },
    error: showAjaxError
  })
}

function orderRiver() {
  $.getJSON(apiServer + '/river/orders/' + TICKER + '/' + EXP, function (data) {
    var orders = '<table><tr><td>Action</td><td>Date</td><td>Asset</td><td>Q</td><td>Price</td></tr>'
    $.each(data, function (key, val) {
      var order =
        '<tr class="' +
        val.type +
        '"><td>' +
        val.action +
        '</td><td>' +
        convertDate(val.time) +
        '</td><td>' +
        val.asset +
        '</td><td>' +
        val.quant +
        '</td><td>' +
        val.price +
        '</td></tr>'
      orders = orders + order
    })
    orders = orders + '</table>'
    $('#orders .content').html(orders)
  }).fail(showAjaxError)
}

function tradeRiver() {
  $.getJSON(apiServer + '/river/trades/' + TICKER + '/' + EXP, function (data) {
    var trades = '<table><tr><td>Date</td><td>Asset</td><td>Q</td><td>Price</td></tr>'
    $.each(data, function (key, val) {
      var trade =
        '<tr class="' +
        val.type +
        '"><td>' +
        convertDate(val.time) +
        '</td><td>' +
        val.asset +
        '</td><td>' +
        val.quant +
        '</td><td>' +
        val.price +
        '</td></tr>'
      trades = trades + trade
    })
    trades = trades + '</table>'
    $('#trades .content').html(trades)
  }).fail(showAjaxError)
}

function orderBook(asset) {
  $('#order-book .content').html('')
  $('#order-book').show()
  var title = assetTitle(asset)
  $.getJSON(apiServer + '/orders/' + asset, function (data) {
    $('#order-book .title').text(title)
    var orders = '<table cellspacing="1">'
    $.each(data, function (key, val) {
      var order = '<tr class="' + val.type + '"><td>' + val.price + '</td><td>' + val.quant + '</td></tr>'
      orders = orders + order
    })
    orders = orders + '</table>'
    $('#order-book .content').html(orders)
  }).fail(showAjaxError)
}

function best() {
  $.getJSON(apiServer + '/best/' + TICKER + '/' + EXP, function (data) {
    $('.price').each(function () {
      $(this).text('')
    })
    $.each(data, function (key, val) {
      $('#' + val.asset + '_' + val.type).text(val.price)
    })
  }).fail(showAjaxError)
}

function theo() {
  $.getJSON(apiServer + '/theo/' + TICKER + '/' + EXP, function (data) {
    $('.theo').each(function () {
      $(this).text('')
    })
    $.each(data, function (key, val) {
      $('#' + val.asset + '_theo').text(val.theo)
    })
  }).fail(showAjaxError)
}

function last() {
  $.getJSON(apiServer + '/last/' + TICKER + '/' + EXP, function (data) {
    $('.last').each(function () {
      $(this).text('')
    })
    $.each(data, function (key, val) {
      $('#' + val.asset + '_last').text(val.last)
    })
  }).fail(showAjaxError)
}

$(document).ready(function () {
  best()
  theo()
  last()
  orderRiver()
  tradeRiver()
  getCounters()
  $('#exchange-menu').html(
    'Sign&nbsp;<span class="pseudoLink" onclick="showMe(\'#form\'); showMe(\'#signin\'); doPosition()">In</span>&nbsp;/&nbsp;<span class="pseudoLink" onclick="showMe(\'#signup\')">Up</span>&nbsp;|&nbsp'
  )
  setTimeout(function () {
    doPosition()
  }, 2500)
  setInterval(function () {
    state()
  }, stateTimer)
  setInterval(function () {
    theo()
    getCounters()
  }, 60000)
})
