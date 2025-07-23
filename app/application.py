from fastapi import FastAPI

from app.middleware.security_middleware import SecurityMiddleware

app = FastAPI()
app.add_middleware(SecurityMiddleware)