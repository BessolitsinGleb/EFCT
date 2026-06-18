from passlib.context import CryptContext
from datetime import timedelta, datetime
from jose import jwt, JWTError
from .database import sync_session
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import User, Task
from fastapi import HTTPException, Depends
from .database import get_db
from fastapi.security import OAuth2PasswordBearer
from .core import settings

def create_access_token(data: dict):
        return jwt.encode(data, settings.SECRET_KEY, algorithm= settings.JWT_ALGORITHM)

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

class Sequrity():

    @staticmethod
    def hash_password(password: str):
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(password: str, hash: str) -> bool:
        return pwd_context.verify(password, hash)

    @staticmethod
    def create_jwt_token(user_data: dict):
        if hasattr(user_data, "__dict__"):
            to_encode = dict(user_data.__dict__)
            to_encode.pop('_sa_instance_state', None)
        else:
            to_encode = user_data.copy()
        expire = datetime.utcnow() + timedelta(minutes=30)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def create_token(data: dict):
        payload = data.copy()  # не мутируем оригинал
        payload["exp"] = datetime.utcnow() + timedelta(hours=24)
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def decode_token(token: str):
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            user_id = int(payload.get("sub"))

            with sync_session() as session:
                res = session.execute(
                    select(User).where(User.user_id == user_id)
                )
                user = res.scalar_one_or_none()
            return user
        except JWTError:
            return None

sequrity = Sequrity()

class AuthLogin:    
    def login(self, user_credentials):
        user = self.db.query(User).filter(User.user_name == user_credentials.user_name).first()
        
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        token_data = sequrity.create_jwt_token(user) 

        token = self.security.create_access_token(data=token_data)
        return token

class UserRepo():
    def __init__(self, db: Session):
        self.db= db

    def create_user(self, role, password, user_name):
        user = User(
            role=role,
            password_hash=password,
            user_name= user_name,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_id(self, user_idd):
        result = self.db.execute(
            select(User).where(User.user_id == user_idd)
        )
        return result.scalar_one_or_none()

    def get_by_name(self, user_name):
        result = self.db.execute(
            select(User).where(User.user_name == user_name)
        )
        return result.scalar_one_or_none()
    
class AuthService:

    def __init__(self, db):
        self.user_repo = UserRepo(db)

    def register(self, data):

        user = self.user_repo.get_by_name(data.user_name)

        if user:
            raise HTTPException(400, "User уже существует")

        hashed_password = sequrity.hash_password(data.password)

        new_user = self.user_repo.create_user(
            role=data.role,
            user_name=data.user_name,
            password=hashed_password
        )
        return new_user

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/user/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401)
    except:
        raise HTTPException(status_code=401)

    user = db.get(User, int(user_id))
    return user

def get_auth_service(db: Session = Depends(get_db)):
    repo = UserRepo(db)
    return AuthService(repo, security= sequrity)

# ws_manager.py
# ws_manager.py
from fastapi import WebSocket

class ConnectionManager:
    
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        print(f"Крановщик {user_id} подключён. Всего соединений: {len(self.active_connections[user_id])}")

    def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        print(f"Крановщик {user_id} отключился")

    async def send_to_user(self, user_id: int, payload: dict) -> bool:

        connections = self.active_connections.get(user_id, [])
        if not connections:
            print(f"Крановщик {user_id} не онлайн")
            return False

        dead_connections = []
        for ws in connections:
            try:
                await ws.send_json(payload)
            except Exception:
                dead_connections.append(ws)  
        for ws in dead_connections:
            self.active_connections[user_id].remove(ws)

        return True

    def get_online_users(self) -> list[int]:
        return list(self.active_connections.keys())

manager = ConnectionManager()

# notifications.py

async def notify_task_assigned(task: Task):

    delivered = await manager.send_to_user(
        task.assigned_to,
        {
            "type": "new_task",
            "task_id": task.id,
            "actions_count": len(task.actions),
        },
    )
    return delivered

from .core import settings
from .database import sync_session

def verify_token(token: str) -> User | None:
    print(f"=== verify_token вызван ===")
    print(f"Токен (первые 20 символов): {token[:20]}")
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        print(f"Payload decoded: {payload}")
        user_id = payload.get("sub")
        print(f"user_id: {user_id}")
        if user_id is None:
            print("user_id is None — выходим")
            return None
    except JWTError as e:
        print(f"JWTError: {e}")
        return None

    db = sync_session()
    try:
        user = db.query(User).filter(User.user_id == int(user_id)).first()
        print(f"User из БД: {user}")
        return user
    finally:
        db.close()