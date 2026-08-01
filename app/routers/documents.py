#documents.py

import os
import time
import requests
import shutil
import uuid
from twelvelabs import TwelveLabs 
from fastapi import APIRouter, UploadFile, BackgroundTasks, HTTPException, Depends, Request
from typing import Annotated
from sqlmodel import Session, select
import threading
from app.services.ai_agent import create_vector_db_with_docling
from app.database import engine
from app.database import Student, get_session, VideoMapping
#from app.services.ai_agent import create_vector_db_with_unstructured
#from app.services.ai_agent import create_vector_db_with_docling
from app.security import get_current_student

router = APIRouter(prefix="/documents", tags=["إدارة المناهج"])

# ==========================================
# إعداد مجلدات الحفظ المركزية
# ==========================================
UPLOAD_DIR = "storage/pdfs"
DB_DIR = "vector_dbs"
VIDEO_DIR = "storage/videos" 
IMAGES_DIR = "storage/images" # الإضافة المتوافقة مع تحديث استخراج الصور

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)

# متغيرات بيئية لمنصة Mux
MUX_TOKEN_ID = os.getenv("MUX_TOKEN_ID")
MUX_TOKEN_SECRET = os.getenv("MUX_TOKEN_SECRET")

# الاستيراد الجديد

@router.post("/upload/")
def upload_document(
    file: UploadFile,
    current_student: Annotated[Student, Depends(get_current_student)]
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="يسمح فقط برفع ملفات PDF")
        
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    db_path = os.path.join(DB_DIR, "qdrant_db1")
    
    # توجيه المعالجة للخلفية عبر Docling
    thread = threading.Thread(
        target=create_vector_db_with_docling,
        args=(file_path, db_path)
    )
    thread.start()
    
    return {"message": f"تم استلام المستند {file.filename} بنجاح. جاري المعالجة محلياً عبر Docling."}



# ==========================================
# 1. قسم معالجة ملفات PDF 
# ==========================================
"""
@router.post("/upload/")
def upload_document(
    file: UploadFile,
    current_student: Annotated[Student, Depends(get_current_student)]
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="يسمح فقط برفع ملفات PDF")
    
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # استخدام معالج Docling + Qdrant الجديد في الخلفية
    thread = threading.Thread(
        target=create_vector_db_with_docling,
        args=(file_path, None) # لا نحتاج لمسار DB محلي لأننا نرفع لـ Qdrant
    )
    thread.start()
    
    return {
        "message": f"تم استلام المستند {file.filename} بنجاح. السيرفر حر الآن وجاري المعالجة والهيكلة الهجينة عبر Docling."
    }

"""
@router.get("/")
async def list_documents(current_student: Annotated[Student, Depends(get_current_student)]):
    try:
        docs = []
        if os.path.exists(DB_DIR):
            for i, name in enumerate(os.listdir(DB_DIR)):
                if name.endswith("_db"):
                    docs.append({"id": i+1, "filename": name.replace("_db", ".pdf")})
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail="تعذر قراءة قائمة المناهج")

