import base64, hashlib, hmac, io, secrets, string

import segno
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .core import settings
from .database import get_db
from .models import User, Role, Crane
from .schemas import UserReg, UserResponse
from .settings import sequrity, AuthService, get_current_user, manager as ws_manager

router = APIRouter(prefix="/user", tags=['user'])

ROLES = {r.value for r in Role}


class EmployeeIn(BaseModel):
    first_name: str
    last_name: str
    role: str


class EmployeesIn(BaseModel):
    employees: list[EmployeeIn]


class EmployeeActive(BaseModel):
    is_active: bool


class BadgeLogin(BaseModel):
    code: str


def require_manager(user: User):
    if user.role != Role.manager:
        raise HTTPException(403, "Только начальник площадки")


def new_password(n: int = 10) -> str:
    # без похожих символов (0/O, 1/l/I), чтобы пароль легко продиктовать и переписать
    alphabet = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
    return "".join(secrets.choice(alphabet) for _ in range(n))


def badge_digest(secret: str, salt: str | None = None) -> str:
    """Хеш секрета пропуска с солью: «соль$SHA-256(соль + секрет)»."""
    salt = salt or secrets.token_hex(8)
    return f"{salt}${hashlib.sha256((salt + secret).encode()).hexdigest()}"


def badge_ok(stored: str | None, secret: str) -> bool:
    if not stored or "$" not in stored:
        return False
    salt = stored.split("$", 1)[0]
    return hmac.compare_digest(stored, badge_digest(secret, salt))


TRANSLIT = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                    ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                     "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))


def make_login(db: Session, first: str, last: str) -> str:
    """Логин из фамилии и первой буквы имени: «Иванов Пётр» → ivanov.p (ivanov.p2, если занят)."""
    tr = lambda w: "".join(TRANSLIT.get(ch, ch) for ch in w.lower() if ch.isalnum() or ch in TRANSLIT)
    base = f"{tr(last)}.{tr(first)[:1]}".strip(".") or "user"
    login, n = base, 1
    while db.execute(select(User).where(User.user_name == login)).first():
        n += 1; login = f"{base}{n}"
    return login


def qr_png_b64(code: str) -> str:
    buf = io.BytesIO()
    segno.make(code, error="m").save(buf, kind="png", scale=8, border=2)
    return base64.b64encode(buf.getvalue()).decode()


def new_badge(u: User) -> str:
    secret = secrets.token_urlsafe(24)
    u.badge_hash = badge_digest(secret)
    return f"EDKT:{u.user_id}:{secret}"


def token_for(user: User) -> dict:
    return {"access_token": sequrity.create_jwt_token({"sub": str(user.user_id)}), "token_type": "bearer"}


def has_manager(db: Session) -> bool:
    return db.scalar(select(func.count(User.user_id)).where(User.role == Role.manager)) > 0


@router.get("/setup")
def setup_state(db: Session = Depends(get_db)):
    """Первый запуск (или старая база без начальника): страница входа предлагает создать начальника."""
    return {"needs_setup": not has_manager(db),
            "open_registration": settings.OPEN_REGISTRATION}


@router.post("/regis")
def register(user: UserReg, db: Session = Depends(get_db)):
    """Самостоятельная регистрация разрешена, только пока на площадке нет начальника (создаётся начальник)
    или на демо-стенде (OPEN_REGISTRATION=true). В остальных случаях сотрудников заводит начальник."""
    if not settings.OPEN_REGISTRATION:
        if has_manager(db):
            raise HTTPException(403, "Сотрудников регистрирует начальник площадки")
        user = UserReg(user_name=user.user_name, password=user.password, role=Role.manager.value)
    if user.role not in ROLES:
        raise HTTPException(422, f"Роль: {', '.join(sorted(ROLES))}")
    AuthService(db).register(user)
    return {"status": "success", "role": user.role}


@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.user_name == form_data.username)).scalar_one_or_none()
    if not user or not sequrity.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный user_name или пароль",
                            headers={"WWW-Authenticate": "Bearer"})
    if not user.is_active:
        raise HTTPException(403, "Учётная запись отключена начальником площадки")
    return token_for(user)


