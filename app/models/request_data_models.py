"""app/models/request_data_models.py"""
from typing import Any

from pydantic import BaseModel


class WorkData:
    class BaseData(BaseModel):
        operate: str
        args: Any

    class super_add_user(BaseModel):
        qq_number: int
        name: str
        avatar_path: str
        role: str
        password: str
    class super_get_user_by_uuid(BaseModel):
        user_uuid: str
        