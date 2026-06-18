from fastapi import APIRouter, Depends, HTTPException, status
from .schemas import TokenResp, UserReg, UserResponse
from sqlalchemy import select
from .models import User
from sqlalchemy.orm import Session
from .database import get_db
from .settings import sequrity, AuthService, get_current_user
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/user", tags=['user'])

@router.post("/regis")
def register(
    user: UserReg,
    db: Session = Depends(get_db)
):
    service = AuthService(db)
    service.register(user)

@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), 
    db: Session = Depends(get_db)
):
    result = db.execute(select(User).where(User.user_name == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not sequrity.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный user_name или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = sequrity.create_jwt_token({"sub": str(user.user_id)})
    return {
        "access_token": access_token, 
        "token_type": "bearer"
    }

@router.get("/me", response_model= UserResponse)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = (
        select(User)
        .where(User.user_id == current_user.user_id)
    )
    result = db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code= status.HTTP_401_UNAUTHORIZED,
            detail="user not found or token is invalid"
        )
    return user