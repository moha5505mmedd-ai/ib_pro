#ai chat

from pydantic import BaseModel
from typing import Annotated, Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.database import Student
from app.security import get_current_student
from app.services.ai_agent import ask_dkm_agent

router = APIRouter(prefix="/chat", tags=["الوكيل الذكي للمنصة"])

class ChatRequest(BaseModel):
    question: str
    search_mode: str = "docs"  # القيمة الافتراضية

@router.post("/")
async def chat_with_agent(
    request: ChatRequest,
    current_student: Annotated[Student, Depends(get_current_student)]
):
    thread_id = f"student_{current_student.university_id}"
    return StreamingResponse(
        ask_dkm_agent(
            question=request.question, 
            thread_id=thread_id,
            search_mode=request.search_mode # تمرير المسار للوكيل
        ),
        media_type="text/plain"
    )
    
    
