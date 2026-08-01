#upload_video.py


import os
import time
import shutil
import requests
from fastapi import APIRouter, UploadFile, BackgroundTasks, HTTPException, Depends
from twelvelabs import TwelveLabs
from dotenv import load_dotenv

# تحميل المتغيرات البيئية
load_dotenv()

TL_API_KEY = os.getenv("TWELVE_LABS_API_KEY")
TL_INDEX_ID = os.getenv("TWELVE_LABS_INDEX_ID")
MUX_TOKEN_ID = os.getenv("MUX_TOKEN_ID")
MUX_TOKEN_SECRET = os.getenv("MUX_TOKEN_SECRET")

# تهيئة العميل
client = TwelveLabs(api_key=TL_API_KEY)

router = APIRouter(prefix="/video", tags=["محرك الفيديو الهجين"])

# قاموس ديناميكي لربط الفيديوهات (سيتم تعبئته تلقائياً)
# ملاحظة: في النسخة المستقبلية للمشروع، يُفضل حفظ هذه البيانات في جدول داخل قاعدة البيانات.
VIDEO_MAPPING = {}








def upload_to_mux(file_path: str):
    """النسخة المحصنة لرفع الفيديو إلى Mux بذكاء وحماية من التعليق اللانهائي"""
    print("[Mux]: جاري طلب رابط الرفع من المنصة...")
    auth = (MUX_TOKEN_ID, MUX_TOKEN_SECRET)

    headers = {"Content-Type": "application/json"}
    data = {
        "new_asset_settings": {"playback_policy": ["public"]},
        "cors_origin": "*"
    }
    
    try:
        res = requests.post("https://api.mux.com/video/v1/uploads", json=data, auth=auth)
        res.raise_for_status()
        upload_data = res.json()["data"]
        upload_url = upload_data["url"]
        upload_id = upload_data["id"]

        print(f"[Mux]: جاري ضخ الفيديو إلى السحابة ({os.path.basename(file_path)})...")
        
        # التعديل الأهم: إرسال نوع الملف (Content-Type) ليفهمه Mux فوراً
        with open(file_path, "rb") as f:
            put_res = requests.put(upload_url, data=f, headers={"Content-Type": "video/mp4"})
            put_res.raise_for_status()

        print("[Mux]: جاري المعالجة... (ستظهر الحالة أدناه)")
        asset_id = None
        attempts = 0
        max_attempts = 60 # حماية: الحد الأقصى للانتظار هو 3 دقائق
        
        while attempts < max_attempts:
            time.sleep(3)
            attempts += 1
            
            check_res = requests.get(f"https://api.mux.com/video/v1/uploads/{upload_id}", auth=auth)
            status_data = check_res.json()["data"]
            current_status = status_data["status"]
            
            print(f"[Mux Status]: {current_status}")
            
            if current_status == "asset_created":
                asset_id = status_data["asset_id"]
                break
            elif current_status == "errored":
                print("[Mux Error]: حدث خطأ في خوادم Mux أثناء التحويل.")
                return None
        
        if not asset_id:
            print("[Mux Error]: انتهى وقت الانتظار ولم ينتهِ Mux من المعالجة.")
            return None

        # جلب Playback ID النهائي
        asset_res = requests.get(f"https://api.mux.com/video/v1/assets/{asset_id}", auth=auth)
        playback_id = asset_res.json()["data"]["playback_ids"][0]["id"]
        
        print(f"[Mux]: تم الرفع بنجاح! 🚀 Playback ID: {playback_id}")
        return playback_id

    except Exception as e:
        print(f"[Mux Error]: فشل الاتصال بمنصة Mux - {e}")
        return None


