#database.py

from sqlmodel import Field, SQLModel, create_engine, Session
from typing import Optional
from datetime import datetime, timezone

# تعريف جدول الطلاب السابق
class Student(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    university_id: str = Field(unique=True, index=True)
    full_name: str
    hashed_password: str

# [إضافة جديدة]: جدول هيكل الفيديوهات والربط المركزي
class VideoMapping(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    video_title: str
    mux_playback_id: str = Field(unique=True, index=True)
    twelvelabs_asset_id: Optional[str] = Field(default=None, unique=True, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

sqlite_url = "sqlite:///ibb_secure_university.db"
engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

def get_session():
    with Session(engine) as session:
        yield session