import pandas as pd
from sqlalchemy import create_engine
import os
from sqlalchemy.orm import Session
from .models import Coordinates as ContainerCell
from .settings import settings
import requests

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

def calculation_score(delta_time, cell, path_from):
    
    score = 0
    cell_list = list(cell)

    if path_from == 1:
        path_from = 5
    elif path_from == 2:
        path_from = 15
    elif path_from == 3:
        path_from = 25

    layer = cell_list[0]
    column = cell_list[1]
    num_row = int(''.join(cell_list[2:]))

    d = (abs(num_row - path_from))/25

    if delta_time <= 4:

        if layer == 'A':
            layer = 1
        elif layer == 'B':
            layer = 2
        elif layer == 'C':
            layer = 3

        if column == 'X':
            column = 1
        elif column == 'Y':
            column = 0.5
        elif column == 'Z':
            column = 1
        
        score = (100*(1-d) + 60*(layer/3) + 20*column)/180
        return round(score, 2)
        
    elif 4 < delta_time <= 10:

        if layer == 'A':
            layer = 0.5
        elif layer == 'B':
            layer = 1
        elif layer == 'C':
            layer = 0.5

        if column == 'X':
            column = 0.5
        elif column == 'Y':
            column = 1
        elif column == 'Z':
            column = 0.5
        
        score = (60*(1-d) + 40*layer + 10*column)/110
        return round(score, 2)
    
    elif delta_time > 10:

        if layer == 'A':
            layer = 1
        elif layer == 'B':
            layer = 0.5
        elif layer == 'C':
            layer = 0

        if column == 'X':
            column = 0.5
        elif column == 'Y':
            column = 1
        elif column == 'Z':
            column = 0.5

        d_ideal = abs(d - 7/25)

        score = (30*(1-d_ideal) + 70*layer + 5*column)/105
        return round(score, 2)

def check_stack_size(
    db: Session,
    cell_id: str,
    size: int
) -> bool:
    EMPTY_CELL = "0"
    cell_id_ = list(cell_id)
    layer = cell_id_[0]
    column = cell_id_[1]
    row = cell_id_[2:]
    
    # слой A
    if layer == "A":
        return True

    # слой B
    if layer == "B":

        a_cell = db.query(ContainerCell).filter(
            ContainerCell.cell_id == f"A{column}{row}"
        ).first()

        if a_cell is None:
            return False

        if a_cell.value == EMPTY_CELL:
            return False

        return a_cell.size == size

    # слой C
    if layer == "C":

        a_cell = db.query(ContainerCell).filter(
            ContainerCell.cell_id == f"A{column}{row}"
        ).first()

        b_cell = db.query(ContainerCell).filter(
            ContainerCell.cell_id == f"B{column}{row}"
        ).first()

        if a_cell is None or b_cell is None:
            return False

        if a_cell.value == EMPTY_CELL:
            return False

        if b_cell.value == EMPTY_CELL:
            return False

        return a_cell.size == size and b_cell.size == size

    return False

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
        }
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]