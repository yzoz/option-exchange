from .settings import modb
from .contracts import getContracts, alreadyContracts
from .utils import splitAsset
from .mc import getCurrencys
import math

orders = modb().orders
users = modb().users
contracts = modb().contracts

currencys = getCurrencys()

def allUsers():
    cursor = users.find({})
    return cursor

def checkUser(userHash):
    cursor = users.find_one({
    'hash': userHash
    })
    if cursor is None:
        return False
    else:
        return cursor['seed']

def realisedPL(user, assets):
    cursor = contracts.find({'user': user})
    pl = {}
    allready = {}
    for currency in currencys:
        pl[currency] = 0
    for asset in assets:
        allready[asset] = {}
        allready[asset]['quant'] = 0
        allready[asset]['amount'] = 0
        allready[asset]['pl'] = 0
    for doc in cursor:
        quant = doc['quant']
        amount = doc['amount']
        asset = doc['asset']
        ass = splitAsset(asset)
        unit = ass['unit']
        if allready[asset]['quant'] != 0:
            wasPrice = allready[asset]['amount'] / allready[asset]['quant']
            bePrice = amount / quant
            if allready[asset]['quant'] > 0 and allready[asset]['quant'] > -quant and quant < 0:
                pl[unit] += (wasPrice - bePrice) * quant
                allready[asset]['quant'] += quant
                allready[asset]['amount'] = wasPrice * allready[asset]['quant']
            elif allready[asset]['quant'] > 0 and allready[asset]['quant'] < -quant and quant < 0:
                pl[unit] += (wasPrice - bePrice) * allready[asset]['quant']
                allready[asset]['quant'] += quant
                allready[asset]['amount'] = bePrice * allready[asset]['quant']
            elif allready[asset]['quant'] > 0 and allready[asset]['quant'] == -quant and quant < 0:
                pl[unit] += (wasPrice - bePrice) * quant
                allready[asset]['quant'] = 0
                allready[asset]['amount'] = 0
            elif allready[asset]['quant'] < 0 and -allready[asset]['quant'] > quant and quant > 0:
                pl[unit] += (wasPrice - bePrice) * quant
                allready[asset]['quant'] += quant
                allready[asset]['amount'] = wasPrice * allready[asset]['quant']
            elif allready[asset]['quant'] < 0 and -allready[asset]['quant'] < quant and quant > 0:
                pl[unit] += (wasPrice - bePrice) * -allready[asset]['quant']
                allready[asset]['quant'] += quant
                allready[asset]['amount'] = bePrice * allready[asset]['quant']
            elif allready[asset]['quant'] < 0 and -allready[asset]['quant'] == quant and quant > 0:
                pl[unit] += (wasPrice - bePrice) * quant
                allready[asset]['quant'] = 0
                allready[asset]['amount'] = 0
            elif (allready[asset]['quant'] > 0 and quant > 0) or (allready[asset]['quant'] < 0 and quant < 0):
                allready[asset]['quant'] += quant
                allready[asset]['amount'] += amount
        else:
            allready[asset]['quant'] = quant
            allready[asset]['amount'] = amount
    for currency in currencys:
        pl[currency] = int(round(pl[currency]))
    return pl

def clearContracts(user, clearingPrice):
    cursor = getContracts(user)
    pl = {}
    for currency in currencys:
        pl[currency] = 0
    for doc in cursor:
        asset = doc['_id']
        quant = doc['quant']
        amount = doc['amount']
        ass = splitAsset(asset)
        strike = int(ass['strike'])
        dude = ass['dude']
        unit = ass['unit']
        if quant == 0:
            pl[unit] += -amount
        else:
            if quant > 0:
                #price = int(math.floor(amount / quant))
                price = int(round(amount / quant))
                if clearingPrice >= strike:
                    if dude == 'C':
                        clearPrice = clearingPrice - strike - price
                    else:
                        clearPrice = -price
                else:
                    if dude == 'P':
                        clearPrice = strike - clearingPrice - price
                    else:
                        clearPrice = -price
                pl[unit] += clearPrice * quant
            else:
                #price = int(math.ceil(amount / quant))
                price = int(round(amount / quant))
                if clearingPrice >= strike:
                    if dude == 'C':
                        clearPrice = -(clearingPrice - strike) + price
                    else:
                        clearPrice = price
                else:
                    if dude == 'P':
                        clearPrice = -(strike - clearingPrice) + price
                    else:
                        clearPrice = price
                pl[unit] += clearPrice * -quant
    #print(pl)
    return pl

def checkContracts(user, assets):
    sellLock = {}
    buyLock = {}
    prize = {}
    for currency in currencys:
        sellLock[currency] = 0
        buyLock[currency] = 0
        prize[currency] = 0
    cursor = getContracts(user)
    for doc in cursor:
        asset = splitAsset(doc['_id'])
        base = asset['base']
        unit = asset['unit']
        quant = doc['quant']
        amount = doc['amount']
        strike = int(asset['strike'])
        dude = asset['dude']
        if quant < 0 and dude == 'C':
            sellLock[base] += quant
            prize[unit] -= amount
        elif quant > 0 and dude == 'P':
            buyLock[unit] -= amount
            #FULL LOCK
            #buyLock[base] -= quant
        if quant > 0 and dude == 'C':
            buyLock[unit] -= amount
            #FULL LOCK
            #buyLock[unit] -= strike * quant
        elif quant < 0 and dude == 'P':
            sellLock[unit] += strike * quant
            prize[unit] -= amount
    return {'contracts': {'sell': sellLock, 'buy': buyLock}, 'prize': prize, 'realised': realisedPL(user, assets)}

def checkOrders(user):
    sellLock = {}
    buyLock = {}
    for currency in currencys:
        sellLock[currency] = 0
        buyLock[currency] = 0
    cursor = orders.find({
    'user': user
    })
    already = alreadyContracts(user)
    for doc in cursor:
        ticker = doc['ticker'].split('_')
        base = ticker[0]
        unit = ticker[1]
        asset = doc['asset']
        type = doc['type']
        quant = doc['quant']
        price = doc['price']
        amount = quant * price
        strike = int(doc['strike'])
        dude = doc['dude']
        if asset in already and already[asset] > 0 and type == 'sell':
            already[asset] -= quant
            if already[asset] < 0 and dude == 'C':
                sellLock[base] += already[asset]
            elif already[asset] < 0 and dude == 'P':
                sellLock[unit] += strike * already[asset]
        elif asset in already and already[asset] < 0 and type == 'buy':
            already[asset] += quant
            if already[asset] > 0:
                buyLock[unit] -= already[asset] * price
        else:
            if type == 'sell' and dude == 'C':
                sellLock[base] -= quant
            elif type == 'sell' and dude == 'P':
                sellLock[unit] -= strike * quant
            else:
                buyLock[unit] -= amount
    return {'orders': {'sell': sellLock, 'buy': buyLock}}

def userBalances(user, assets):
    cursor = users.find_one({
    'hash': user
    })
    balances = {'own': cursor['balances']}
    lockOrders = checkOrders(user)
    lockContracts = checkContracts(user, assets)
    _available = {}
    for currency in currencys:
        _available[currency] = balances['own'][currency] + lockOrders['orders']['sell'][currency] + lockOrders['orders']['buy'][currency] + lockContracts['contracts']['sell'][currency] + lockContracts['contracts']['buy'][currency] + lockContracts['realised'][currency]
    available = {'available': _available}
    full = {**balances, **lockOrders, **lockContracts, **available}
    #print(user, full)
    if cursor is None:
        return 0
    else:
        return full