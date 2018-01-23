import hashlib
from ecdsa import SigningKey, SECP256k1, VerifyingKey
import sha3
#from sha3 import keccak_256 as keccak

alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
base_count = len(alphabet)
       
def encode58(num):
    encode = ''
   
    if (num < 0):
        return ''
   
    while (num >= base_count):    
        mod = num % base_count
        encode = alphabet[mod] + encode
        num = num // base_count
 
    if (num):
        encode = alphabet[num] + encode
 
    return encode

def encode58_check(src, version):

    src = bytes([version]) + src
    hasher = hashlib.sha256()
    hasher.update(src)
    r = hasher.digest()
 
    hasher = hashlib.sha256()
    hasher.update(r)
    r = hasher.digest()
 
    checksum = r[:4]
    s = src + checksum
 
    return encode58(int.from_bytes(s, 'big'))

def getAddress(public_key):
    hasher = hashlib.sha256()
    hasher.update(public_key)
    r = hasher.digest()
 
    hasher = hashlib.new('ripemd160')
    hasher.update(r)
    r = hasher.digest()

    return '1' + encode58_check(r, version=0)

priv = SigningKey.generate(curve=SECP256k1)
pub = b'\x04' + priv.get_verifying_key().to_string()

print('Private:', priv.to_string().hex())
print('Private58:', encode58_check(priv.to_string(), 128))
print('Public:', pub.hex())
print('Address:', getAddress(pub))

print('----------------------------------------------')
keccak = sha3.keccak_256()

priv = SigningKey.generate(curve=SECP256k1)
pub = priv.get_verifying_key().to_string()

keccak.update(pub)
address = keccak.hexdigest()[24:]

print("Private key:", priv.to_string().hex())
print("Public key: ", pub.hex())
print("Address:     0x" + address)

#priv = SigningKey.generate(curve=SECP256k1)
#pub = priv.get_verifying_key()
#print(priv.to_string())
#print(pub.to_string())
#print(priv.to_string().hex())
#print(pub.to_string().hex())

#privB: b"@\xb7:\x08\x86\x16\xde\x8a.sY\x1c\xd3\x1be'\xe8\xa0\x87h\x8b\xae\xd9\x16y\x87\x8cphq*\x13"
#pubB = b'\xa1\xfdo\xdc\x9b\xd0s\xad1:\x93\xb2\xe5\x92\xac\x993\xd5\xae\x17\x83\xb7Z\x007to\x9c\xc7G\xbc\x88DE\xf0\x94$OZK\x1e{\x80\xd4\xb0\xedp\x17Kv\xae\x17\xe9\xec\x9a\xaa\xa9qP\xe7\x11\xae\\?'

privT = '40b73a088616de8a2e73591cd31b6527e8a087688baed91679878c7068712a13'
pubT = 'a1fd6fdc9bd073ad313a93b2e592ac9933d5ae1783b75a0037746f9cc747bc884445f094244f5a4b1e7b80d4b0ed70174b76ae17e9ec9aaaa97150e711ae5c3f'
privB = bytes.fromhex(privT)
pubB = bytes.fromhex(pubT)
print(privB)
print(pubB)

sk = SigningKey.from_string(privB, curve=SECP256k1)
vk = VerifyingKey.from_string(pubB, curve=SECP256k1)

print(sk.to_string().hex())
print(vk.to_string().hex())
print ('------------------------------')
mes = 'i love sex'.encode()
sign = sk.sign(mes)
print(sign.hex())
print(vk.verify(sign, mes))
assert vk.verify(sign, mes)