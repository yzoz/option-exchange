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

def editQuant(ticker, exp, strike, dude, id, user, type, quant, asset, price):
    cursor = orders.update_one({'_id': id}, {'$set': {'quant': quant}}).modified_count
    if cursor == 1:
        inOrder(ticker, exp, strike, dude, user, type, quant, price, 'EDIT')
        return 'Edit: ' + str(cursor) + '\n'

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