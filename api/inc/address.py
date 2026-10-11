"""Генерация Bitcoin/Ethereum-адресов и ключей.

ВАЖНО: это одноразовая CLI-утилита, а не модуль рантайма. Приложение её НЕ
импортирует (иначе при старте API в лог печатались бы приватные ключи). Запуск:

    python api/inc/address.py

Ранее в файле был зашит приватный ключ `privT` (и печатался при импорте) —
считать его скомпрометированным и никогда не использовать для реальных средств.
"""

import hashlib

from ecdsa import SigningKey, SECP256k1

try:
    import sha3  # keccak для ETH-адресов
except ImportError:  # pragma: no cover - необязательная зависимость
    sha3 = None

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

    # On OpenSSL 3 ripemd160 живёт в legacy-провайдере и может быть недоступен.
    try:
        hasher = hashlib.new('ripemd160')
        hasher.update(r)
        r = hasher.digest()
    except ValueError:
        return None

    return '1' + encode58_check(r, version=0)


def newBitcoinKey():
    priv = SigningKey.generate(curve=SECP256k1)
    pub = b'\x04' + priv.get_verifying_key().to_string()
    return {
        'private': priv.to_string().hex(),
        'private58': encode58_check(priv.to_string(), 128),
        'public': pub.hex(),
        'address': getAddress(pub),
    }


def newEthereumKey():
    if sha3 is None:
        raise RuntimeError('модуль sha3 не установлен — нужен для ETH-адресов')
    priv = SigningKey.generate(curve=SECP256k1)
    pub = priv.get_verifying_key().to_string()
    keccak = sha3.keccak_256()
    keccak.update(pub)
    address = keccak.hexdigest()[24:]
    return {
        'private': priv.to_string().hex(),
        'public': pub.hex(),
        'address': '0x' + address,
    }


def signMessage(privateHex, message):
    """Подписать сообщение приватным ключом (hex). Возвращает (signature, verify)."""
    sk = SigningKey.from_string(bytes.fromhex(privateHex), curve=SECP256k1)
    vk = sk.get_verifying_key()
    signature = sk.sign(message.encode())
    return signature.hex(), vk.verify(signature, message.encode())


def main():
    btc = newBitcoinKey()
    print('Private:', btc['private'])
    print('Private58:', btc['private58'])
    print('Public:', btc['public'])
    print('Address:', btc['address'])
    print('----------------------------------------------')
    eth = newEthereumKey()
    print('Private key:', eth['private'])
    print('Public key: ', eth['public'])
    print('Address:      ', eth['address'])


if __name__ == '__main__':
    main()
