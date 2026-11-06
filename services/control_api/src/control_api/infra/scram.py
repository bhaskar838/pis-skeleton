"""Client-side SCRAM-SHA-256 verifiers (RFC 5802 / RFC 7677) in Postgres' stored format.

Sending ``PASSWORD 'SCRAM-SHA-256$...'`` means the plaintext password never appears in a SQL statement, so it
cannot leak through ``log_statement`` or ``pg_stat_statements``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

ITERATIONS = 4096


def scram_sha256_verifier(password: str, *, salt: bytes | None = None, iterations: int = ITERATIONS) -> str:
    salt = salt or os.urandom(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()

    def b64(b: bytes) -> str:
        return base64.b64encode(b).decode()

    return f"SCRAM-SHA-256${iterations}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}"
