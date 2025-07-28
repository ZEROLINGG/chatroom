# app/utils/eec.py
import hashlib
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes


class Eec:
    class Hash:
        @staticmethod
        def sha256(data: str, encoding: str = 'utf-8') -> str:
            try:
                return hashlib.sha256(data.encode(encoding)).hexdigest()
            except Exception:
                return ''

        @staticmethod
        def sha512(data: str, encoding: str = 'utf-8') -> str:
            try:
                return hashlib.sha512(data.encode(encoding)).hexdigest()
            except Exception:
                return ''

    class Bytes:
        @staticmethod
        def stb(data: str, encoding: str = 'utf-8') -> bytes:
            try:
                return data.encode(encoding)
            except Exception:
                return b''

        @staticmethod
        def bts(data: bytes, encoding: str = 'utf-8') -> str:
            try:
                return data.decode(encoding)
            except Exception:
                return ''

    class B64:
        @staticmethod
        def encode_str(data: str, encoding: str = 'utf-8') -> str:
            try:
                byte_data = data.encode(encoding)
                encoded_bytes = base64.b64encode(byte_data)
                return encoded_bytes.decode(encoding)
            except Exception:
                return ''

        @staticmethod
        def decode_str(data: str, encoding: str = 'utf-8') -> str:
            try:
                byte_data = base64.b64decode(data.encode(encoding))
                return byte_data.decode(encoding)
            except Exception:
                return ''

        @staticmethod
        def encode_bytes(data: bytes, encoding: str = 'utf-8') -> str:
            try:
                encoded_bytes = base64.b64encode(data)
                return encoded_bytes.decode(encoding)
            except Exception:
                return ''

        @staticmethod
        def decode_bytes(data: str, encoding: str = 'utf-8') -> bytes:
            try:
                return base64.b64decode(data.encode(encoding))
            except Exception:
                return b''

    class Aes:
        # class Cbc:
        #     @staticmethod
        #     def encrypt_str(data: str, key: str, encoding: str = 'utf-8') -> str:
        #         try:
        #                 # 确保密钥长度为 16, 24 或 32 字节
        #             if len(key.encode(encoding)) not in (16, 24, 32):
        #                 raise ValueError("Invalid AES key length.")
        #             iv = get_random_bytes(16)
        #             cipher = AES.new(key.encode(encoding), AES.MODE_CBC, iv)
        #             padded_data = pad(data.encode(encoding), 16)
        #             encrypted_bytes = cipher.encrypt(padded_data)
        #             # 将 IV + 加密数据一起编码
        #             encrypted_data = base64.b64encode(iv + encrypted_bytes).decode(encoding)
        #             return encrypted_data
        #         except Exception:
        #             return ''
        #     @staticmethod
        #     def decrypt_str(data: str, key: str, encoding: str = 'utf-8') -> str:
        #         try:
        #             # 确保密钥长度为 16, 24 或 32 字节
        #             if len(key.encode(encoding)) not in (16, 24, 32):
        #                 raise ValueError("Invalid AES key length.")
        #             raw_data = base64.b64decode(data.encode(encoding))
        #             iv = raw_data[:16]
        #             encrypted_data = raw_data[16:]
        #             cipher = AES.new(key.encode(encoding), AES.MODE_CBC, iv)
        #             decrypted_bytes = unpad(cipher.decrypt(encrypted_data), 16)
        #             return decrypted_bytes.decode(encoding)
        #         except Exception:
        #              return ''

        class Gcm:
            @staticmethod
            def encrypt_str(data: str, key: str, encoding: str = 'utf-8') -> dict:
                try:
                    cipher = AES.new(key.encode(encoding), AES.MODE_GCM)
                    ciphertext, tag = cipher.encrypt_and_digest(data.encode(encoding))
                    return {
                        "iv": base64.b64encode(cipher.nonce).decode(encoding),
                        "data": base64.b64encode(ciphertext).decode(encoding),
                        "tag": base64.b64encode(tag).decode(encoding)
                    }
                except Exception:
                    return {}
            @staticmethod
            def decrypt_str(data: str, iv: str, tag: str, key: str, encoding: str = 'utf-8') -> str:
                try:
                    if len(key.encode(encoding)) not in (16, 24, 32):
                        raise ValueError("Invalid AES key length.")
                    nonce = base64.b64decode(iv)
                    ciphertext = base64.b64decode(data)
                    tag_bytes = base64.b64decode(tag)
                    cipher = AES.new(key.encode(encoding), AES.MODE_GCM, nonce=nonce)
                    decrypted_bytes = cipher.decrypt_and_verify(ciphertext, tag_bytes)
                    return decrypted_bytes.decode(encoding)
                except Exception:
                    return ''
            @staticmethod
            def encrypt_bytes(data: bytes, key: str, encoding: str = 'utf-8') -> dict:
                try:
                    if len(key.encode(encoding)) not in (16, 24, 32):
                        raise ValueError("Invalid AES key length.")
                    cipher = AES.new(key.encode(encoding), AES.MODE_GCM)
                    ciphertext, tag = cipher.encrypt_and_digest(data)
                    return {
                        "iv": base64.b64encode(cipher.nonce).decode(encoding),
                        "data": base64.b64encode(ciphertext).decode(encoding),
                        "tag": base64.b64encode(tag).decode(encoding)
                    }
                except Exception:
                    return {}
            @staticmethod
            def decrypt_bytes(data: str, iv: str, tag: str, key: str, encoding: str = 'utf-8') -> bytes:
                try:
                    if len(key.encode(encoding)) not in (16, 24, 32):
                        raise ValueError("Invalid AES key length.")
                    nonce = base64.b64decode(iv)
                    ciphertext = base64.b64decode(data)
                    tag_bytes = base64.b64decode(tag)
                    cipher = AES.new(key.encode(encoding), AES.MODE_GCM, nonce=nonce)
                    return cipher.decrypt_and_verify(ciphertext, tag_bytes)
                except Exception:
                    return b''

