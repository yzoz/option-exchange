var host = window.location.hostname;

if (host == 'localhost') {
    var apiServer = 'http://localhost:69';
    var stateTimer = 5000;
}
else {
    var apiServer = 'https://yzoz.com:8080';
    var stateTimer = 1000;
}

var TICKER = $('#ticker').val();
var EXP = $('#exp').val();
var TRADE = 0;
var ORDER = 0;

var currencys = ['ETH', 'BTC']

jQuery.fn.center = function() {
    this.css("top", Math.max(0, (($(window).height() - $(this).outerHeight()) / 2) + $(window).scrollTop()) + "px");
    this.css("left", Math.max(0, (($(window).width() - $(this).outerWidth()) / 2) + $(window).scrollLeft()) + "px");
    return this;
}

function doPosition(){
    var deskHeight = $('#desk .content').height();
    $('#main .reheight .content').css('height', deskHeight + 'px');
    var topHeight = $('#form .content').height();
    $('#signin .content').css('height', topHeight + 'px');
}

function showMe(el){
    $(el).show();
}

function hideMe(el){
    $(el).hide();
}

function assetTitle(asset) {
    splited = asset.split('_');
    strike = splited[3];
    dude = splited[4];
    title = strike + '_' + dude;
    return title;
}

function convertDate(inDate) {
    function subDate(inNum) {
        return ('0' + inNum).substr(-2)
    }
    var date = new Date(parseInt(inDate / 1000));
    var month = subDate(date.getMonth() + 1);
    var day = subDate(date.getDate());
    var hours = subDate(date.getHours());
    var minutes = subDate(date.getMinutes());
    var seconds = subDate(date.getSeconds());
    out = day + '.' + month + '&nbsp;|&nbsp;' + hours + ':' + minutes + ':' + seconds
    return out
}

function getMyKey() {
    var key = $('#userKey').val();
    return key;
}

function getMySeed() {
    var seed = $('#userID').val();
    return seed;
}

function getHMAC(question) {
    seed = getMySeed();
    var shaObjHMAC = new jsSHA('SHA3-512', 'TEXT');
    shaObjHMAC.setHMACKey(seed, 'TEXT');
    shaObjHMAC.update(question);
    var hmac = shaObjHMAC.getHMAC("HEX");
    return hmac;
}

function genKey(){
    var possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    var mask = 'XXXXX-XXXXX-XXXXX-XXXXX-X';
    var key = mask.replace(/X/g,
        function(char) {
            char = possible.charAt(Math.floor(Math.random() * possible.length));
            return char;
        }
    );
    $('#regKey').val(key);
}

function genSeed() {
    $.get("/seed", function(data) {
        $("#regSeed" ).val(data);
    });
}

function signUp() {
    key = $('#regKey').val();
    seed = $('#regSeed').val();
    email = $('#regEmail').val();
    data = {
        'key': key,
        'seed': seed,
        'email': email
    };
    $.ajax({
        type: 'POST',
        url: apiServer + '/signup', 
        data: JSON.stringify(data),
        contentType: 'application/json',
        success: function(out) {
            $('#log .content').html(out);
            $('#log').show();
            $('#log').center();
        }
    })
}

function updateBlocks() {
    if ($('#my-orders').is(":visible")){
        userOrders();
    }
    if ($('#my-contracts').is(":visible")){
        userContracts();
    }
    if ($('#my-trades').is(":visible")){
        userTrades();
    }
    if ($('#balances').is(":visible")){
        userBalances();
    }
    if ($('#order-book').is(":visible")){
        asset = $('#order-book .title').text();
        orderBook(TICKER + '_' + EXP + '_' + asset);
    }
}

function getCounters() {
    $.getJSON(apiServer + '/counters/' + TICKER, function(data) {
        $('#counters').html('HV:  <a href="/info/volatility/eth/btc/">' + Number((data[0].vola * 100).toFixed(2)) + '</a> | Price: <a href="https://poloniex.com/exchange#btc_eth">' + data[0].price + '</a>');
    })
}

