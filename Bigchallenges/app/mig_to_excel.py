import pandas as pd
from sqlalchemy import create_engine
import os
from sqlalchemy.orm import Session
from .models import Coordinates as ContainerCell
from .settings import settings
import re
import requests
from datetime import datetime, timezone
from sqlalchemy import text
from .placement import calculation_score as _score, calculation_movement_price as _price
from .yard import YARD, SCORING


def to_utc_naive(dt):
    """Приводит дату к UTC без часового пояса — так даты хранятся в БД."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def hours_until(dt):
    """Сколько часов осталось до даты dt (отрицательно, если дата прошла)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return round((to_utc_naive(dt) - now).total_seconds() / 3600, 2)

def migration():
    db_url = settings.DB_URL

    try:
        engine = create_engine(db_url)
        query = "SELECT * FROM movement_information;"
        df = pd.read_sql_query(query, con=engine)
        
        filename = "movement_information.csv"
        if os.path.exists(filename):
            os.remove(filename)
            # print(f"Старый файл {filename} успешно удален.")

        df.to_csv(filename, index=False)
        # print(f"Данные успешно выгружены в {filename}")
        
    except Exception as e:
        print(f"Ошибка: {e}")

def upload_company_mov(company: str,
                       start_data: datetime,
                       end_data: datetime):
    
    start_data_req = start_data.strftime("%Y-%m-%d %H:%M:%S")
    end_data_req = end_data.strftime("%Y-%m-%d %H:%M:%S")
    start_data_name = start_data.strftime('%y.%m.%d')
    end_data_name = end_data.strftime('%y.%m.%d')

    db_url = settings.DB_URL

    try:
        engine = create_engine(db_url)
        # параметризованный запрос: раньше название компании подставлялось f-строкой (SQL-инъекция)
        query = text("SELECT * FROM movement_information "
                     "WHERE company = :company AND movement_time BETWEEN :start AND :end")
        with engine.connect() as conn:
            df = pd.read_sql_query(query, con=conn,
                                   params={"company": company, "start": start_data_req, "end": end_data_req})

        safe_company = re.sub(r"[^A-Za-z0-9_\-]", "_", company)  # без «/», «..» и т. п. в имени файла
        filename = f"{safe_company}_reporting_from_{start_data_name}_to_{end_data_name}.csv"
        # отчёт отдаётся пользователю файлом (раньше сохранялся только на сервере);
        # utf-8-sig — чтобы Excel правильно открыл кириллицу
        return filename, df.to_csv(index=False).encode("utf-8-sig"), len(df)
    except Exception as e:
        print(f"error {e}")
        return None
            

def ask_ai(prompt: str):

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "model": "deepseek/deepseek-chat",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def calculation_score(delta_time, cell, path_from, lower_delta_time):
    """Оценка ячейки (логика — в placement.py, параметры площадки — из настроек)."""
    return _score(delta_time, cell, path_from, lower_delta_time, cfg=YARD, sc=SCORING)


def calculation_movement_price(mov_type, size, cell_1, cell_2=None, path=None):
    """Тариф операции (логика — в placement.py)."""
    return _price(mov_type, size, cell_1, cell_2=cell_2, path=path, cfg=YARD)
