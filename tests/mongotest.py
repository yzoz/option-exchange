from pymongo import MongoClient
from bson.objectid import ObjectId
import time, random, json, math, scipy.stats, requests
client = MongoClient('localhost:27017')
client.admin.authenticate('ad', 'pass')
db = client.exchange
orders = db.orders

def findBest(type):
    cursor = orders.aggregate([
    {'$match': {'type': type}},
    {'$group': {'_id': '$asset',
                'price': {'$min': '$price'}
                }
    }])
    res = []
    for doc in cursor:
        res.append({'_id': doc['_id'], 'price': doc['price']})
    print(json.dumps(res, indent=1))

def getBestPrice(type, asset):
    if (type == 'sell'):
        priceOrder = 1
    else:
        priceOrder = -1
    cursor = orders.find_one({
    'type': type,
    'asset': asset,
    'price': {'$exists': True}
    }, sort=[('price', priceOrder)])
    #print(res)
    if cursor is None:
        return 0
    else:
        return cursor['price']


def getAll(type, asset):
    if (type == 'sell'):
        timeOrder = -1
    else:
        timeOrder = 1
    cursor = orders.find({
    'type': type,
    'asset': asset,
    }, sort=[('price', -1), ('time', timeOrder)])
    #print(json.dumps(res))
    res = []
    for doc in cursor:
        res.append({'user': doc['user'], 'quant': doc['quant'], 'price': doc['price'], 'time': doc['time']})
    print(json.dumps(res, indent=1))
        
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
    return cursor
    #for doc in res:
        #print(doc['user'], doc['quant'], doc['price'], doc['time'])

def sendLimit(user, type, quant, asset, price):
    times = time.time()
    cursor = orders.insert_one({
    'user': int(user),
    'type': type,
    'quant': int(quant),
    'asset': asset,
    'price': int(price),
    'time': times
    }).inserted_id
    if (cursor):
        return 'SendLimit: ' + str(times) + ' | ' + str(user) + ' | ' + type + ' | ' + str(quant) + ' | ' + asset + ' | ' + str(price) + '\n'
    
def editQuant(id, quant):
    cursor = orders.update_one({'_id': id}, {'$set': {'quant': quant}}).modified_count
    if (cursor == 1):
        return 'Edit: ' + str(cursor) + '\n'
    
def removeOrder(id):
    cursor = orders.delete_one({'_id': id}).deleted_count
    if (cursor == 1):
        return 'Remove: ' + str(cursor) + '\n'

def sendOrder(sex, user, type, quant, asset, price):
    output = 'LOG:::\n'
    output = output + 'WantFood: ' +  str(quant)  + '\n'
    if (type == 'sell'):
        oppType = 'buy'
    else:
        oppType = 'sell'
    bestPrice = getBestPrice(oppType, asset)
    #If I Sell, bestPrice (bid) must be < then my price, to place limit order, else I place market order
    #But if I want to buy, best ask must be > then my price, to send limit
    if (type == 'sell'):
        dir = price - bestPrice
    else:
        dir = bestPrice - price
    if (dir > 0):
        limit = sendLimit(user, type, quant, asset, price)
        output = output + limit
    else:
        machOrders = getLimit(oppType, asset, price)
        for oppOrder in machOrders:
            oppUser = oppOrder['user']
            oppQuant = oppOrder['quant']
            oppPrice = oppOrder['price']
            oppId = ObjectId(oppOrder['_id'])
            optTime = oppOrder['time']
            if (user == oppUser):
                remove = removeOrder(oppId)
                output = output + remove
                output = output + 'I\'m Stupid!\n'
                continue
            if (quant > oppQuant):
                output = output + 'Food: ' + ' | ' + str(oppUser) + ' | ' + str(oppQuant) + ' | ' + str(oppPrice) + ' | ' + str(optTime) + '\n'
                remove = removeOrder(oppId)
                output = output + remove
                quant-=oppQuant
                output = output + 'ToEat: ' + str(quant) + '\n'
            elif (quant == oppQuant):
                output = output + 'BestFood: ' + str(oppUser) + ' | ' + str(oppQuant) + ' | ' + str(oppPrice) + ' | ' + str(optTime) + '\n'
                remove = removeOrder(oppId)
                output = output + remove
                quant = 0
                break
            else:
                output = output + 'LastFood: ' + str(oppUser) + ' | ' + str(oppQuant) + ' | ' + str(oppPrice) + ' | ' + str(optTime) + '\n'
                oppQuant-=quant
                edit = editQuant(oppId, oppQuant)
                output = output + edit
                output = output + 'NotEat: ' + str(oppQuant) + '\n'
                quant = 0
                break
        if (quant > 0):
            limit = sendLimit(user, type, quant, asset, price)
            output = output + limit
    return output

