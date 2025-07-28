# app/utils/response.py
import json
from typing import Any, Optional, Dict

from app.utils.eec import Eec


def success(data: Any | None, old_key: str, new_key: str, message: str = "成功", code: int = 0) -> Dict[str, Any]:
    r = {
        'key': new_key,
        'data': data
    }
    return {
        "code": code,
        "message": message,
        "data": Eec.Aes.Gcm.encrypt_str(json.dumps(r), old_key)
    }


def error(message: str, data: Any | None = None, old_key: str = None, new_key: str = None, code: int = 1) -> Dict[str, Any]:
    r = {
        'key': new_key,
        'data': data
    }
    enc_r = r
    if code < 1 and old_key and new_key:
        enc_r = Eec.Aes.Gcm.encrypt_str(json.dumps(r), old_key)
    return {
        "code": code,
        "message": message,
        "data": enc_r
    }
