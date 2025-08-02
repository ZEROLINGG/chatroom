from typing import Any
from Crypto.PublicKey import RSA


class Check:
    class Rsa:
        @staticmethod
        def key_pub_pem(pubkey_str: Any) -> bool:
            if not isinstance(pubkey_str, str):
                return False
            if len(pubkey_str) > 4096:  # 4KB长度限制，可根据需求调整
                return False
            try:
                key = RSA.import_key(pubkey_str.encode('utf-8'))
            except (ValueError, IndexError, TypeError):
                return False
            if key.has_private():
                return False
            if key.size_in_bits() < 2048:
                return False
            return True