# ==========================================
# 2. قسم معالجة الفيديوهات (الرفع المبدئي)
# ==========================================
def upload_to_mux(file_path: str):
    """النسخة المحصنة لرفع الفيديو إلى Mux بذكاء"""
    print("[Mux]: جاري طلب رابط الرفع من المنصة...")
    auth = (MUX_TOKEN_ID, MUX_TOKEN_SECRET)

    # التحديث لمعمارية MUX الجديدة (Static Renditions)
    data = {
        "cors_origin": "*", 
        "new_asset_settings": {
            "playback_policy": ["public"],
            "static_renditions": [
                {"resolution": "highest"} # الإعداد الحديث للحصول على MP4 خام
            ]
        }
    }
    
    try:
        res = requests.post("https://api.mux.com/video/v1/uploads", json=data, auth=auth)
        res.raise_for_status()
        upload_data = res.json()["data"]
        upload_url = upload_data["url"]
        upload_id = upload_data["id"]

        print(f"[Mux]: جاري ضخ الفيديو إلى السحابة ({os.path.basename(file_path)})...")
        
        with open(file_path, "rb") as f:
            put_res = requests.put(upload_url, data=f, headers={"Content-Type": "video/mp4"})
            put_res.raise_for_status()

        print("[Mux]: جاري المعالجة الأولية...")
        asset_id = None
        attempts = 0
        max_attempts = 60 
        
        while attempts < max_attempts:
            time.sleep(3)
            attempts += 1
            
            check_res = requests.get(f"https://api.mux.com/video/v1/uploads/{upload_id}", auth=auth)
            status_data = check_res.json()["data"]
            current_status = status_data["status"]
            
            if current_status == "asset_created":
                asset_id = status_data["asset_id"]
                break
            elif current_status == "errored":
                print("[Mux Error]: حدث خطأ في خوادم Mux أثناء التحويل.")
                return None
        
        if not asset_id:
            print("[Mux Error]: انتهى وقت الانتظار الآمن ولم ينتهِ Mux من المعالجة.")
            return None

        asset_res = requests.get(f"https://api.mux.com/video/v1/assets/{asset_id}", auth=auth)
        playback_id = asset_res.json()["data"]["playback_ids"][0]["id"]
        
        print(f"[Mux]: تم الرفع المبدئي بنجاح! Playback ID: {playback_id}")
        return playback_id

    except requests.exceptions.HTTPError as e:
        print(f"❌ [Mux API Error Details]: {e.response.text}")
        return None
    except Exception as e:
        print(f"❌ [Mux Error]: فشل الاتصال بمنصة Mux - {e}")
        return None

