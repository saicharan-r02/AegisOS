import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from fastapi import FastAPI,HTTPException,WebSocket,WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from aegis_os.kernel.checkpoint import CheckpointStore
from aegis_os.kernel.events import EventBus,KernelEvent
from aegis_os.api_models import MissionListResponse,MissionResponse,MissionStepsResponse

class _SuppressShutdownErrors(logging.Filter):
    _PATTERNS=("CancelledError","lifespan","Traceback")
    def filter(self,record: logging.LogRecord)->bool:
        msg=record.getMessage()
        return not any(p in msg for p in self._PATTERNS)

logging.getLogger("uvicorn.error").addFilter(_SuppressShutdownErrors())
global_store: CheckpointStore = None
global_bus: EventBus = None
_ws_clients: set = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    if global_store:
        global_store.close()

app=FastAPI(title="AegisOS Mission Control API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

def init_app(db_path: Path) -> None:
    global global_store,global_bus
    global_store=CheckpointStore(db_path)
    global_bus=EventBus()

@app.get("/api/missions", response_model=MissionListResponse)
def get_missions():
    if not global_store:
        raise HTTPException(status_code=500, detail="Store not initialized")
    missions=global_store.list_missions()
    response=[]
    for m in missions:
        m_data={
            "session_id":str(m.get("session_id")),
            "goal":m.get("goal")or "Unknown Goal",
            "status":m.get("status"),
            "current_step_index":int(m.get("current_step_index",0)),
            "updated_at":str(m.get("updated_at",""))
        }
        response.append(MissionResponse(**m_data))
    return MissionListResponse(missions=response)

@app.get("/api/missions/{session_id}/steps",response_model=MissionStepsResponse)
def get_mission_steps(session_id: str):
    if not global_store:
        raise HTTPException(status_code=500,detail="Store not initialized")
    steps=global_store.list_steps(session_id)
    if not steps:
        raise HTTPException(status_code=404,detail="Mission not found")
    return MissionStepsResponse(session_id=session_id,steps=steps)


@app.websocket("/api/events")
async def websocket_events(websocket: WebSocket):
    await websocket.accept()
    if not global_bus:
        await websocket.close(code=1011,reason="EventBus not initialized")
        return

    queue=asyncio.Queue()

    def on_event(event: KernelEvent) -> None:
        queue.put_nowait(event)

    global_bus.subscribe("*",on_event)
    _ws_clients.add(websocket)

    try:
        while True:
            event = await queue.get()
            await websocket.send_json({
                "event_type": event.__class__.__name__,
                "payload": event.model_dump(mode="json")
            })
    except (WebSocketDisconnect,asyncio.CancelledError):
        pass
    finally:
        _ws_clients.discard(websocket)


@app.post("/api/events/ingest")
async def ingest_event(event_data: dict):
    """Receive raw events from a CLI process and broadcast to all connected WebSocket clients."""
    dead = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_json(event_data)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)
    return {"ok": True, "clients": len(_ws_clients)}


_static_dir=Path(os.path.dirname(__file__))/"static"
if _static_dir.exists():
    app.mount("/",StaticFiles(directory=str(_static_dir),html=True),name="static")