@router.post("/login_badge")
def login_badge(data: BadgeLogin, db: Session = Depends(get_db)):
    """Вход по пропуску: QR-код вида EDKT:<id>:<секрет>. В базе хранится только хеш секрета."""
    try:
        prefix, uid, secret = data.code.strip().split(":", 2)
        assert prefix == "EDKT"
        user = db.get(User, int(uid))
    except Exception:
        raise HTTPException(401, "Код пропуска не распознан")
    if not user or not badge_ok(user.badge_hash, secret):
        raise HTTPException(401, "Пропуск недействителен")
    if not user.is_active:
        raise HTTPException(403, "Учётная запись отключена начальником площадки")
    return token_for(user)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


# ---------- начальник площадки: сотрудники ----------

@router.get("/employees")
def list_employees(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_manager(current_user)
    cranes = {}
    for c in db.query(Crane).all():
        if c.operator_id:
            cranes[c.operator_id] = c.name
    online = set(ws_manager.active_connections)
    return [{"user_id": u.user_id, "user_name": u.user_name, "first_name": u.first_name, "last_name": u.last_name,
             "role": u.role.value, "is_active": u.is_active,
             "has_badge": bool(u.badge_hash), "crane": cranes.get(u.user_id), "online": u.user_id in online}
            for u in db.query(User).order_by(User.user_id).all()]


@router.post("/employees")
def create_employees(data: EmployeesIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Начальник заводит сразу несколько сотрудников. Для каждого программа составляет логин,
    генерирует пароль и выпускает пропуск с QR-кодом. Пароль и пропуск показываются один раз —
    в базе остаются только их хеши."""
    require_manager(current_user)
    if not data.employees:
        raise HTTPException(422, "Список сотрудников пуст")
    for e in data.employees:
        if e.role not in ROLES:
            raise HTTPException(422, f"Роль: {', '.join(sorted(ROLES))}")
        if not e.first_name.strip() or not e.last_name.strip():
            raise HTTPException(422, "Укажите имя и фамилию каждого сотрудника")
    out = []
    for e in data.employees:
        password = new_password()
        u = User(user_name=make_login(db, e.first_name.strip(), e.last_name.strip()), role=e.role,
                 first_name=e.first_name.strip(), last_name=e.last_name.strip(),
                 password_hash=sequrity.hash_password(password))
        db.add(u); db.flush()                    # нужен user_id для кода пропуска
        code = new_badge(u)
        out.append({"user_id": u.user_id, "user_name": u.user_name, "first_name": u.first_name,
                    "last_name": u.last_name, "role": e.role, "password": password,
                    "badge_code": code, "qr_png": qr_png_b64(code)})
    db.commit()                                  # все сотрудники создаются одной транзакцией
    return out


def get_employee(db: Session, user_id: int) -> User:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "Сотрудник не найден")
    return u


@router.post("/employees/{user_id}/password")
def reset_password(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_manager(current_user)
    u = get_employee(db, user_id)
    password = new_password()
    u.password_hash = sequrity.hash_password(password)
    db.commit()
    return {"user_id": u.user_id, "user_name": u.user_name, "password": password}


@router.post("/employees/{user_id}/badge")
def issue_badge(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Выпустить пропуск с QR-кодом. Новый пропуск отменяет старый (например, если пропуск потерян)."""
    require_manager(current_user)
    u = get_employee(db, user_id)
    code = new_badge(u)
    db.commit()
    return {"user_id": u.user_id, "user_name": u.user_name, "first_name": u.first_name, "last_name": u.last_name,
            "role": u.role.value, "badge_code": code, "qr_png": qr_png_b64(code)}


@router.patch("/employees/{user_id}")
def set_active(user_id: int, data: EmployeeActive, current_user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    """Отключить (уволен, утерян пропуск) или снова включить сотрудника."""
    require_manager(current_user)
    u = get_employee(db, user_id)
    if u.user_id == current_user.user_id and not data.is_active:
        raise HTTPException(409, "Нельзя отключить самого себя")
    u.is_active = data.is_active
    if not data.is_active:
        u.badge_hash = None
        for c in db.query(Crane).filter(Crane.operator_id == u.user_id):
            c.operator_id = None
    db.commit()
    return {"user_id": u.user_id, "is_active": u.is_active}
