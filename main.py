from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from typing import List, Dict
import json
import os

PORT = int(os.getenv("PORT", 8000))
# Crear directorios necesarios si no existen
os.makedirs("static", exist_ok=True)
os.makedirs("templates", exist_ok=True)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Manejador de conexiones WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {
            "web": [],
            "esp32": []
        }

    async def connect(self, websocket: WebSocket, client_type: str):
        await websocket.accept()
        if client_type not in self.active_connections:
            self.active_connections[client_type] = []
        self.active_connections[client_type].append(websocket)

    def disconnect(self, websocket: WebSocket, client_type: str):
        self.active_connections[client_type].remove(websocket)

    async def send_to_esp32(self, data: dict):
        for connection in self.active_connections["esp32"]:
            await connection.send_json(data)

    async def send_to_web(self, data: dict):
        for connection in self.active_connections["web"]:
            await connection.send_json(data)

    async def broadcast(self, data: dict):
        # Enviar a todos los clientes (web y ESP32)
        for client_type in self.active_connections:
            for connection in self.active_connections[client_type]:
                await connection.send_json(data)

manager = ConnectionManager()

# Ruta para la página web
@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Endpoint WebSocket para clientes web
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket, "web")
    try:
        while True:
            data = await websocket.receive_json()
            # Reenviar el mensaje a todas las ESP32 conectadas
            await manager.send_to_esp32(data)
            # También enviar de vuelta a los clientes web como confirmación
            await manager.send_to_web({"status": "sent", "data": data})
    except WebSocketDisconnect:
        manager.disconnect(websocket, "web")

# Endpoint WebSocket específico para la ESP32
@app.websocket("/ws/esp32")
async def esp32_endpoint(websocket: WebSocket):
    await manager.connect(websocket, "esp32")
    try:
        while True:
            data = await websocket.receive_json()
            # Enviar datos del ESP32 a todos los clientes web
            await manager.send_to_web(data)
    except WebSocketDisconnect:
        manager.disconnect(websocket, "esp32")