function state() {
    $.getJSON(apiServer + '/state', function(data) {
        var lastTrade = data[0][TICKER + '_' + EXP + '_TRADE'];
        var lastOrder = data[0][TICKER + '_' + EXP + '_ORDER'];
        if (typeof lastTrade != 'undefined' && lastTrade > TRADE) {
            last();
            tradeRiver();
            TRADE = lastTrade;
        }
        if (typeof lastOrder != 'undefined' && lastOrder > ORDER) {
            best();
            orderRiver();
            ORDER = lastOrder;
        }
    })  
}

function userContracts() {
    key = getMyKey();
    question = 'contracts';
    hmac = getHMAC(question);
    data = {
        'user': key,
        'hmac': hmac,
        'question': question
    };
    $.ajax({
        type: 'POST',
        url: apiServer + '/user',
        data: JSON.stringify(data),
        contentType: 'application/json',
        success: function(out, status, xhr) {
            var ct = xhr.getResponseHeader("content-type") || "";
            if (ct.indexOf('json') > -1) {
                var contracts = '<table><tr><td>Asset</td><td>Q</td><td>Price</td><td>Amount</td><td>P/L</td></tr>';
                out = JSON.parse(JSON.stringify(out));
                $.each(out, function(key, val) {
                    if (val.pl < 0) {
                        var thisClass = 'sell';
                    }
                    else {
                        var thisClass = 'buy';
                    }
                    contract = '<tr class="' + thisClass + '"><td>' + val.asset + '</td><td>' + val.quant + '</td><td>' + val.price + '</td><td>' + val.amount + '</td><td>' + val.pl + '</td></tr>';
                    contracts = contracts + contract;
                });
                contracts = contracts + '</table>';
                $('#my-contracts .content').html(contracts);
                $('#my-contracts').show();
            }
            if (ct.indexOf('html') > -1) {
                $('#log .content').html(out);
                $('#log').show();
                $('#log').center();
            }
        }
    })
}

function userBalances() {
    key = getMyKey();
    question = 'balances';
    hmac = getHMAC(question);
    data = {
        'user': key,
        'hmac': hmac,
        'question': question
    };
    $.ajax({
        type: 'POST',
        url: apiServer + '/user',
        data: JSON.stringify(data),
        contentType: 'application/json',
        success: function(out, status, xhr) {
            var ct = xhr.getResponseHeader("content-type") || "";
            if (ct.indexOf('json') > -1) {
                var balances = '<table><tr><td>Сurrency</td><td>Own</td><td>Sell Orders</td><td>Buy Orders</td><td>Sell Contracts</td><td>Buy Contracts</td><td>Prize</td><td>Realised</td><td>Available</td></tr>';
                out = JSON.parse(JSON.stringify(out));
                for(currency in currencys) {
                    balance = '<tr><td>' + currencys[currency] + '</td><td>' + out.own[currencys[currency]] + '</td><td>' + out.orders.sell[currencys[currency]] + '</td><td>' + out.orders.buy[currencys[currency]] + '</td><td>' + out.contracts.sell[currencys[currency]] + '</td><td>' + out.contracts.buy[currencys[currency]] + '</td><td>' + out.prize[currencys[currency]] + '</td><td>' + out.realised[currencys[currency]] + '</td><td>' + out.available[currencys[currency]] + '</td></tr>';
                    balances = balances + balance;
                }
                balances = balances + '</table>';
                $('#balances .content').html(balances);
                $('#balances').show();
            }
            if (ct.indexOf('html') > -1) {
                $('#log .content').html(out);
                $('#log').show();
                $('#log').center();
            }
        }
    })
}

