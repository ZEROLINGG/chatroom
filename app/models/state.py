"""app/models/state.py"""
from pathlib import Path
from fastapi.datastructures import State
from app.db.db import AbstractAsyncDB
from app.utils.registration_code import RegKey
from app.utils.rsa import Rsa
from app.kv import Kv


class AppState(State):
    db: AbstractAsyncDB
    rsa: Rsa
    key: str
    kv: Kv
    rk: RegKey
    DIR_base: Path
    DIR_web: Path
