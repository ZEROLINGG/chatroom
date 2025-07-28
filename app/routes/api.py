"""app/routes/api.py"""
import uuid
import aiofiles

from pydantic import ValidationError
import orjson
from fastapi import Request, Form, Response, Cookie, APIRouter
from fastapi.responses import HTMLResponse

from app.state import get_state
from app.utils.check import Check
from app.utils.eec import Eec
from app.utils.response import success, error
from app.models.request_models import ReqData1

router = APIRouter()


@router.api_route('/rs', methods=["GET", "PUT", "DELETE"])
@router.api_route('/api', methods=["GET", "PUT", "DELETE"])
async def method_not_allowed():
    return error('不允许的方式', code=100405)


@router.post('/rs')
async def rs(response: Response, request: Request, user_key_pub_pem: str = Form(...)):
    if not Check.Rsa.key_pub_pem(user_key_pub_pem):
        return error("无效的 RSA 公钥")
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
        samesite="strict"
    )

    await state.kv.add(session, aes_key, ttl=120)

    return {"key": encrypted_key, "code": 0}  # 该部分通过rsa确保安全，不采用success()


@router.post('/api')
async def api_post(request: Request, response: Response, session_id: str = Cookie(None)):
    if not request.headers.get("Content-Type", "").startswith("application/json"):
        return error("Content-Type 不正确")
    state = get_state(request.app)
    aes_key = await state.kv.get(session_id, None)  # 示例结果： "0e9eee0055c319f2"
    if not aes_key:
        return error('无有效的加密通道')
    try:
        raw_body = await request.body()
        if len(raw_body) > 3 * 1024 * 1024:  # 3 MiB 上限
            return error("请求体过大")

        json_data_ = orjson.loads(raw_body)
        payload = ReqData1(**json_data_)

    except orjson.JSONDecodeError:
        return error("JSON 格式解析失败")
    except ValidationError as ve:
        return error(f"数据结构校验失败: {ve.errors()}")
    except Exception as e:
        return error(f"未知错误: {str(e)}")

    sha256 = Eec.Hash.sha256(aes_key + uuid.uuid4().hex)
    new_aes_key = sha256[:16]
    new_session = sha256[16:]
    # 修改 Cookie
    response.set_cookie(
        key="session_id",
        value=new_session,
        httponly=True,
        max_age=120,
        samesite="strict"
    )
    await state.kv.delete(session_id)
    await state.kv.add(new_session, new_aes_key, ttl=120)  # 更新cookie和对称密钥

    json_data = ""
    if not payload.compression:
        json_data = Eec.Aes.Gcm.decrypt_str(**payload.content.model_dump(), key=aes_key)
    else:
        if payload.algorithm == "gzip":
            pass
        elif payload.algorithm == "zlib":
            pass
        elif payload.algorithm == "zstd":
            pass
        elif payload.algorithm == "lzma":
            pass
        pass
    data = orjson.loads(json_data)

    """其他业务操作"""
    # 目前先验证逻辑

    r = success({'operate': data.get('operate')}, old_key=aes_key, new_key=new_aes_key)
    print("!!! 返回内容  ！！！")
    print(r)
    print("!!! 返回内容  ！！！")
    return r


@router.get('/test')
async def test(request: Request):
    async with aiofiles.open(get_state(request.app).DIR_web / "template" / "xxx.html", mode="r", encoding="utf-8") as f:
        content = await f.read()
    return HTMLResponse(content=content, status_code=200)
