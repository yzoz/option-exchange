from datetime import datetime as dt
import pandas as pd
from hashlib import blake2b, sha3_512, pbkdf2_hmac
import os
import time
import hmac

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

# Пароль пользователя: PBKDF2-HMAC-SHA512, случайная соль.
# В БД лежит только производное значение — plaintext-секрета нет.
PBKDF2_ITERATIONS = 200000
PBKDF2_DKLEN = 32

def hashPassword(password):
    salt = os.urandom(16).hex()
    digest = pbkdf2_hmac('sha512', password.encode(), bytes.fromhex(salt),
                         PBKDF2_ITERATIONS, dklen=PBKDF2_DKLEN)
    return digest.hex(), salt

def verifyPassword(password, passwordHash, salt):
    if not passwordHash or not salt:
        return False
    digest = pbkdf2_hmac('sha512', password.encode(), bytes.fromhex(salt),
                         PBKDF2_ITERATIONS, dklen=PBKDF2_DKLEN)
    return hmac.compare_digest(digest.hex(), passwordHash)

def checkHMAC(seed, question, yourHMAC):
    sex = seed.encode()
    req = question.encode()
    myHMAC = hmac.new(sex, req, sha3_512).hexdigest()
    if myHMAC == yourHMAC:
        return True
    else:
        return False


# --- Простой per-IP rate-limit (in-memory) -----------------------------------
# Защищает публичные входы (/signup, /order, /user) от перебора/флуда.
# Ограничение локальное для процесса — как и блокировка матчинга (см. DONE.md):
# при нескольких воркерах нужен внешний счётчик (Redis/Memcached). Опционально
# отключается RATE_LIMIT=0.
import threading

RATE_LIMIT = os.getenv('RATE_LIMIT', '1') != '0'
RATE_WINDOW = float(os.getenv('RATE_WINDOW', '60'))
RATE_MAX = int(os.getenv('RATE_MAX', '120'))

_rateHits = {}
_rateGuard = threading.Lock()


def rateAllow(client, weight=1):
    """True, если запрос от client разрешён. Скользящее окно RATE_WINDOW сек."""
    if not RATE_LIMIT:
        return True
    now = time.time()
    with _rateGuard:
        hits = [t for t in _rateHits.get(client, []) if now - t < RATE_WINDOW]
        if len(hits) + weight > RATE_MAX:
            _rateHits[client] = hits
            return False
        hits.append(now)
        _rateHits[client] = hits
    return True
