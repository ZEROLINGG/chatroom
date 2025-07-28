import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from app.application import app, templates


@app.get("/")
async def root():
    a = await app.state.db.get_database_info()

    return {"message": f"Hello World{a}"}


@app.get("/hello/{name}", response_class=HTMLResponse)
async def say_hello(request: Request, name: str):
    return templates.TemplateResponse("hello.html", {"request": request, "name": name})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
