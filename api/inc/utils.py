from datetime import datetime as dt
import pandas as pd
from hashlib import blake2b, sha3_512
import os, time, hmac

def pyMode():
    pyMode = os.getenv('PY_MODE')
    return pyMode

def toTS(date):
    ts = int(dt.timestamp(pd.Timestamp(date)))
    return ts

def fromTS(ts):
    date = dt.fromtimestamp(ts)
    return date

def getTime():
    return int(time.time() * 10000000 / 10)

def splitAsset(asset):
    splited = asset.split('_')
    base = splited[0]
    unit = splited[1]
    ticker = splited[0] + '_' + splited[1]
    exp = splited[2]
    strike = splited[3]
    dude = splited[4]
    return {'base':base, 'unit':unit, 'ticker':ticker, 'exp': exp, 'strike': strike, 'dude': dude}

def hashUser(user):
    req = user.encode()
    b2b = blake2b(digest_size=6)
    b2b.update(req)
    userHash = b2b.hexdigest()
    return userHash

def checkHMAC(seed, question, yourHMAC):
    sex = seed.encode()
    req = question.encode()
    myHMAC = hmac.new(sex, req, sha3_512).hexdigest()
    if myHMAC == yourHMAC:
        return True
    else:
        return False