FROM python:3.13-slim

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend

EXPOSE 8000

# настройки (SECRET_KEY, OPENROUTER_API_KEY, DB_URL) передаются через env_file в docker-compose.yml
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
