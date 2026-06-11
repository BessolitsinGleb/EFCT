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

def calculation_score(delta_time, cell, path_from, lower_delta_time):
    
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

    if delta_time <= 96:

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

        if (lower_delta_time is not None and lower_delta_time < delta_time):
            score *= 0.5

        return round(score, 2)
        
    elif 96 < delta_time <= 240:

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

        if (lower_delta_time is not None and lower_delta_time < delta_time):
            score *= 0.5

        return round(score, 2)
    
    elif delta_time > 240:

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

        d_ideal = abs(d - 5/25)

        score = (30*(1-d_ideal) + 70*layer + 5*column)/105

        if (lower_delta_time is not None and lower_delta_time < delta_time):
            score *= 0.5
            
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
            ContainerCell.cell_id == f"A{''.join(cell_id_[1:])}"
        ).first()

        if not a_cell:
            return False

        if a_cell.value == EMPTY_CELL:
            return False

        return a_cell.size == size

    # слой C
    if layer == "C":

        a_cell = db.query(ContainerCell).filter(
            ContainerCell.cell_id == f"A{''.join(cell_id_[1:])}"
        ).first()

        b_cell = db.query(ContainerCell).filter(
            ContainerCell.cell_id == f"B{''.join(cell_id_[1:])}"
        ).first()

        if not a_cell or not b_cell:
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

def calculation_movement_price(mov_type, size, cell_1, cell_2= None, path= None):
    
    row_price = 0
    col_price = 0 
    if size == 20:
        power_price = 1
    if size == 40:
        power_price = 2

    if mov_type == "adding" or mov_type == 'loading':

        lay_price = 0
        CONST_PRICE = 50 # цена за поднятие/опускание контейнера на/с транспорта
        list_cell_1 = list(cell_1)
        layer = list_cell_1[0]
        column = list_cell_1[1]
        row = int(''.join(list_cell_1[2:]))
        
        if path == 1:
            path_to = 5
        if path == 2:
            path_to = 15
        if path == 3:
            path_to = 25

        if layer == 'A':
            lay_price = 3
        if layer == 'B':
            lay_price = 2
        if layer == 'C':
            lay_price = 1
        
        if column == 'X' or column == 'Z':
            col_price = 2 
        if column == 'Y':
            col_price = 3
        
        row_price = abs(row - path_to)/25

        price = power_price * (25 * lay_price + 35 * col_price + 100 * row_price + CONST_PRICE)
        return price
    
    if mov_type == 'rearrangement':

        lay_price_up = 0
        lay_price_down = 0

        list_cell_from = list(cell_1)
        layer_from = list_cell_from[0]
        column_from = list_cell_from[1]
        if column_from == 'X':
            column_from = 1
        if column_from == 'Y':
            column_from = 2
        if column_from == 'Z':
            column_from = 3
        row_from = int(''.join(list_cell_from[2:]))

        list_cell_to = list(cell_2)
        layer_to = list_cell_to[0]
        column_to = list_cell_to[1]
        if column_to == 'X':
            column_to = 1
        if column_to == 'Y':
            column_to = 2
        if column_to == 'Z':
            column_to = 3
        row_to = int(''.join(list_cell_to[2:]))

        row_price = abs(row_to - row_from)/29
        
        if layer_from == 'A':
            lay_price_up = 3
        if layer_from == 'B':
            lay_price_up = 2
        if layer_from == 'C':
            lay_price_up = 1

        if layer_to == 'A':
            lay_price_down = 3
        if layer_to == 'B':
            lay_price_down = 2
        if layer_to == 'C':
            lay_price_down = 1
        
        col_price = abs(column_from - column_to)

        price = power_price * (lay_price_up * 25 + lay_price_down * 25 + col_price * 50 + row_price * 500)
        return round(price)
