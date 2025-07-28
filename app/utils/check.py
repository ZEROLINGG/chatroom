# app/utils/check.py
from typing import Any
from Crypto.PublicKey import RSA


class Check:
    class Rsa:
        @staticmethod
        def key_pub_pem(pubkey_str: Any) -> bool:
            if not isinstance(pubkey_str, str):
                return False
            try:
                RSA.import_key(pubkey_str.encode('utf-8'))  
                return True
            except (ValueError, IndexError):
                return False