def postOrders():
    orders.drop()
    K = 2500
    i = 0
    T = 'C'
    j = 1
    while j < 3:
        K = 2500
        while K <= 30000:
            i = 0
            if T == 'C':
                ko = 80000/K
            else:
                ko = K/800
            print(K, T, ko)
            while i <= 15:
                orders.insert_one({
                 'user': random.randrange(1, 5, 1),
                 'type': 'sell',
                 'quant': random.randrange(5, 10, 1),
                 'asset': str(K) + T,
                 'price': int(random.randrange(51, 100, 1) * ko),
                 'time': times + random.randrange(1, 100000, 1)
                 }).inserted_id
                orders.insert_one({
                 'user': random.randrange(1, 5, 1),
                 'type': 'buy',
                 'quant': random.randrange(5, 10, 1),
                 'asset': str(K) + T,
                 'price': int(random.randrange(5, 50, 1) * ko),
                 'time': times + random.randrange(1, 100000, 1)
                 }).inserted_id
                i+=1
            K+=2500
        T = 'P'
        j+=1

class Calculation():

    def d1(self, S, K, V, T):
        return (math.log(S / float(K)) + (V**2 / 2) * T) / (V * math.sqrt(T))

    def d2(self, S, K, V, T):
        return self.d1(S, K, V, T) - (V * math.sqrt(T))

    def theo(self, S, K, V, T, dT):
        if dT == 'C':
            return S * scipy.stats.norm.cdf(self.d1(S, K, V, T)) - K * scipy.stats.norm.cdf(self.d2(S, K, V, T))
        else:
            return K * scipy.stats.norm.cdf(-self.d2(S, K, V, T)) - S * scipy.stats.norm.cdf(-self.d1(S, K, V, T))

calc = Calculation()
S = 11000
T = 30/365
V = 70/100
def testOrders():
    #orders.drop()
    i = 1
    while i < 1000:
        K = random.randrange(2500, 32500, 2500)
        dT01 = random.randrange(0,2)
        if dT01 == 1:
            dT = 'C'
        else:
            dT = 'P'
        D01 = random.randrange(0,2)
        if D01 == 1:
            D = 'buy'
        else:
            D = 'sell'
        U = random.randrange(1, 5, 1)
        Q = random.randrange(1, 100, 1)
        theo = int(calc.theo(S, K, V, T, dT))
        if theo == 0:
            theo = K / 100
        theoMin = int(theo - theo * 0.75) + 1
        theoMax = int(theo + theo * 0.25) + 1
        P = random.randrange(theoMin, theoMax, 1)
        print('-----', U, D, Q, str(K) + dT, P, '-----')
        #send = sendOrder('SeXxX', U, D, Q, str(K) + dT, P)
        try:
            send = requests.post('https://api.yzoz.com:69/order', data = {
            'sex': 'SeXxX',
            'user': U,
            'type': D,
            'quant': Q,
            'asset': str(K) + dT,
            'price': P
            }, verify=False)
        except requests.exceptions.RequestException as e:
            print('Error: {}'.format(e))
        else:
            print(send.text)
        time.sleep(1)
        i=+1
        
#findBest('sell')
#findBest('buy')
#getAll('sell', '12500P')
#getAll('buy', '12500P')
#getLimit('sell', '12500P', 49)
#getLimit('buy', '12500P', 7)
#postOrders()
testOrders()
#print(getBestPrice('buy', '20000P'))
#print(sendOrder('SeXxX', 3, 'sell', 1, '22500P', 12000))
#getBestPrice(1, 'sell', '12500P')
#getBestPrice(1, 'buy', '12500P')
