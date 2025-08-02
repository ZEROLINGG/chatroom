# app/utils/response.py
import json
from typing import Any, Dict

from app.utils.eec import Eec


def res(data: Any | None, old_key: str, new_key: str, message: str = "OK", code: int = 0) -> Dict[str, Any]:
    r = {
        'key': new_key,
        'data': data
    }
    return {
        "code": code,
        "message": message,
        "data": Eec.Aes.Gcm.encrypt_str(json.dumps(r), old_key)
    }


def res_no_encrypt(data: Any | None, message: str = "error", code: int = -999) -> Dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "data": data
    }