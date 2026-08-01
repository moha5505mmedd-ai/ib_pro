#app/security 


from typing import Annotated
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlmodel import Session, select
from app.database import Student, get_session

SECRET_KEY = "ibb_university_super_secret_key_dkm_project"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")

# دالة التفتيش للتأكد من هوية صاحب التوكن
def get_current_student(token: Annotated[str, Depends(oauth2_scheme)], session: Session = Depends(get_session)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        university_id: str = payload.get("sub")
        if university_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="البطاقة تالفة")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="البطاقة غير صالحة")
    
    student = session.exec(select(Student).where(Student.university_id == university_id)).first()
    if student is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="الطالب غير موجود")
    
    return student