function userOrders() {
    key = getMyKey();
    question = 'orders';
    hmac = getHMAC(question);
    data = {
        'user': key,
        'hmac': hmac,
        'question': question
    };
    $.ajax({
        type: 'POST',
        url: apiServer + '/user',
        data: JSON.stringify(data),
        contentType: 'application/json',
        success: function(out, status, xhr) {
            var ct = xhr.getResponseHeader("content-type") || "";
            if (ct.indexOf('json') > -1) {
                var orders = '<table><tr><td>Date</td><td>Asset</td><td>Q</td><td>Price</td><td>Amount</td><td></td></tr>';
                out = JSON.parse(JSON.stringify(out));
                $.each(out, function(key, val) {
                    order = '<tr class="' + val.type + '"><td>' + convertDate(val.time) + '</td><td>' + val.asset + '</td><td>' + + val.quant + '</td><td>' + val.price + '</td><td>' + val.price * val.quant + '</td><td><img src="/images/remove.png" alt="R" class="icon" title="Remove" onclick="orderRemove(\'' + val.id + '\')" /></td></tr>';
                    //<img src="/images/edit.png" alt="E" class="icon" title="Edit"onclick="orderEdit(' + val.id + ')" />
                    orders = orders + order;
                });
                orders = orders + '</table>';
                $('#my-orders .content').html(orders);
                $('#my-orders').show();
            }
            if (ct.indexOf('html') > -1) {
                $('#log .content').html(out);
                $('#log').show();
                $('#log').center();
            }
        }
    })
}

function userTrades() {
    key = getMyKey();
    question = 'trades';
    hmac = getHMAC(question);
    data = {
        'user': key,
        'hmac': hmac,
        'question': question
    };
    $.ajax({
        type: 'POST',
        url: apiServer + '/user',
        data: JSON.stringify(data),
        contentType: 'application/json',
        success: function(out, status, xhr) {
            var ct = xhr.getResponseHeader("content-type") || "";
            if (ct.indexOf('json') > -1) {
                var trades = '<table><tr><td>Date</td><td>Asset</td><td>Q</td><td>Price</td><td>Amount</td></tr>';
                out = JSON.parse(JSON.stringify(out));
                $.each(out, function(key, val) {
                    if (val.quant < 0) {
                        var thisClass = 'sell';
                    }
                    else {
                        var thisClass = 'buy';
                    }
                    trade = '<tr class="' + thisClass + '"><td>' + convertDate(val.time) + '</td><td>' + val.asset + '</td><td>' + + val.quant + '</td><td>' + val.price + '</td><td>' + val.amount + '</td></tr>';
                    trades = trades + trade;
                });
                trades = trades + '</table>';
                $('#my-trades .content').html(trades);
                $('#my-trades').show();
            }
            if (ct.indexOf('html') > -1) {
                $('#log .content').html(out);
                $('#log').show();
                $('#log').center();
            }
        }
    })
}

function orderSend(type, asset) {
    key = getMyKey();
    action = 'send';
    asset = TICKER + '_' + EXP + '_' + $('#strike').val() + '_' + $('.type:checked').val();
    price = $('#price').val();
    quant = $('#quant').val();
    question = {
        action: action,
        type: type,
        quant: quant,
        asset: asset,
        price: price 
    };
    toHMAC = action + type + quant + asset + price;
    hmac = getHMAC(toHMAC);
    data = {
        'user': key,
        'hmac': hmac,
        'question': question
    };
    $.ajax({
        type: 'POST',
        url: apiServer + '/order', 
        data: JSON.stringify(data),
        contentType: 'application/json',
        success: function(out) {
            $('#log .content').html(out.replace(/\n/g, '<br />'))
            $('#log').show();
            $('#log').center();
            updateBlocks();
        }
    })
}

function orderRemove(id) {
    key = getMyKey();
    action = 'remove';
    question = {
        action: action,
        id: id 
    };
    toHMAC = action + id;
    hmac = getHMAC(toHMAC);
    data = {
        'user': key,
        'hmac': hmac,
        'question': question
    };
    $.ajax({
        type: 'POST',
        url: apiServer + '/order', 
        data: JSON.stringify(data),
        contentType: 'application/json',
        success: function(out) {
            $('#log .content').html(out.replace(/\n/g, '<br />'))
            $('#log').show();
            $('#log').center();
            updateBlocks();
        }
    })
}

