from __future__ import annotations

import base64
import hashlib
import hmac
import secrets


def _derive_master_key(secret_key: str) -> bytes:
    seed = str(secret_key or "").strip().encode("utf-8")
    return hashlib.sha256(seed + b"|bim_revit.v1").digest()


def generate_plugin_secret(length: int = 48) -> str:
    safe_len = int(length) if int(length or 0) > 16 else 48
    # token_urlsafe may exceed requested length; truncate for stable UX.
    return secrets.token_urlsafe(safe_len)[:safe_len]


def encrypt_plugin_secret(plain_text: str, *, secret_key: str) -> str:
    value = str(plain_text or "")
    if not value:
        return ""

    plain = value.encode("utf-8")
    master = _derive_master_key(secret_key)
    nonce = secrets.token_bytes(16)
    keystream = hashlib.pbkdf2_hmac("sha256", master, nonce, 120_000, dklen=len(plain))
    cipher = bytes([a ^ b for a, b in zip(plain, keystream)])
    mac = hmac.new(master, nonce + cipher, hashlib.sha256).digest()
    payload = nonce + mac + cipher
    return base64.urlsafe_b64encode(payload).decode("ascii")


def decrypt_plugin_secret(cipher_text: str, *, secret_key: str) -> str:
    raw = str(cipher_text or "").strip()
    if not raw:
        return ""

    try:
        payload = base64.urlsafe_b64decode(raw.encode("ascii"))
    except Exception as exc:
        raise ValueError("Invalid encrypted plugin secret format.") from exc

    if len(payload) < 48:
        raise ValueError("Invalid encrypted plugin secret payload.")

    nonce = payload[:16]
    mac = payload[16:48]
    cipher = payload[48:]
    master = _derive_master_key(secret_key)
    expected_mac = hmac.new(master, nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise ValueError("Plugin secret integrity check failed.")

    keystream = hashlib.pbkdf2_hmac("sha256", master, nonce, 120_000, dklen=len(cipher))
    plain = bytes([a ^ b for a, b in zip(cipher, keystream)])
    return plain.decode("utf-8")


def compute_body_sha256(body: bytes | bytearray | None) -> str:
    if body is None:
        return hashlib.sha256(b"").hexdigest()
    return hashlib.sha256(bytes(body)).hexdigest()


def build_signature_canonical(
    *,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body_sha256: str,
) -> str:
    return "\n".join(
        [
            str(method or "").upper(),
            str(path or ""),
            str(timestamp or ""),
            str(nonce or ""),
            str(body_sha256 or ""),
        ]
    )


def compute_plugin_signature(*, secret: str, canonical: str) -> str:
    return hmac.new(
        str(secret or "").encode("utf-8"),
        str(canonical or "").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

