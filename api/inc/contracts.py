from .settings import modb, memdb
from .influx import inTrade
from .mc import setState, upLast
from .utils import getTime
mc = memdb()
contracts = modb().contracts

def makeDeal(ticker, exp, strike, dude, user, oppUser, type, quant, asset, price):
    times = getTime()
    if type == 'buy':
        inQuant = quant
        inAmount = quant * price
        oppQuant = -quant
        oppAmount = -quant * price
    else:
        inQuant = -quant
        inAmount = -quant * price
        oppQuant = quant
        oppAmount = quant * price
    cursor = contracts.insert_many([
      {
        'user': user,
        'quant': inQuant,
        'asset': asset,
        'amount': inAmount,
        'time': times,
        'ticker': ticker,
        'exp': exp,
        'strike': strike,
        'dude': dude
       },
      {
        'user': oppUser,
        'quant': oppQuant,
        'asset': asset,
        'amount': oppAmount,
        'time': times,
        'ticker': ticker,
        'exp': exp,
        'strike': strike,
        'dude': dude
       }
    ]).inserted_ids
    if (cursor):
        inTrade(ticker, exp, strike, dude, user, oppUser, type, quant, price)
        upLast(asset, price)
        setState(ticker, exp, 'TRADE', getTime())
        return 'Deal: ' + str(times) + ' | ' + str(user) + ' User ' + type + ' from ' + str(oppUser) + ' User ' + str(quant) + ' of ' + asset + ' for ' + str(price) + '\n'
    else:
        return 'Failed to make Deal\n'

#Get SUM of contracts of user
def getContracts(user):
    cursor = contracts.aggregate([
    {'$match': {'user': user}},
    {'$group': {'_id': '$asset',
                'amount': {'$sum': '$amount'},
                'quant': {'$sum': '$quant'}
                }
    },
    {'$sort': {'_id': -1}}
    ])
    return cursor

#Get SUM contracts of User with Asset
def userContracts(user):
    cursor = getContracts(user)
    res = []
    for doc in cursor:
        asset = doc['_id']
        quant = doc['quant']
        if quant == 0:
            amount = 0
            price = 0
            pl = -doc['amount']
        else:
            amount = doc['amount']
            price = int(round(amount / quant))
            last = mc.get('LAST_' + asset)
            if amount < 0:
                pl = -amount - last * -quant
            else:
                pl = last * quant - amount
        res.append({'asset': asset, 'quant': quant, 'amount': amount, 'price': price, 'pl': pl})
    return res

#Get All TRADES of User
def userTrades(user):
    cursor = contracts.find({
    'user': user
    }, sort=[('time', -1)])
    res = []
    for doc in cursor:
        amount = doc['amount']
        quant = doc['quant']
        price = int(round(doc['amount'] / quant))
        res.append({'asset': doc['asset'], 'quant': quant, 'amount': amount, 'price': price, 'time': doc['time']})
    return res

#Get Array of Assets with contracts
def alreadyContracts(user):
    cursor = getContracts(user)
    already = {}
    for doc in cursor:
        if doc['quant']:
            already[doc['_id']] = doc['quant']
    return already