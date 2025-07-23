import uvicorn
from fastapi import FastAPI
from app.application import app


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


uvicorn.run(app, host="0.0.0.0", port=8000)