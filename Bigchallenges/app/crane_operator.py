import asyncio
import httpx
import websockets
import argparse  

BASE_URL = "http://localhost:8000"

async def main(username: str, password: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/user/login", 
            data={"username": username, "password": password}
        )
        if response.status_code != 200:
            print(f"Ошибка логина: {response.json()}")
            return

        token = response.json()["access_token"]
        # print(f"Токен получен для {username}")

    url = f"ws://localhost:8000/ws?token={token}"
    async with websockets.connect(url) as ws:
        print(f"Крановщик {username} подключён, жду задания...")
        while True:
            msg = await ws.recv()
            print(f"[{username}] Получено: {msg}")

parser = argparse.ArgumentParser()
parser.add_argument("--username", required=True)
parser.add_argument("--password", required=True)
args = parser.parse_args()

asyncio.run(main(args.username, args.password))