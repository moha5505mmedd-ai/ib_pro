#main

import os
from fastapi import FastAPI
from tqdm import tqdm
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from twelvelabs import TwelveLabs
from qdrant_client import QdrantClient
# استيرادات المشروع المحلية
from app.database import engine, SQLModel
from app.routers import auth, students, documents, ai_chat
from app.services.ai_agent import load_latest_vectorstore

# ==========================================
# 1. دوال الإعداد الآلي لمنصة Twelve Labs
# ==========================================
def _save_index_to_env(index_id: str):
    """دالة مساعدة لحفظ الـ ID في ملف .env بشكل دائم"""
    try:
        with open(".env", "a", encoding="utf-8") as f:
            f.write(f"\nTWELVE_LABS_INDEX_ID={index_id}\n")
    except Exception as e:
        print(f"⚠️ تعذر الكتابة على ملف .env: {e}")

def setup_twelvelabs_index_automatically():
    """دالة التهيئة الذكية: تعمل لمرة واحدة عند أول إقلاع للسيرفر"""
    load_dotenv() # التأكد من تحميل المتغيرات البيئية قبل الفحص
    TL_API_KEY = os.getenv("TWELVE_LABS_API_KEY")
    TL_INDEX_ID = os.getenv("TWELVE_LABS_INDEX_ID")

    if not TL_API_KEY:
        print("⚠️ [Twelve Labs]: مفتاح الـ API غير موجود في ملف .env")
        return

    client = TwelveLabs(api_key=TL_API_KEY)
    index_name = "dkm-hybrid-index"

    # 1. إذا كان الفهرس مسجلاً بالفعل في النظام، نتجاهل العملية
    if TL_INDEX_ID:
        print(f"✅ [Twelve Labs]: الفهرس موجود ومسجل مسبقاً ({TL_INDEX_ID})")
        return

    print("🔍 [Twelve Labs]: لم يتم العثور على فهرس مسجل، جاري الفحص السحابي...")
    try:
        # 2. البحث سحابياً
        existing_indexes = client.indexes.list()
        for idx in existing_indexes:
            current_name = getattr(idx, 'index_name', getattr(idx, 'name', ''))
            if current_name == index_name:
                print(f"✅ [Twelve Labs]: تم العثور على الفهرس الهجين سحابياً. جاري حفظه... ({idx.id})")
                _save_index_to_env(idx.id)
                os.environ["TWELVE_LABS_INDEX_ID"] = idx.id
                return

        # 3. الإنشاء الآلي للفهرس الجديد
        print("🚀 [Twelve Labs]: جاري إنشاء فهرس هجين يدعم (البحث) و (التحليل النصي) معاً...")
        new_index = client.indexes.create(
            index_name=index_name,
            models=[
                {"model_name": "marengo3.0", "model_options": ["visual", "audio"]}, # محرك البحث
                {"model_name": "pegasus1.5", "model_options": ["visual", "audio"]}  # محرك التحليل
            ]
        )
        print(f"🎉 [Twelve Labs]: تم إنشاء الفهرس الهجين بنجاح! ID: {new_index.id}")
        
        # حفظ المعرف الجديد تلقائياً في ملف الإعدادات
        _save_index_to_env(new_index.id)
        os.environ["TWELVE_LABS_INDEX_ID"] = new_index.id

    except Exception as e:
        print(f"❌ [Twelve Labs]: فشل إعداد الفهرس الآلي: {e}")

# ==========================================
# 2. إعداد الـ Lifespan للتحقق من قواعد البيانات عند التشغيل
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🔄 [النظام]: جاري التحقق من قواعد بيانات المناهج والجداول...")
    
    # بناء جداول قاعدة البيانات بأمان
    SQLModel.metadata.create_all(engine)
    print("✅ [النظام]: تم التحقق من جداول قاعدة البيانات بنجاح.")

    # استدعاء الإعداد الآلي لـ Twelve Labs هنا
    setup_twelvelabs_index_automatically()

    try:
        load_latest_vectorstore()
        print("✅ [النظام]: تم تهيئة النظام وجاهز لاستقبال الاستفسارات.")
    except Exception as e:
        print(f"⚠️ [النظام]: لم يتم تحميل أي منهج تلقائياً. النظام بانتظار رفع ملف. ({e})")
    
    yield
    
    # عمليات التنظيف عند إيقاف السيرفر
    print("🛑 [النظام]: تم إيقاف السيرفر.")

# ==========================================
# 3. إنشاء التطبيق وإعداد السيرفر
# ==========================================
app = FastAPI(
    title="DKM - Ibb University API",
    version="1.0",
    lifespan=lifespan
)

# ==========================================
# 4. إعداد المجلدات الثابتة (StaticFiles)
# ==========================================
# تأكد من وجود المجلدات المطلوبة قبل ربطها
os.makedirs("storage/clips", exist_ok=True)
os.makedirs("storage/images", exist_ok=True) # مجلد الصور الجديد

# السماح للواجهة الأمامية بقراءة الملفات من هذه المجلدات مباشرة
app.mount("/clips", StaticFiles(directory="storage/clips"), name="clips")
app.mount("/images", StaticFiles(directory="storage/images"), name="images")

# ==========================================
# 5. إعداد الـ CORS
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 6. ربط الراوترات (Routers)
# ==========================================
app.include_router(auth.router)
app.include_router(students.router)
app.include_router(documents.router)
app.include_router(ai_chat.router)

# ==========================================
# 7. المسار الرئيسي (Root)
# ==========================================
@app.get("/")
def root():
    return {
        "message": "مرحباً بكم في خادم منصة المعرفة الديناميكية (DKM) لجامعة إب"
    }