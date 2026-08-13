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
    
    
#اضافة الميكرفون


import os
import asyncio
import google.generativeai as genai
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.security import get_current_student
from app.database import Student

@router.post("/voice-to-text/")
async def transcribe_voice_endpoint(
    audio_file: UploadFile = File(...),
    current_student: Student = Depends(get_current_student)
):
    """
    مسار معزول لتحويل صوت الطالب إلى نص باستخدام الإرسال المباشر (Inline Data)
    لضمان سرعة الاستجابة وتجنب أخطاء رفع الملفات.
    """
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY10"))
    
    # 1. قراءة الملف في الذاكرة مباشرة
    content = await audio_file.read()
    
    # 2. حماية هندسية: التأكد من أن الميكروفون التقط صوتاً فعلياً
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="الملف الصوتي فارغ. يرجى التأكد من الميكروفون.")

    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = "أنت مساعد متخصص في تفريغ الصوت الأكاديمي. استمع إلى هذا المقطع الصوتي واكتب ما قيل فيه باللغة العربية بدقة، مع تصحيح أي أخطاء إملائية. أعد النص فقط بدون أي إضافات، أو مقدمات، أو شروحات."
        
        # 3. إرسال الصوت كبيانات حية (Inline) مع تحديد نوع الملف إجبارياً
        # نستخدم audio_file.content_type والذي سيكون غالباً audio/webm
        audio_part = {
            "mime_type": audio_file.content_type or "audio/webm",
            "data": content
        }
        
        response = await model.generate_content_async([prompt, audio_part])
        transcribed_text = response.text.strip()
        
        return {"text": transcribed_text}
        
    except Exception as e:
        print(f"\n❌ [تفاصيل خطأ جيميناي]: {type(e).__name__} - {str(e)}\n")
        raise HTTPException(status_code=500, detail=f"فشل تحليل الصوت: {str(e)}")