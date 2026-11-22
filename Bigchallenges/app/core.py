from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings_(BaseSettings):

    DB_URL: str
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    OPENROUTER_API_KEY: str

    # Площадка: задаётся под конкретного заказчика (можно переопределить в .env)
    YARD_LAYERS: str = "ABC"          # ярусы снизу вверх
    YARD_COLUMNS: str = "XYZ"         # колонны, крайние — первая и последняя
    YARD_ROWS: int = 30
    YARD_PATH_ROWS: str = "5,15,25"   # ряды, возле которых проходят пути 1, 2, 3, ...
    YARD_CRANES: str = "Кран 1,Кран 2"  # краны, создаваемые при первом запуске

    # Параметры оценки ячейки
    SCORE_URGENT_HOURS: float = 96
    SCORE_MEDIUM_HOURS: float = 240
    SCORE_LOWER_PENALTY: float = 0.5

    # Хранение (условный тариф, заменяется прайсом терминала):
    # первые STORAGE_FREE_DAYS суток бесплатно, далее ставка за TEU в сутки (40 фут. = 2 TEU)
    STORAGE_FREE_DAYS: int = 2
    STORAGE_RATE_TEU_DAY: float = 100

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings_()