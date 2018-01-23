from .settings import indb

inTrades = indb('trades')
inOrders = indb('orders')

def inOrder(ticker, exp, strike, dude, user, type, quant, price, action):
    data = [
    {
        'measurement': ticker,
        'tags': {
            'exp': exp
        },
        'fields': {
            'user': user,
            'type': type,
            'quant': quant,
            'asset': strike + '_' + dude,
            'price': price,
            'action': action
        }
    }]
    inOrders.write_points(data)

def inTrade(ticker, exp, strike, dude, user, oppUser, type, quant, price):
    data = [
    {
        'measurement': ticker,
        "tags": {
            'exp': exp
        },
        'fields': {
            'user': user,
            'oppUser': oppUser,
            'type': type,
            'quant': quant,
            'asset': strike + '_' + dude,
            'price': price
        }
    }]
    inTrades.write_points(data)

def outOrders(ticker, exp):
    cursor = inOrders.query('SELECT type, quant, asset, price, action, time FROM %s WHERE exp=\'%s\' ORDER BY time DESC LIMIT 100' % (ticker, exp), epoch='u').get_points()
    res = []
    for doc in cursor:
        res.append({'type': doc['type'], 'asset': doc['asset'], 'quant': doc['quant'], 'price': doc['price'], 'action': doc['action'], 'time': doc['time']})
    return res

def outTrades(ticker, exp):
    cursor = inTrades.query('SELECT type, quant, asset, price, time FROM %s WHERE exp=\'%s\' ORDER BY time DESC LIMIT 100' % (ticker, exp), epoch='u').get_points()
    res = []
    for doc in cursor:
        res.append({'type': doc['type'], 'asset': doc['asset'], 'quant': doc['quant'], 'price': doc['price'], 'time': doc['time']})
    return res