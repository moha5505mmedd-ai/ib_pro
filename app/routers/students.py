#student.py

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from app.database import Student, get_session
from app.security import password_hash, get_current_student

router = APIRouter(prefix="/students", tags=["إدارة الطلاب"])

@router.post("/register/")
def register_student(
    university_id: str, 
    full_name: str, 
    password: str, 
    session: Session = Depends(get_session)
):
    existing_student = session.exec(select(Student).where(Student.university_id == university_id)).first()
    if existing_student:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="الرقم الجامعي مسجل مسبقاً!")
    
    hashed_pwd = password_hash.hash(password)
    new_student = Student(university_id=university_id, full_name=full_name, hashed_password=hashed_pwd)
    session.add(new_student)
    session.commit()
    return {"message": "تم تسجيل الطالب بنجاح"}

@router.get("/me/")
def read_student_profile(current_student: Annotated[Student, Depends(get_current_student)]):
    return {
        "message": f"مرحباً بك يا {current_student.full_name} في منصة DKM",
        "university_id": current_student.university_id,
        "security_status": "أنت تتصفح النظام الآن باتصال آمن ومشفر"
    }

# مسار الاستعلام عن كل الطلاب (تم إصلاحه وإزالة التعارض)
@router.get("/")
def read_all_students(
    current_student: Annotated[Student, Depends(get_current_student)],
    session: Session = Depends(get_session)
):
    try:
        students = session.exec(select(Student)).all()
        safe_students = [
            {"id": s.id, "university_id": s.university_id, "full_name": s.full_name}
            for s in students
        ]
        return safe_students
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))