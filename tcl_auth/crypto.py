from __future__ import annotations

import base64
import hashlib
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def encrypt_by_section(data: str, public_key_b64: str) -> str:
    key = load_der_public_key(base64.b64decode(public_key_b64))
    raw = data.encode("utf-8")
    chunks: list[bytes] = []
    for offset in range(0, len(raw), 117):
        chunks.append(key.encrypt(raw[offset : offset + 117], padding.PKCS1v15()))
    return base64.b64encode(b"".join(chunks)).decode("ascii")
