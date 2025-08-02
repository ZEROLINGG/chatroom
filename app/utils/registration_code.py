"""app/utils/registration_code.py"""

import json
import uuid
from typing import Optional
from starlette.datastructures import State

from app.utils.eec import Eec


class RegKey:
    @staticmethod
    async def create(
            state: State,
            ttl: int = 3600 * 12,
            key_type: str = "all",
            qq_number: int = 0
    ) -> str:
        if key_type not in ("all", "qq"):
            return ""
        uuid_str = str(uuid.uuid4())
        k = {
            "uuid": uuid_str,
            "key_type": key_type,
            "qq_number": qq_number,
            "ttl": ttl
        }
        json_k = json.dumps(k)
        data = Eec.Aes.Cbc.encrypt_str(json_k, state.key)

        if key_type == "all":
            await state.kv.add(f"RK:all:{uuid_str}", data, ttl=ttl)
        elif key_type == "qq":
            await state.kv.add(f"RK:qq:{uuid_str}", data, ttl=ttl)
        else:
            return ""

        return data

    @staticmethod
    async def use(state: State, reg_key: str, qq_number: int = 0) -> bool:
        if len(reg_key) not in (152, 172, 192):
            return False

        try:
            json_k = Eec.Aes.Cbc.decrypt_str(reg_key, state.key)
            k = json.loads(json_k)

            uuid_str = k.get("uuid")
            key_type = k.get("key_type")
            stored_key: Optional[str] = None

            if key_type == "all":
                key_name = f"RK:all:{uuid_str}"
                stored_key = await state.kv.get(key_name)
                if stored_key != reg_key:
                    return False
                await state.kv.delete(key_name)
                return True

            elif key_type == "qq":
                key_name = f"RK:qq:{uuid_str}"
                stored_key = await state.kv.get(key_name)
                if stored_key != reg_key:
                    return False
                if k.get("qq_number") != qq_number:
                    return False
                await state.kv.delete(key_name)
                return True

            else:
                return False

        except Exception:
            return False
