"""app/models/state.py"""
from pathlib import Path
from fastapi.datastructures import State
from app.db.db import AbstractAsyncDB  # 假设你实际使用的是 AsyncSession 类型
from app.utils.rsa import Rsa
from app.kv import Kv


class AppState(State):
    db: AbstractAsyncDB
    rsa: Rsa
    kv: Kv
    DIR_base: Path
    DIR_web: Path