function orderRiver() {
    $.getJSON(apiServer + '/river/orders/' + TICKER + '/' + EXP, function(data) {
        var orders = '<table><tr><td>Action</td><td>Date</td><td>Asset</td><td>Q</td><td>Price</td></tr>';
        $.each(data, function(key, val) {
            order = '<tr class="' + val.type + '"><td>' + val.action + '</td><td>' + convertDate(val.time) + '</td><td>' + val.asset + '</td><td>' + val.quant + '</td><td>' + val.price + '</td></tr>';
            orders = orders + order;
        });
        orders = orders + '</table>';
        $('#orders .content').html(orders);
    })
}

function tradeRiver() {
    $.getJSON(apiServer + '/river/trades/' + TICKER + '/' + EXP, function(data) {
        var trades = '<table><tr><td>Date</td><td>Asset</td><td>Q</td><td>Price</td></tr>';
        $.each(data, function(key, val) {
            trade = '<tr class="' + val.type + '"><td>' + convertDate(val.time) + '</td><td>' + val.asset + '</td><td>' + val.quant + '</td><td>' + val.price + '</td></tr>';
            trades = trades + trade;
        });
        trades = trades + '</table>';
        $('#trades .content').html(trades);
    })
}

function orderBook(asset) {
    $('#order-book .content').html('');
    $('#order-book').show();
    title = assetTitle(asset);
    $.getJSON(apiServer + '/orders/' + asset, function(data) {
        $('#order-book .title').text(title);
        var orders = '<table cellspacing="1">';
        $.each(data, function(key, val) {
            order= '<tr class="' + val.type + '"><td>' + val.price + '</td><td>' + val.quant + '</td></tr>';
            orders = orders + order;
        });
        orders = orders + '</table>';
        $('#order-book .content').html(orders);
    })
}
//$('[id^="ar"]').each(function(){})

function best() {
    $.getJSON(apiServer + '/best/' + TICKER + '/' + EXP, function(data) {
        $('.price').each(function() {
            $(this).text('');
        });
        $.each(data, function(key, val) {
            $('#' + val.asset + '_' + val.type).text(val.price);
        })
    })
}

function theo() {
    $.getJSON(apiServer + '/theo/' + TICKER + '/' + EXP, function(data) {
        $('.theo').each(function() {
            //id = $(this).attr("id");
            $(this).text('');
        });
        $.each(data, function(key, val) {
            $('#' + val.asset + '_theo').text(val.theo);
        })
    })
}

function last() {
    $.getJSON(apiServer + '/last/' + TICKER + '/' + EXP, function(data) {
        $('.last').each(function() {
            $(this).text('');
        });
        $.each(data, function(key, val) {
            $('#' + val.asset + '_last').text(val.last);
        })
    })
}

$(document).ready(function() {
    best();
    theo();
    last();
    orderRiver();
    tradeRiver();
    getCounters()
    /*
    $('#order-book .show-hide').on('click', function() {
        $('#order-book .content').slideToggle();
    });
    $('#log .show-hide').on('click', function() {
        $('#log').hide();
    });
    //$('#order-book').draggable({handle:'.header'});
    */
    $('#exchange-menu').html('Sign&nbsp;<span class="pseudoLink" onclick="showMe(\'#form\'); showMe(\'#signin\'); doPosition()">In</span>&nbsp;/&nbsp;<span class="pseudoLink" onclick="showMe(\'#signup\')">Up</span>&nbsp;|&nbsp');
    setTimeout(function() { 
        doPosition();
    }, 2500);
    setInterval(function() { 
        state();
    }, stateTimer);
    setInterval(function() { 
        theo();
        getCounters();
    }, 60000);
});