#app/auth


from typing import Annotated
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.database import Student, get_session
from app.security import password_hash, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

# إنشاء الراوتر الخاص بالتوثيق
router = APIRouter(tags=["التوثيق وتسجيل الدخول"])

@router.post("/token")
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Session = Depends(get_session)
):
    student = session.exec(select(Student).where(Student.university_id == form_data.username)).first()
    
    if not student or not password_hash.verify(form_data.password, student.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="الرقم الجامعي أو كلمة المرور غير صحيحة",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": student.university_id, "exp": expire.timestamp()}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    
    return {"access_token": encoded_jwt, "token_type": "bearer"}