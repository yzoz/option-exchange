from influxdb import InfluxDBClient
from pymongo import MongoClient
from memcache import Client as MemClient

inUser = 'ad'
inPwd = 'pass'
InHost = 'localhost'
inPort = 8086

def indb(inDB):
    db = InfluxDBClient(InHost, inPort, inUser, inPwd, inDB)
    return db
    
moUser = 'ad'
moPwd = 'pass'
moHost = 'localhost'
moPort = '27017'

def modb():
    cli = MongoClient(moHost + ':' + moPort)
    cli.admin.authenticate(moUser, moPwd)
    db = cli.exchange
    return db
    
def memdb():
    servers = ["127.0.0.1:11211"]
    db = MemClient(servers, debug=1)
    return db
