"""app/operate/work.py"""
from typing import Coroutine, Any

from app.models.state import AppState
from app.utils.eec import Eec


class Work:
    super_add_user_flag = True

    @staticmethod
    async def super_add_user(state: AppState, qq_number: int, name: str, avatar_path: str, role: str, password: str, inviter: str="") -> str:

        user_data = {
            'qq_number': qq_number,
            'name': name,
            'avatar_path': avatar_path,
            'role': role,
            'password_hash': Eec.Hash.sha512(password + str(qq_number)),
            'inviter': inviter
        }
        return await state.db.create_user(user_data)    # 如果成功则返回该用户的uuid，否则返回“”
    @staticmethod
    async def super_get_database_info(state: AppState) -> dict:
        return await state.db.get_database_info()
    @staticmethod
    async def super_get_user_by_uuid(state: AppState, user_uuid: str):
        return await state.db.get_user_by_uuid(user_uuid)
        

