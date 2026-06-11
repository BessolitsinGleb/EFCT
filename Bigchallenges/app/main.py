import uvicorn
from fastapi import FastAPI
from .database import engine, Base
from fastapi.middleware.cors import CORSMiddleware
from .routers import router

app = FastAPI(title="Прототип терминала")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.on_event("startup")
def on_startup():
    with engine.begin() as conn:
        Base.metadata.create_all(bind=engine)

if '__main__'==__name__:
    uvicorn.run("main.app", host= "0.0.0.0")

"""
8. ОФОРМИТЬ ФРОНТЕНД КРАСИВО

11. Добавить вход по паролю и логину и он будет привязан к терминалу всему

12. добавить роли(приемосдатчик(уже создан) и крановщика - на текущий этап) и страницу от их лица

    1. крановщик: упрощенный интерфейс, выполняет команды, выходящие на экране.

    2. Логин - отвечает за терминал
    3. Пароль за роль(на данный этап приемосдатчик/крановщик)

13. Фильтр по компаниям сколько операций за конкретный период времени прошло у конкретной компании
    1. к каждой операции присвоить ценник(по условному каталогу)
        * 1. просчет ценника в зависимости от дальности передвижения, веса контейнера 
        * в movement_information добавить компанию и цену передвижения(расчет через отдельную функцию)

        !!!добавить эндпоинт выгрузки данных за опред период у конкретной компании и возможность его выгрузить в цсв файле  
"""