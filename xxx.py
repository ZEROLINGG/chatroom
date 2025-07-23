from typing import List

import uvicorn
from fastapi import WebSocket, FastAPI
from starlette.websockets import WebSocketDisconnect

app = FastAPI()
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/chat")
async def chat_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await manager.broadcast(f"用户说: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)



uvicorn.run(app, host="0.0.0.0", port=8000)
