"""app/models/request_models.py"""
from pydantic import BaseModel


class EncryptedContent(BaseModel):
    iv: str
    data: str
    tag: str


class ReqData1(BaseModel):
    message: str
    compression: bool
    algorithm: str
    content: EncryptedContent
