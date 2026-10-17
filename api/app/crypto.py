import base64
import hashlib
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .config import settings


def cipher() -> AESGCM:
    try:
        key = base64.urlsafe_b64decode(settings().tinyfish_encryption_key)
        if len(key) != 32:
            raise ValueError()
        return AESGCM(key)
    except Exception as exc:
        raise RuntimeError("TINYFISH_ENCRYPTION_KEY must encode 32 bytes") from exc


def encrypt(value: str) -> str:
    nonce = os.urandom(12)
    payload = nonce + cipher().encrypt(nonce, value.encode(), None)
    return base64.urlsafe_b64encode(payload).decode()


def decrypt(value: str) -> str:
    payload = base64.urlsafe_b64decode(value)
    return cipher().decrypt(payload[:12], payload[12:], None).decode()


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]
