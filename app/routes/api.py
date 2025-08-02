"""app/routes/api.py"""
import uuid
import aiofiles

import gzip
import zlib
import lzma
import zstandard as zstd

from pydantic import ValidationError
import orjson
from fastapi import Request, Form, Response, Cookie, APIRouter
from fastapi.responses import HTMLResponse
from starlette.datastructures import Headers

from app.models.request_data_models import WorkData
from app.models.state import AppState
from app.operate.work import Work
from app.state import get_state
from app.utils.check import Check
from app.utils.eec import Eec
from app.utils.response import res, res_no_encrypt
from app.models.request_models import ReqData1

router = APIRouter()


@router.api_route('/rs', methods=["GET", "PUT", "DELETE"])
@router.api_route('/api', methods=["GET", "PUT", "DELETE"])
async def method_not_allowed():
    return res_no_encrypt('不允许的方式', code=100405)


@router.post('/rs')
async def rs(response: Response, request: Request, user_key_pub_pem: str = Form(...)):
    if not Check.Rsa.key_pub_pem(user_key_pub_pem):
        return res_no_encrypt("无效的 RSA 公钥")
    state = get_state(request.app)

    sha256 = Eec.Hash.sha256(user_key_pub_pem + uuid.uuid4().hex)
    aes_key = sha256[:16]
    session = sha256[16:]
    encrypted_key = state.rsa.encrypt(aes_key, user_key_pub_pem, output='hex')  # hex字符串

    # 设置 Cookie
    response.set_cookie(
        key="session_id",
        value=session,
        httponly=True,
        max_age=120,
        samesite="strict",
        # secure=True
    )

    await state.kv.add(session, aes_key, ttl=120)

    return res_no_encrypt(encrypted_key, "ok", 0)


@router.post('/api')
async def api_post(request: Request, response: Response):
    if not request.headers.get("Content-Type", "").startswith("application/json"):
        return res_no_encrypt("Content-Type 不正确")
    state = get_state(request.app)
    session_id = request.cookies.get("session_id")
    if not session_id:
        return res_no_encrypt('无有效的加密通道')
    aes_key = await state.kv.get(session_id, None)  # 示例结果： "0e9eee0055c319f2"
    if not aes_key:
        return res_no_encrypt('无有效的加密通道')
    session_user = request.headers.get("session_user")
    if not session_user:
        return res_no_encrypt("无有效的加密通道")
    if Eec.Hash.sha256(aes_key) != session_user:  # 用于防止csrf
        return res_no_encrypt("头部加密错误")
    try:
        raw_body = await request.body()
        if len(raw_body) > 3 * 1024 * 1024:  # 3 MiB 上限
            return res_no_encrypt("请求体过大")

        json_data_ = orjson.loads(raw_body)
        payload = ReqData1(**json_data_)

    except orjson.JSONDecodeError:
        return res_no_encrypt("第一层json错误")
    except ValidationError as ve:
        return res_no_encrypt(f"第一层json结构校验失败: {ve.errors()}")
    except Exception:
        return res_no_encrypt("未知错误: Exception")

    sha256 = Eec.Hash.sha256(aes_key + uuid.uuid4().hex)
    new_aes_key = sha256[:16]
    new_session = sha256[16:]
    # 修改 Cookie
    response.set_cookie(
        key="session_id",
        value=new_session,
        httponly=True,
        max_age=120,
        samesite="strict",
        # secure=True

    )
    await state.kv.delete(session_id)
    await state.kv.add(new_session, new_aes_key, ttl=120)  # 更新cookie和对称密钥

    if not payload.compression:
        json_data = Eec.Aes.Gcm.decrypt_str(**payload.content.model_dump(), key=aes_key)
        if not json_data:
            return res_no_encrypt("无法解密的数据")
    else:
        _data_bytes = Eec.Aes.Gcm.decrypt_bytes(**payload.content.model_dump(), key=aes_key)
        if not _data_bytes:
            return res_no_encrypt("无法解密的数据")
        if payload.algorithm == "gzip":
            try:
                json_data = gzip.decompress(_data_bytes).decode('utf-8')
            except Exception:
                return res(f"gzip 解压失败: {payload.algorithm}", aes_key, new_aes_key, "error", -201)
        elif payload.algorithm == "zlib":
            try:
                json_data = zlib.decompress(_data_bytes).decode('utf-8')
            except Exception:
                return res(f"zlib 解压失败: {payload.algorithm}", aes_key, new_aes_key, "error", -201)
        elif payload.algorithm == "zstd":
            try:
                dctx = zstd.ZstdDecompressor()
                json_data = dctx.decompress(_data_bytes).decode('utf-8')
            except Exception:
                return res(f"zstd 解压失败: {payload.algorithm}", aes_key, new_aes_key, "error", -201)
        elif payload.algorithm == "lzma":
            try:
                json_data = lzma.decompress(_data_bytes).decode('utf-8')
            except Exception:
                return res(f"lzma 解压失败: {payload.algorithm}", aes_key, new_aes_key, "error", -201)
        else:
            return res(f"不支持的压缩算法: {payload.algorithm}", aes_key, new_aes_key, "error", -201)

    r, msg, code = await api_work(json_data, state, request.cookies, request.headers)
    return res(r, aes_key, new_aes_key, msg, code)


@router.get('/test')
async def test(request: Request):
    async with aiofiles.open(get_state(request.app).DIR_web / "template" / "hello.html", mode="r", encoding="utf-8") as f:
        content = await f.read()
    return HTMLResponse(content=content, status_code=200)


async def api_work(json_data: str, state: AppState, cookie: dict[str, str], head: Headers):
    try:
        json_data_ = orjson.loads(json_data)
        payload = WorkData.BaseData(**json_data_)
    except orjson.JSONDecodeError:
        return "第二层json错误", "error", -101
    except ValidationError as ve:
        return f"第二层json结构校验错误 {ve.errors()}", "error", -102
    except Exception:
        return f"未知错误: 未知服务器内部错误", "error", -103
    if not hasattr(Work, payload.operate):
        return f"不合法的操作 {payload.operate}", "error", -104
    """根据cookie确认用户，并验证是否有权限操作"""
    if not hasattr(Work, f"{payload.operate}_flag"):
        # 验证用户
        pass
    if hasattr(WorkData, payload.operate):
        # 验证数据结构
        model_class = getattr(WorkData, payload.operate)
        try:
            validated_args = model_class(**payload.args)
            payload.args = validated_args.model_dump()  # 用于后续实际操作方法调用
        except ValidationError as ve:
            return f"{payload.operate} 参数结构校验失败: {ve.errors()}", "error", -105
    

    # 获取待执行的方法
    method = getattr(Work, payload.operate)
    # 调用方法并返回结果
    try:
        result = await method(state, **payload.args)
        return result, "ok", 0
    except Exception as e:
        return f"方法执行异常：{payload.operate}: {e}", "error", -106
