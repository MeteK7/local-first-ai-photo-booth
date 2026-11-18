from hashlib import scrypt, sha256
from hmac import compare_digest
from secrets import token_bytes, token_urlsafe


def issue_token() -> str:
    return token_urlsafe(32)


def token_digest(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def derive(password: str, salt: bytes) -> bytes:
    return scrypt(password.encode(), salt=salt, n=2**16, r=8, p=2, maxmem=96 * 1024**2, dklen=32)


def hash_password(password: str) -> str:
    salt = token_bytes(16)
    return f"scrypt-v1${salt.hex()}${derive(password, salt).hex()}"


def check_password(encoded: str, password: str) -> bool:
    try:
        scheme, salt_hex, key_hex = encoded.split("$")
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(key_hex)
        return (scheme == "scrypt-v1" and len(salt) == 16 and len(expected) == 32
                and compare_digest(derive(password, salt), expected))
    except ValueError:
        return False


DUMMY_HASH = hash_password(token_urlsafe(32))