def process_video_in_background(file_path: str):
    """إدارة عمليات الرفع المتوازي والربط الذكي في الخلفية للمشروع الأساسي"""
    try:
        # --- الخطوة 1: استدعاء دالة Mux المحصنة ---
        print(f"⏳ [النظام]: بدء خط المعالجة للفيديو ({os.path.basename(file_path)})...")
        mux_playback_id = upload_to_mux(file_path)
        
        if not mux_playback_id:
            print("[نظام الرفع]: ❌ توقفت العملية لفشل الرفع إلى Mux.")
            return # إذا فشل Mux، نوقف العملية ولا نكمل لـ Twelve Labs

        # --- الخطوة 2: الرفع لمنصة Twelve Labs (للذكاء الاصطناعي) ---
        print(f"⏳ [النظام]: جاري رفع الفيديو إلى سحابة Twelve Labs...")
        with open(file_path, "rb") as video_stream:
            task = client.tasks.create(
                index_id=TL_INDEX_ID,
                video_file=video_stream
            )
        
        print(f"✅ [النظام]: تم استلام الفيديو سحابياً بنجاح. (Task ID: {task.id})")
        print("🚀 [النظام]: المعالجة مستمرة الآن في سحابة Twelve Labs. سيرفر المنصة حُر وجاهز لخدمة الطلاب!")

        # انتظار Twelve Labs حتى تنهي الفهرسة
        def on_task_update(task_obj):
            print(f"[Twelve Labs Status]: {task_obj.status}")

        client.tasks.wait_for_done(task_id=task.id, callback=on_task_update)

        # --- الخطوة 3: الدمج الديناميكي (السحر الهندسي) ---
        completed_task = client.tasks.retrieve(task.id)
        tl_video_id = completed_task.video_id
        
        # ربط المُعرّفين وحفظهما في الذاكرة
        if tl_video_id and mux_playback_id:
            VIDEO_MAPPING[tl_video_id] = mux_playback_id
            print("\n=======================================================")
            print(f"[الربط الذكي السحري بنجاح]:")
            print(f"معرف Twelve Labs البصري: {tl_video_id}")
            print(f"معرف Mux الخاص بالبث: {mux_playback_id}")
            print("=======================================================\n")

    except Exception as e:
        print(f"[النظام]: خطأ غير متوقع أثناء خط المعالجة: {e}")
        
        
        
@router.post("/upload-video/")

async def upload_video_endpoint(file: UploadFile, background_tasks: BackgroundTasks):
    """مسار استقبال الفيديو من واجهة SPA"""
    if not file.filename.endswith((".mp4", ".mov", ".mkv")):
        raise HTTPException(status_code=400, detail="يسمح فقط برفع ملفات الفيديو")
    
    os.makedirs("storage/videos", exist_ok=True)
    file_path = os.path.join("storage/videos", file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    background_tasks.add_task(process_video_in_background, file_path)
    
    return {"message": f"تم استلام الفيديو {file.filename} بنجاح. جاري فهرسته ورفعه لـ Mux في الخلفية."}




# ==========================================
# دالة الاسترجاع ليستخدمها LangGraph (Retrieve Node)
# ==========================================
def search_video_twelve_labs(query: str):
    try:
        search_results = client.search.query(
            index_id=TL_INDEX_ID,
            query_text=query,
            search_options=["visual", "audio"]
        )
        
        clips = list(search_results)
        results = []
        
        for clip in clips[:2]:
            start_time = round(clip.start)
            end_time = round(clip.end)
            start_fmt = time.strftime('%M:%S', time.gmtime(start_time))
            end_fmt = time.strftime('%M:%S', time.gmtime(end_time))
            
            tl_video_id = clip.video_id
            
            # سحب Playback ID الخاص بـ Mux بناءً على نتيجة Twelve Labs
            mux_id = VIDEO_MAPPING.get(tl_video_id)
            
            # خط دفاع احتياطي: في حال لم يُعثر على المعرف
            if not mux_id:
                mux_id = os.getenv("MUX_PLAYBACK_ID", "")
            
            button_html = f'<a href="#" class="mux-jump-btn" data-playback-id="{mux_id}" data-start="{start_time}" data-end="{end_time}">شاهد الشرح المرئي ({start_fmt} - {end_fmt})</a>'
            
            results.append({
                "start": start_time,
                "end": end_time,
                "html_button": button_html
            })
            
        return results
    except Exception as e:
        print(f"[Twelve Labs Error]: {e}")
        return []