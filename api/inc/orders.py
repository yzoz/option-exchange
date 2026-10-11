from bson.objectid import ObjectId
from .settings import modb
from .influx import inOrder
from .mc import setState
from .utils import getTime

orders = modb().orders

#Get ID of order
def getOrder(id):
    cursor = orders.find_one({'_id': id})
    if cursor is None:
        return 0
    else:
        return cursor

#Get ordrers mached the price < or >
def getLimit(type, asset, price):
    if (type == 'sell'):
        dir = '$lte'
        priceOrder = 1
    else:
        dir = '$gte'
        priceOrder = -1
    cursor = orders.find({
    'type': type,
    'asset': asset,
    'price': {dir: price}
    }, sort=[('price', priceOrder), ('time', 1)])
    if (cursor):
        return cursor

#Get best Bid or Ask of Asset
def getBestPrice(type, asset):
    if type == 'sell':
        priceOrder = 1
    else:
        priceOrder = -1
    cursor = orders.find_one({
    'type': type,
    'asset': asset,
    'price': {'$exists': True}
    }, sort=[('price', priceOrder)])
    if cursor is None:
        return 0
    else:
        return cursor['price']

#Order Book
def getAsset(type, asset):
    cursor = orders.aggregate([
    {'$match': {'$and': [{'type': type},{'asset': asset}]}},
    {'$group': {'_id': '$price',
                'quant': {'$sum': '$quant'},
                'type': {'$last': '$type'}
                }
    },
    {'$sort': {'_id': -1}}
    ])
    res = []
    for doc in cursor:
        res.append({'price': doc['_id'], 'quant': doc['quant'] , 'type': doc['type']})
    return res

"""USER ACTIONS"""

def matchOrder(ticker, exp, strike, dude, oppType, asset, price, quant, user):
    """Атомарно забрать у встречной заявки min(quant, её объём).

    Возвращает (заявка_до_изменения, взятый_объём) или (None, 0).
    Заявка удаляется/уменьшается условным запросом (по _id + текущему quant),
    поэтому одну заявку нельзя выкупить дважды — в т.ч. из параллельных
    процессов. Свои заявки (user) исключены — самосведение запрещено.
    """
    if oppType == 'sell':
        dir = '$lte'
        priceOrder = 1
    else:
        dir = '$gte'
        priceOrder = -1
    while True:
        cand = orders.find_one({
            'type': oppType,
            'asset': asset,
            'user': {'$ne': user},
            'price': {dir: price}
        }, sort=[('price', priceOrder), ('time', 1)])
        if cand is None:
            return None, 0
        candId = cand['_id']
        oppQuant = cand['quant']
        if oppQuant <= quant:
            # Забираем заявку целиком. Условие по quant ловит гонку: если другой
            # процесс успел её изменить — find_one_and_delete вернёт None, повторяем.
            taken = orders.find_one_and_delete({'_id': candId, 'quant': oppQuant})
            if taken is None:
                continue
            inOrder(ticker, exp, strike, dude, taken['user'], oppType, oppQuant, taken['price'], 'REMOVE')
            setState(ticker, exp, 'ORDER', getTime())
            return taken, oppQuant
        # Заявка больше нашего объёма — уменьшаем её на взятый объём.
        taken = orders.find_one_and_update(
            {'_id': candId, 'quant': oppQuant},
            {'$set': {'quant': oppQuant - quant}})
        if taken is None:
            continue
        inOrder(ticker, exp, strike, dude, taken['user'], oppType, quant, taken['price'], 'EDIT')
        setState(ticker, exp, 'ORDER', getTime())
        return taken, quant

def sendLimit(ticker, exp, strike, dude, user, type, quant, asset, price):
    times = getTime()
    cursor = orders.insert_one({
    'user': user,
    'type': type,
    'quant': quant,
    'asset': asset,
    'price': price,
    'time': times,
    'ticker': ticker,
    'exp': exp,
    'strike': strike,
    'dude': dude
    }).inserted_id
    if (cursor):
        inOrder(ticker, exp, strike, dude, user, type, quant, price, 'SEND')
        setState(ticker, exp, 'ORDER', getTime())
        return 'SendLimit: ' + str(times) + ' | User ' + str(user) + ' ' + type + ' ' + str(quant) + ' of ' + asset + ' for ' + str(price) + '\n'
    else:
        return 'Failed to send Order\n'

def editOrder(ticker, exp, strike, dude, id, user, type, quant, asset, price):
    # Правка только собственной заявки: фильтр по _id И user — чужие не тронуть.
    doc = orders.find_one_and_update(
        {'_id': id, 'user': user},
        {'$set': {'quant': quant, 'price': price}})
    if doc is None:
        return None
    inOrder(ticker, exp, strike, dude, user, type, quant, price, 'EDIT')
    setState(ticker, exp, 'ORDER', getTime())
    return 'Edit: User ' + str(user) + ' ' + type + ' ' + str(quant) + ' of ' + asset + ' for ' + str(price) + '\n'

def removeOrder(ticker, exp, strike, dude, id, user, type, quant, asset, price):
    cursor = orders.delete_one({'_id': id}).deleted_count
    if cursor == 1:
        inOrder(ticker, exp, strike, dude, user, type, quant, price, 'REMOVE')
        setState(ticker, exp, 'ORDER', getTime())
        return 'Remove: order of User ' + str(user) + ' ' + type + ' ' + str(quant) + ' of ' + asset + ' for ' + str(price) + '\n'
    else:
        return 'Failed to remove Order\n'

#Get All orders of User
def userOrders(user):
    cursor = orders.find({
    'user': user
    }, sort=[('time', -1)])
    res = []
    for doc in cursor:
        res.append({'id': str(ObjectId(doc['_id'])), 'type': doc['type'], 'asset': doc['asset'], 'quant': doc['quant'], 'price': doc['price'], 'time': doc['time']})
    return res

"""FOR BALANCES"""

#Get SUM of but or sell orders of user
def getOrders(user, type):
    cursor = orders.aggregate([
    {'$match':  {'$and': [{'type': type},{'user': user}]}},
    {'$group': {'_id': '$asset',
                'quant': {'$sum': '$quant'}
                }
    },
    {'$sort': {'_id': -1}}
    ])
    return cursor

#Get Array of Assets with orders
def alreadyOrders(user, type):
    cursor = getOrders(user, type)
    already = {}
    for doc in cursor:
        if doc['quant']:
            already[doc['_id']] = doc['quant']
    return already
