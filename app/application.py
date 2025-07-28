# app/application.py
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db.db import DbWork
from app.kv import Kv
from app.models.state import AppState
from app.routes import api
from app.utils.rsa import Rsa



@asynccontextmanager
async def lifespan(app: FastAPI):

    # 初始化数据库接口
    db_work = await DbWork.create_async()
    app.state.db = db_work.get_db()

    # 初始化服务器公私钥
    _rsa = Rsa()
    _rsa.init()
    app.state.rsa = _rsa

    # 初始化异步键值对管理器
    app.state.kv = Kv()

    # 获取目录信息
    app.state.DIR_base = Path(__file__).resolve().parent.parent  # 指向项目根目录
    app.state.DIR_web = app.state.DIR_base / 'web'

    yield  # 应用开始接收请求



def create_app() -> FastAPI:
    _app = FastAPI(lifespan=lifespan)
    # 添加中间件
    # _app.add_middleware(SecurityMiddleware)  # type: ignore
    return _app


app = create_app()
# 挂载静态资源目录
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# 设置模板路径
templates = Jinja2Templates(directory="web/template")
app.include_router(api.router)
