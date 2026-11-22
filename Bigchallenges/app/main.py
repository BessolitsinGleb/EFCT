import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from .database import engine, Base, sync_session
from sqlalchemy import inspect, text
from .yard import ensure_yard_cells, ensure_cranes
from . import models  # noqa: F401  (регистрирует таблицы, в т.ч. cranes и placement_rules)
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
    Base.metadata.create_all(bind=engine)
    # таблица tasks могла быть создана до появления кранов: добавляем колонку, если её нет
    with engine.begin() as conn:
        if "crane_id" not in [c["name"] for c in inspect(conn).get_columns("tasks")]:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN crane_id INTEGER REFERENCES cranes(crane_id)"))
        if "size" not in [c["name"] for c in inspect(conn).get_columns("movement_information")]:
            conn.execute(text("ALTER TABLE movement_information ADD COLUMN size INTEGER"))
        ucols = [c["name"] for c in inspect(conn).get_columns("users")]
        if "is_active" not in ucols:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"))
        if "badge_hash" not in ucols:
            conn.execute(text("ALTER TABLE users ADD COLUMN badge_hash VARCHAR"))
        for col in ("first_name", "last_name"):
            if col not in ucols:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} VARCHAR"))
    # новая роль «начальник» в старой базе: значение перечисления добавляется вне транзакции
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("ALTER TYPE role ADD VALUE IF NOT EXISTS 'manager'"))
    with sync_session() as db:
        created = ensure_yard_cells(db)
        if created:
            print(f"Создано ячеек площадки: {created}")
        ensure_cranes(db)

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
    uvicorn.run("app.main:app", host="0.0.0.0")


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