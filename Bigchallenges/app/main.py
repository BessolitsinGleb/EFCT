import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from .database import engine, Base
from fastapi.middleware.cors import CORSMiddleware
from .routers import router
from .routers_2 import router as router_2
from .users import router as user_router
from .settings import manager, verify_token

app = FastAPI(title="EFCT")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(user_router)
app.include_router(router_2)

@app.on_event("startup")
def on_startup():
    with engine.begin() as conn:
        Base.metadata.create_all(bind=engine)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    user = verify_token(token)
    if user is None:
        await websocket.close(code=1008)
        return
    await manager.connect(user.user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user.user_id, websocket)  

if '__main__'==__name__:
    uvicorn.run("main.app", host= "0.0.0.0")


"""
1. Добавить на страницу крановщика пульт управления краном(ехать по рельсам, движение кабины, опускать поднимать захват(забыл название), 
    взять отпустить контейнер)

2. Собрать где-то каким-то чудом терминал маленький и сделать реализацию пульта
   2.1 закупить компоненты(хз какие, есп 32 точно типо для старта)
   2.2 сделать платы, по электронике все сделать короче
   2.3 напечатать где-то кран на рельзах и контейнеров несколько
   2.4 добавить "точность движений" типо 1 клик сдвиг на опред растояние 
   2.5 тестить 
"""