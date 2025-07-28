from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256
from base64 import b64encode, b64decode
import binascii


class Rsa:
    def __init__(self, name="RSA-OAEP", hash_algo="SHA-256"):
        self.name = name
        self.hash_algo = hash_algo
        self.key_pair = None

    def init(self):
        try:
            self.key_pair = RSA.generate(2048)
        except Exception as e:
            raise RuntimeError(f"密钥生成失败: {e}")

    def get_public_key_pem(self) -> str:
        if not self.key_pair:
            raise ValueError("密钥尚未初始化")
        try:
            public_key = self.key_pair.publickey()
            pem = public_key.export_key().decode()
            return pem
        except Exception as e:
            raise RuntimeError(f"导出公钥失败: {e}")

    def encrypt(self, plain_text: str, PublicKey_pem=None, use_myPublicKey=False, output='base64') -> str:
        try:
            public_key = self._resolve_public_key(PublicKey_pem, use_myPublicKey)
            cipher = PKCS1_OAEP.new(public_key, hashAlgo=SHA256)
            encrypted = cipher.encrypt(plain_text.encode())

            if output == 'hex':
                return binascii.hexlify(encrypted).decode()
            else:
                return b64encode(encrypted).decode()
        except Exception as e:
            raise RuntimeError(f"加密失败: {e}")

    def decrypt(self, cipher_text: str, *, input='base64') -> str:
        if not self.key_pair:
            raise ValueError("私钥未初始化")
        try:
            if input == 'hex':
                encrypted = binascii.unhexlify(cipher_text)
            else:
                encrypted = b64decode(cipher_text)

            cipher = PKCS1_OAEP.new(self.key_pair, hashAlgo=SHA256)
            decrypted = cipher.decrypt(encrypted)
            return decrypted.decode()
        except Exception as e:
            raise RuntimeError(f"解密失败: {e}")

    # ======================
    # 私有方法
    # ======================

    def _resolve_public_key(self, pem: str, use_myKey: bool):
        if use_myKey:
            if not self.key_pair:
                raise ValueError("公钥未初始化")
            return self.key_pair.publickey()
        if not pem:
            raise ValueError("必须提供 PEM 格式公钥或启用 use_myPublicKey")

        try:
            public_key = RSA.import_key(pem)
            return public_key
        except Exception as e:
            raise ValueError(f"无效的 PEM 公钥格式: {e}")


if __name__ == '__main__':
    rsa = Rsa()
    rsa.init()
    pub_key = rsa.get_public_key_pem()
    msg = "测试消息"
    encrypted = rsa.encrypt(msg, PublicKey_pem=pub_key)
    decrypted = rsa.decrypt(encrypted)
    print(f"原文: {msg}\n加密: {encrypted}\n解密: {decrypted}")