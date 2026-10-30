import base64
import hashlib
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DEFAULT_SECRET = os.getenv("ENCRYPTION_KEY", "growcord_super_secret_aes_key_2026")


def derive_key(secret: str = DEFAULT_SECRET) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def decrypt_token(encrypted_str: str, secret: str = DEFAULT_SECRET) -> str:
    """
    Mendekripsi token berformat 'aes:<base64(12_bytes_iv + ciphertext + 16_bytes_tag)>'
    yang kompatibel dengan Node.js crypto AES-256-GCM.
    Jika token tidak diawali 'aes:', diasumsikan token plaintext.
    """
    if not encrypted_str:
        return ""
    if not encrypted_str.startswith("aes:"):
        return encrypted_str

    try:
        raw = base64.b64decode(encrypted_str[4:])
        nonce = raw[:12]
        ciphertext_and_tag = raw[12:]
        key = derive_key(secret)
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(nonce, ciphertext_and_tag, None)
        return decrypted.decode("utf-8")
    except Exception as exc:
        raise ValueError(f"Gagal mendekripsi token: {exc}")


def encrypt_token(plain_token: str, secret: str = DEFAULT_SECRET) -> str:
    if not plain_token:
        return ""
    key = derive_key(secret)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plain_token.encode("utf-8"), None)
    combined = nonce + ciphertext
    return "aes:" + base64.b64encode(combined).decode("utf-8")


if __name__ == "__main__":
    test_token = "MTAyNDk2OTAzNzg0.DummyToken.Test12345"
    enc = encrypt_token(test_token)
    dec = decrypt_token(enc)
    assert dec == test_token
    print(f"Test AES-256-GCM OK!\nEncrypted: {enc[:30]}...\nDecrypted: {dec}")