# ==========================================
# 3. قسم هندسة Webhook (الربط السحابي)
# ==========================================
@router.post("/mux-webhook/")
async def mux_webhook_handler(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    
    if payload.get("type") == "video.asset.ready":
        playback_ids = payload["data"].get("playback_ids", [])
        
        if playback_ids:
            mux_playback_id = playback_ids[0]["id"]
            
            static_renditions = payload["data"].get("static_renditions", {})
            mp4_status = static_renditions.get("status")
            
            if mp4_status == "ready":
                mp4_files = static_renditions.get("files", [])
                file_name = mp4_files[0].get("name", "highest.mp4") if mp4_files else "highest.mp4"
                
                mp4_url = f"https://stream.mux.com/{mux_playback_id}/{file_name}"
                # تمرير المهمة للخلفية (بدون Session)
                background_tasks.add_task(link_mux_to_twelvelabs, mux_playback_id, mp4_url)

    return {"status": "success"}

def link_mux_to_twelvelabs(mux_playback_id: str, mp4_url: str):
    TL_API_KEY = os.getenv("TWELVE_LABS_API_KEY")
    TL_INDEX_ID = os.getenv("TWELVE_LABS_INDEX_ID")
    
    # فتح جلسة خاصة ومستقلة للعمليات في الخلفية
    with Session(engine) as session:
        try:
            client = TwelveLabs(api_key=TL_API_KEY)
            print(f"\n🚀 [Twelve Labs]: جاري إنشاء مهمة فهرسة للفيديو عبر الرابط الخام...")
            
            task = client.tasks.create(
                index_id=TL_INDEX_ID,
                video_url=mp4_url
            )
            client.tasks.wait_for_done(task_id=task.id)
            completed_task = client.tasks.retrieve(task.id)
            
            video_record = session.exec(select(VideoMapping).where(VideoMapping.mux_playback_id == mux_playback_id)).first()
            if video_record:
                video_record.twelvelabs_asset_id = completed_task.video_id
                session.add(video_record)
                session.commit()
                print(f"🎉 [النظام]: تم الربط السحابي المزدوج بنجاح: Mux({mux_playback_id}) <-> TwelveLabs({completed_task.video_id})")
                
        except Exception as e:
            print(f"❌ [النظام]: خطأ أثناء ربط Webhook مع Twelve Labs: {e}")

# ==========================================
# 4. المعالجة المزدوجة للفيديو
# ==========================================
def process_video_in_background(file_path: str, file_name: str):
    """تعمل في الخلفية: ترفع لـ MUX و Twelve Labs مباشرة من جهازك (بدون انتظار Webhooks)"""
    
    # 1. التحقق السريع من قاعدة البيانات
    with Session(engine) as session:
        existing_video = session.exec(select(VideoMapping).where(VideoMapping.video_title == file_name)).first()
        if existing_video and existing_video.twelvelabs_asset_id:
            print(f"\n⚡ [النظام - كاش ذكي]: الملف '{file_name}' تم رفعه مسبقاً!")
            return

    print(f"\n⏳ [النظام]: بدء خط المعالجة المزدوج للفيديو ({file_name})...")
    
    # 2. الرفع إلى MUX
    mux_playback_id = upload_to_mux(file_path)
    
    # 3. الرفع المباشر إلى Twelve Labs
    TL_API_KEY = os.getenv("TWELVE_LABS_API_KEY")
    TL_INDEX_ID = os.getenv("TWELVE_LABS_INDEX_ID")
    tl_video_id = None
    
    if mux_playback_id and TL_API_KEY and TL_INDEX_ID:
        try:
            print("⏳ [Twelve Labs]: جاري رفع الفيديو مباشرة من جهازك إلى السحابة للفهرسة...")
            client = TwelveLabs(api_key=TL_API_KEY)
            
            with open(file_path, "rb") as video_stream:
                task = client.tasks.create(
                    index_id=TL_INDEX_ID, 
                    video_file=video_stream 
                )
                client.tasks.wait_for_done(task_id=task.id)
                completed_task = client.tasks.retrieve(task.id)
                tl_video_id = completed_task.video_id
                print(f"✅ [Twelve Labs]: تم استلام وفهرسة الفيديو بنجاح.")
                
        except Exception as e:
            print(f"❌ [Twelve Labs] خطأ أثناء الرفع: {e}")

    # 4. حفظ المعرفين معاً في قاعدة البيانات وربطهما
    if mux_playback_id and tl_video_id:
        with Session(engine) as session:
            try:
                new_video = VideoMapping(
                    video_title=file_name,
                    mux_playback_id=mux_playback_id,
                    twelvelabs_asset_id=tl_video_id
                )
                session.add(new_video)
                session.commit()
                print("\n=======================================================")
                print(f"🎉 [الربط والتحصين السحابي تـم بنجـاح تام]")
                print("=======================================================\n")
            except Exception as e:
                print(f"❌ [النظام]: خطأ أثناء حفظ الفيديو الجديد: {e}")
    else:
        print("❌ [النظام]: فشل اكتمال الربط المزدوج. يرجى مراجعة الأخطاء أعلاه.")

# ==========================================
# 5. مسار استقبال الفيديوهات الرئيسي
# ==========================================
@router.post("/upload-video/")
def upload_video_endpoint(
    file: UploadFile, 
    background_tasks: BackgroundTasks,
    current_student: Annotated[Student, Depends(get_current_student)]
):
    """المسار الأساسي لاستقبال الفيديو من الواجهة الأمامية"""
    if not file.filename.endswith((".mp4", ".mov", ".mkv")):
        raise HTTPException(status_code=400, detail="يسمح فقط برفع ملفات الفيديو")
    
    file_path = os.path.join(VIDEO_DIR, file.filename)
    
    # الحفظ على شكل حزم (Stream) لحماية الذاكرة
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # تمرير المهمة للخلفية للبدء في المعالجة
    background_tasks.add_task(process_video_in_background, file_path, file.filename)
    
    return {"message": f"تم استلام الفيديو {file.filename} بنجاح. السيرفر حر الآن، وجاري المعالجة في الخلفية."}