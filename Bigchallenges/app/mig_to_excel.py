import pandas as pd
from sqlalchemy import create_engine
import os

def migration():
    USER = "aleksejbessolicin"
    PASSWORD = "password"
    HOST = "localhost"
    PORT = "5432"
    DATABASE = "terminal"

    db_url = f"postgresql+psycopg2://{USER}:{PASSWORD}@{HOST}:{PORT}/{DATABASE}"

    try:
        engine = create_engine(db_url)
        query = "SELECT * FROM movement_information;"
        df = pd.read_sql_query(query, con=engine)
        
        filename = "movement_information.xlsx"
        if os.path.exists(filename):
            os.remove(filename)
            # print(f"Старый файл {filename} успешно удален.")

        df.to_excel(filename, index=False)
        # print(f"Данные успешно выгружены в {filename}")
        
    except Exception as e:
        print(f"Ошибка: {e}")
