#ai agent
import asyncio
import os
import time
import base64
import io
import urllib.parse
import traceback
from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient, models
# Docling
from langchain_google_genai import ChatGoogleGenerativeAI
from qdrant_client.models import Prefetch, FusionQuery,Fusion
from qdrant_client.models import Prefetch
from qdrant_client.models import (
    VectorParams, 
    Distance, 
    PointStruct, 
    SparseVectorParams, 
    SparseIndexParams, 
    SparseVector, 
    PayloadSchemaType, 
    UpdateStatus,
    Filter,
    FieldCondition,
    MatchValue
)
import uuid
from fastembed import SparseTextEmbedding
from qdrant_client.models import VectorParams, Distance, PointStruct, SparseVectorParams, SparseIndexParams, SparseVector
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct, SparseVectorParams, SparseIndexParams
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.chunking import HierarchicalChunker
from PIL import Image
from sentence_transformers import CrossEncoder
from typing import TypedDict, Annotated
from langchain_experimental.text_splitter import SemanticChunker
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv
from sqlmodel import Session, select
from app.database import engine, VideoMapping
from twelvelabs import TwelveLabs
from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode, tools_condition

from langchain_groq import ChatGroq
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_unstructured import UnstructuredLoader
from langchain_chroma import Chroma
from langchain_experimental.tools import PythonREPLTool
from tqdm import tqdm

# ==========================================
# 1. إعداد البيئة والمفاتيح
# ==========================================
load_dotenv()

TL_API_KEY = os.getenv("TWELVE_LABS_API_KEY")
TL_INDEX_ID = os.getenv("TWELVE_LABS_INDEX_ID")
LOCAL_VIDEO_PATH = os.getenv("LOCAL_VIDEO_PATH")
COLLECTION_NAME = "qdrant_db1"
tl_client = None
if TL_API_KEY:
    tl_client = TwelveLabs(api_key=TL_API_KEY)
groq_key = os.getenv("GROQ_API_KEY")
if not groq_key or not groq_key.strip():
    raise ValueError("❌ [النظام]: مفتاح GROQ_API_KEY مفقود أو فارغ في ملف .env")
# --- نظام المفاتيح الدوارة (Key Rotation) ---
GOOGLE_KEYS = []
for i in range(1, 6):
    key = os.getenv(f"GOOGLE_API_KEY_{i}")
    if key:
        GOOGLE_KEYS.append(key)

if not GOOGLE_KEYS and os.getenv("GOOGLE_API_KEY"):
    GOOGLE_KEYS.append(os.getenv("GOOGLE_API_KEY"))

current_google_key_index = 0

def get_dynamic_embeddings():
    """جلب نموذج التضمين مع تدوير المفاتيح ديناميكياً لتجنب استنفاد الرصيد"""
    global current_google_key_index
    current_api_key = GOOGLE_KEYS[current_google_key_index] if GOOGLE_KEYS else os.getenv("GOOGLE_API_KEY")
    if current_api_key:
        os.environ["GOOGLE_API_KEY"] = current_api_key
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-2",
        google_api_key=current_api_key
    )
    
def clean_credentials(text: str) -> str:
    """تنظيف النصوص والمفاتيح من المسافات والرموز غير المرئية"""
    if not text:
        return ""
    return text.strip().encode('ascii', 'ignore').decode('ascii')    
from langchain_core.messages import HumanMessage

async def explain_image(image_bytes, user_prompt="اشرح ما في هذه الصورة بالتفصيل"):
    """دالة مخصصة لإرسال الصور إلى Gemini"""
    message = HumanMessage(
        content=[
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_bytes}"}}
        ]
    )
    
    # استخدام نموذج الرؤية فقط هنا
    response = await vision_llm.ainvoke([message])
    return response.content
# ==========================================
# 2. تهيئة النماذج الأساسية
# ==========================================
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.0, streaming=True)
embeddings = get_dynamic_embeddings()
global_vectorstore = None

COLLECTION_NAME = "qdrant_db1"
qdrant_client = None
sparse_embedding_model = SparseTextEmbedding(model_name="Qdrant/bm25")
# ========================================== #
print(" جاري تحميل النماذج قد يستغرق ثواني معدودة . . . ")
reranker = CrossEncoder('BAAI/bge-reranker-v2-m3', device='cuda')
sparse_embedding_model = SparseTextEmbedding(
    model_name="Qdrant/bm25", 
    providers=["CUDAExecutionProvider","CPUExecutionProvider"],
    api_key=os.environ.get("GROQ_API_KEY")
)
vision_llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.3,
    api_key=os.environ.get("GOOGLE_API_KEY")
)
print(f"🚀 Reranker is currently using: {reranker.model.device}")

# ==========================================
# 3. الأدوات (Tools)
# ==========================================
@tool
def generate_code_block(language: str, code: str, explanation: str) -> str:
    """أداة مخصصة لكتابة الأكواد البرمجية في بايثون، JS، HTML، CSS، أو C++ وتنسيقها للواجهة"""
    clean_code = code.strip()
    return (
        f"\n### شرح الكود:\n{explanation}\n\n"
        f'<div dir="ltr" style="text-align:left; direction: ltr;">\n'
        f'```{language}\n{clean_code}\n```\n'
        f'</div>\n'
    )
python_repl = PythonREPLTool()
tools = [python_repl, generate_code_block]
llm_with_tools = llm.bind_tools(tools)

# ==========================================
# 4. دالة معالجة المستندات واستخراج الصور (Ingestion)
# ==========================================
"""
def create_vector_db_with_unstructured(pdf_path: str, db_directory: str):
    global global_vectorstore
    print("\n[النظام]: بدء معالجة المستند واستخراج الصور سحابياً...")
    
    try:
        loader = UnstructuredLoader(
            file_path=pdf_path,
            api_key=os.getenv("UNSTRUCTURED_API_KEY"),
            partition_via_api=True,
            strategy="hi_res",
            extract_image_block_to_payload=True, 
            extract_image_block_types=["Image", "Table"],
        )
        raw_docs = loader.load()

        valid_docs = []
        images_found = 0
        pdf_filename = os.path.basename(pdf_path)
        safe_images_dir = "storage/images" 
        os.makedirs(safe_images_dir, exist_ok=True)
        
        # 1. قاموس لتخزين الصور حسب رقم الصفحة
        page_images = {}
        
        for i, doc in enumerate(raw_docs):
            if "image_base64" in doc.metadata and doc.metadata["image_base64"]:
                try:
                    img_data = base64.b64decode(doc.metadata["image_base64"])
                    image = Image.open(io.BytesIO(img_data))
                    if image.mode in ("RGBA", "P"): image = image.convert("RGB")
                    
                    img_filename = f"extracted_{pdf_filename}_img_{i}.jpg"
                    img_path = os.path.join(safe_images_dir, img_filename)
                    image.save(img_path, "JPEG", optimize=True, quality=70)
                    
                    images_found += 1
                    page_num = doc.metadata.get("page_number")
                    
                    if page_num:
                        page_images[page_num] = img_filename
                        
                except Exception as e:
                    print(f"⚠️ خطأ في معالجة الصورة: {e}")
                    
        # 2. خطوة "التدبيس": ربط الصورة بالنصوص
        for doc in raw_docs:
            has_text = bool(doc.page_content and doc.page_content.strip())
            page_num = doc.metadata.get("page_number")
            
            if page_num in page_images:
                doc.metadata["image_path"] = page_images[page_num]
                
            if has_text or ("image_path" in doc.metadata):
                if "image_base64" in doc.metadata:
                    del doc.metadata["image_base64"]
                valid_docs.append(doc)
                
        print(f"✅ تم استخراج {images_found} صورة. إجمالي المقاطع السليمة: {len(valid_docs)}.")

        # ==========================================
        # 3. التقطيع والدمج المحلي (Local Chunking)
        # ==========================================
        merged_docs = []
        current_content = ""
        current_metadata = {}

        for doc in valid_docs:
            text = doc.page_content.strip()
            if not text:
                continue
            
            if not current_metadata:
                current_metadata = doc.metadata.copy()

            if len(current_content) + len(text) > 1500:
                merged_docs.append(Document(page_content=current_content.strip(), metadata=current_metadata))
                overlap_text = current_content[-200:] if len(current_content) > 200 else current_content
                current_content = overlap_text + "\n" + text
                current_metadata = doc.metadata.copy()
            else:
                current_content += "\n" + text
                if "image_path" in doc.metadata:
                    current_metadata["image_path"] = doc.metadata["image_path"]

        if current_content:
            merged_docs.append(Document(page_content=current_content.strip(), metadata=current_metadata))
            
        print(f"✅ تم دمج النصوص محلياً. إجمالي المقاطع للمعالجة: {len(merged_docs)} مقطع متكامل.")

        # --- الحفظ في ChromaDB ---
        global current_google_key_index
        current_embeddings = get_dynamic_embeddings()
        vectorstore = Chroma(persist_directory=db_directory, embedding_function=current_embeddings)
        
        batch_size = 50
        success_count = 0
        
        for i in range(0, len(merged_docs), batch_size):
            batch = merged_docs[i:i+batch_size]
            if not batch: continue
            
            success = False
            while not success:
                try:
                    vectorstore.add_documents(batch)
                    success_count += len(batch)
                    print(f"تم حفظ الدفعة ({i+1} إلى {i+len(batch)}) بنجاح.")
                    success = True
                except Exception as e:
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        current_google_key_index += 1
                        if current_google_key_index < len(GOOGLE_KEYS):
                            print(f"⚠️ تم استنفاد الرصيد! التبديل للمفتاح رقم {current_google_key_index + 1}...")
                            current_embeddings = get_dynamic_embeddings()
                            vectorstore._embedding_function = current_embeddings
                            time.sleep(3)
                        else:
                            raise ValueError("❌ انتهى رصيد جميع مفاتيح جوجل!")
                    else:
                        print(f"⚠️ خطأ غير متوقع: {e}. جاري المحاولة الفردية...")
                        for doc in batch:
                            try:
                                vectorstore.add_documents([doc])
                                success_count += 1
                            except: pass
                        success = True
                        
            if i + batch_size < len(merged_docs): 
                time.sleep(2)

        global_vectorstore = vectorstore
        print(f"✅ الإجمالي: تم حفظ {success_count} مقطع في قاعدة البيانات.")
        return True

    except Exception as e:
        print(f"❌ [خطأ النظام]: حدثت مشكلة أثناء المعالجة! {e}")
        return False




"""


import os
import io
import time
import base64
from PIL import Image



def fix_arabic_text_smart(text: str) -> str:
    """فحص وإصلاح النصوص العربية المعكوسة الناتجة عن قراءة بعض ملفات PDF"""
    if not isinstance(text, str) or not text.strip():
        return text

    normal_words = {'هذا', 'إلى', 'عن', 'على', 'من', 'في', 'هي', 'هو', 'أن', 'الذي', 'التي'}
    reversed_words = {'اذه', 'ىلإ', 'نع', 'ىلع', 'نم', 'يف', 'يه', 'وه', 'نأ', 'يذلا', 'يتلا'}

    words = text.split()
    normal_count = sum(1 for w in words if w in normal_words)
    reversed_count = sum(1 for w in words if w in reversed_words)
    starts_with_al = sum(1 for w in words if w.startswith('ال'))
    ends_with_la = sum(1 for w in words if w.endswith('لا'))

    needs_fixing = (reversed_count > normal_count) or (ends_with_la > starts_with_al * 2)

    if needs_fixing:
        arabic_pattern = re.compile(r'[\u0600-\u06FF]+')
        return arabic_pattern.sub(lambda m: m.group(0)[::-1], text)
    return text

"""
def create_vector_db_with_docling(pdf_path: str, db_directory: str = None) -> bool:
    print(f" [النظام: بدء معالجة المستند عبر Docling: {os.path.basename(pdf_path)}]")
    safe_images_dir = "storage/images"
    os.makedirs(safe_images_dir, exist_ok=True)

    try:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.generate_picture_images = True
        pipeline_options.generate_table_images = True

        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        result = converter.convert(pdf_path)
        doc = result.document
        file_name = os.path.basename(pdf_path)

        chunker = HierarchicalChunker()
        docling_chunks = chunker.chunk(doc)
        valid_chunks = []
        sparse_embedding_model = SparseTextEmbedding(model_name="prithivida/Splade_PP_en_v1")
# أو النموذج الافتراضي:
# sparse_embedding_model = SparseTextEmbedding()
        for i, chunk in enumerate(tqdm(docling_chunks, desc="تجهيز المقاطع الهرمية")):
            text_content = chunk.text.strip()
            if not text_content:
                continue
            text_content = fix_arabic_text_smart(text_content)

            pages = set()
            chunk_images = []
            try:
                if hasattr(chunk.meta, 'doc_items'):
                    for item in chunk.meta.doc_items:
                        if hasattr(item, 'prov') and item.prov:
                            for p in item.prov:
                                if hasattr(p, 'page_no'):
                                    pages.add(p.page_no)

                        if hasattr(item, 'get_image'):
                            try:
                                img = item.get_image(doc)
                                if img:
                                    p_no = list(pages)[0] if pages else "1"
                                    img_name = f"docling_{file_name}_p{p_no}_c{i}.png"
                                    img_path = os.path.join(safe_images_dir, img_name)
                                    img.save(img_path, "PNG")
                                    chunk_images.append(img_name)
                            except Exception:
                                pass
            except Exception:
                pass

            section_title = chunk.meta.heading if hasattr(chunk.meta, 'heading') and chunk.meta.heading else text_content[:50].replace('\n', ' ')
            valid_chunks.append({
                "text": text_content,
                "images": chunk_images,
                "page": str(list(pages)[0]) if pages else "1",
                "section": section_title,
                "filename": file_name
            })

        q_url = clean_credentials(os.getenv("QDRANT_URL", "http://localhost:6333"))
        q_key = clean_credentials(os.getenv("QDRANT_API_KEY", ""))
        qdrant = QdrantClient(url=q_url, api_key=q_key if q_key else None)

        embeddings_model = get_dynamic_embeddings()
        test_vector = embeddings_model.embed_query("اختبار")

        collections = qdrant.get_collections().collections
        if not any(c.name == COLLECTION_NAME for c in collections):
            qdrant.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=len(test_vector), distance=Distance.COSINE),
                sparse_vectors_config={"text-sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))}
            )
            qdrant.create_payload_index(collection_name=COLLECTION_NAME, field_name="filename", field_schema=PayloadSchemaType.KEYWORD)

        points = []
        BATCH_SIZE = 10
        for i in range(0, len(valid_chunks), BATCH_SIZE):
            batch = valid_chunks[i:i+BATCH_SIZE]
            batch_texts = [str(c.get("text", "")) for c in batch]
                
            try:
                sparse_vecs = list(sparse_embedding_model.embed(batch_texts))
                dense_vecs = []
                    
                    # 1. إرسال المقاطع واحداً تلو الآخر مع احترام القيود المجانية لجوجل
                for t in batch_texts:
                    time.sleep(2) # ⏱️ تأخير ثانيتين بين كل طلب لتجنب القصف السريع للطلبات
                        
                    success = False
                    attempts = 0
                    while not success and attempts < 3:
                        try:
                            d_vec = embeddings_model.embed_query(t)
                            dense_vecs.append(d_vec)
                            success = True
                        except Exception as e:
                            err_msg = str(e).lower()
                                # استشعار خطأ تجاوز الرصيد أو الطلبات في الدقيقة
                            if "429" in err_msg or "quota" in err_msg or "exhausted" in err_msg:
                                print("⏳ [القيود المجانية]: تم تجاوز الحد. السيرفر سينتظر 45 ثانية للتعافي...")
                                time.sleep(45) # انتظار كافٍ بناءً على رسائل جوجل السابقة
                                attempts += 1
                            else:
                                print(f"⚠️ [خطأ في التضمين]: {e}")
                                break # خطأ آخر غير الرصيد، نخرج من محاولات الإعادة

                    # 2. التحقق الصارم من تطابق عدد المخرجات مع عدد المقاطع المرسلة
                if len(dense_vecs) != len(batch) or len(sparse_vecs) != len(batch):
                    print(f"⚠️ [تخطي دفعة]: السيرفر لم يرجع متجهات كاملة للدفعة ({i}). الكثيفة: {len(dense_vecs)} | المتناثرة: {len(sparse_vecs)}")
                    continue
                        
                    # 3. بناء النقاط ورفعها
                for j, chunk in enumerate(batch):
                    point_id = str(uuid.uuid4())
                    s_vec = sparse_vecs[j]
                    q_sparse = SparseVector(indices=s_vec.indices.tolist(), values=s_vec.values.tolist())
                        
                    points.append(PointStruct(
                        id=point_id,
                        vector={"": dense_vecs[j], "text-sparse": q_sparse},
                        payload=chunk
                        ))
                        
            except Exception as batch_err:
                print(f"⚠️ [خطأ في معالجة الدفعة]: {batch_err}. سيتم تجاوزها لمنع توقف السيرفر.")
                continue

            # الحفظ النهائي للنقاط المتجمعة
        if points:
            qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
            print(f"✅ [النظام]: تم رفع ({len(points)}) مقطع هجين إلى Qdrant بنجاح!")
    except Exception as e:
        print(f" [خطأ في معالجة Docling/Qdrant]: {e}")
        traceback.print_exc()
        return False

"""
"""
def create_vector_db_with_docling(pdf_path: str, db_directory: str = None) -> bool:
    global qdrant_client, current_google_key_index
    print(f"\n[النظام]: بدء معالجة المستند عبر Docling: [{os.path.basename(pdf_path)}]")
    
    safe_images_dir = "storage/images"
    os.makedirs(safe_images_dir, exist_ok=True)

    try:
        pipeline_options = PdfPipelineOptions()
        pipeline_options.generate_picture_images = True
        pipeline_options.generate_table_images = True

        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        result = converter.convert(pdf_path)
        doc = result.document
        file_name = os.path.basename(pdf_path)

        chunker = HierarchicalChunker()
        docling_chunks = chunker.chunk(doc)
        valid_chunks = []
        sparse_embedding_model = SparseTextEmbedding(model_name="Qdrant/bm25")

        for i, chunk in enumerate(tqdm(docling_chunks, desc="تجهيز المقاطع الهرمية")):
            text_content = chunk.text.strip()
            if not text_content:
                continue
            
            # إصلاح النصوص العربية إذا كان لديك هذه الدالة، وإلا يمكنك مسح هذا السطر
            if 'fix_arabic_text_smart' in globals():
                text_content = fix_arabic_text_smart(text_content)

            pages = set()
            chunk_images = []
            
            try:
                if hasattr(chunk.meta, 'doc_items'):
                    for item in chunk.meta.doc_items:
                        if hasattr(item, 'prov') and item.prov:
                            for p in item.prov:
                                if hasattr(p, 'page_no'):
                                    pages.add(p.page_no)

                        if hasattr(item, 'get_image'):
                            try:
                                img = item.get_image(doc)
                                if img:
                                    p_no = list(pages)[0] if pages else "1"
                                    img_name = f"docling_{file_name}_p{p_no}_c{i}.png"
                                    img_path = os.path.join(safe_images_dir, img_name)
                                    img.save(img_path, "PNG")
                                    chunk_images.append(img_name)
                            except Exception:
                                pass
            except Exception:
                pass

            section_title = chunk.meta.heading if hasattr(chunk.meta, 'heading') and chunk.meta.heading else text_content[:50].replace('\n', ' ')
            
            # نأخذ أول صورة فقط كمسار أساسي لتبسيط الاسترجاع في Qdrant
            primary_image = chunk_images[0] if chunk_images else ""
            
            valid_chunks.append({
                "text": text_content,
                "image_path": primary_image,
                "page": str(list(pages)[0]) if pages else "1",
                "section": section_title,
                "filename": file_name
            })

        # إعداد قاعدة البيانات
        q_url = clean_credentials(os.getenv("QDRANT_URL", ""))
        q_key = clean_credentials(os.getenv("QDRANT_API_KEY", ""))
        
        if qdrant_client is None:
            if q_url and q_key:
                qdrant_client = QdrantClient(url=q_url, api_key=q_key,timeout=180.0)
            else:
                db_directory = db_directory or os.path.join("vector_dbs", "qdrant_db")
                os.makedirs(db_directory, exist_ok=True)
                qdrant_client = QdrantClient(path=db_directory,timeout=180.0)

        embeddings_model = get_dynamic_embeddings()
        test_vector = embeddings_model.embed_query("اختبار")

        collections = qdrant_client.get_collections().collections
        if not any(c.name == COLLECTION_NAME for c in collections):
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(size=len(test_vector), distance=models.Distance.COSINE),
                sparse_vectors_config={"text-sparse": models.SparseVectorParams(index=models.SparseIndexParams(on_disk=False))}
            )
            qdrant_client.create_payload_index(collection_name=COLLECTION_NAME, field_name="filename", field_schema=PayloadSchemaType.KEYWORD)

        points = []
        total_upserted = 0
        BATCH_SIZE = 10
        
        for i in range(0, len(valid_chunks), BATCH_SIZE):
            batch = valid_chunks[i:i+BATCH_SIZE]
            batch_texts = [str(c.get("text", "")) for c in batch]
            
            # مصفوفة مؤقتة لهذه الدفعة فقط (10 مقاطع)
            points_batch = [] 
                
            try:
                sparse_vecs = list(sparse_embedding_model.embed(batch_texts))
                dense_vecs = []
                    
                for t in batch_texts:
                    time.sleep(2) 
                    success = False
                    attempts = 0
                    while not success and attempts < 3:
                        try:
                            d_vec = embeddings_model.embed_query(t)
                            dense_vecs.append(d_vec)
                            success = True
                        except Exception as e:
                            err_msg = str(e).lower()
                            if "429" in err_msg or "quota" in err_msg or "exhausted" in err_msg:
                                print("\n⏳ [القيود المجانية]: تم تجاوز الحد. السيرفر سينتظر 45 ثانية للتعافي...")
                                time.sleep(45)
                                attempts += 1
                                global current_google_key_index
                                if 'GOOGLE_KEYS' in globals() and current_google_key_index < len(GOOGLE_KEYS) - 1:
                                    current_google_key_index += 1
                                    embeddings_model = get_dynamic_embeddings()
                            else:
                                print(f"⚠️ [خطأ في التضمين]: {e}")
                                break 

                if len(dense_vecs) != len(batch) or len(sparse_vecs) != len(batch):
                    print(f"⚠️ [تخطي دفعة]: السيرفر لم يرجع متجهات كاملة للدفعة.")
                    continue
                        
                for j, chunk in enumerate(batch):
                    point_id = str(uuid.uuid4())
                    s_vec = sparse_vecs[j]
                    q_sparse = models.SparseVector(indices=s_vec.indices.tolist(), values=s_vec.values.tolist())
                        
                    points_batch.append(models.PointStruct(
                        id=point_id,
                        vector={"": dense_vecs[j], "text-sparse": q_sparse},
                        payload=chunk
                    ))
                
                # الرفع المرحلي للسحابة (لكل 10 مقاطع)
                if points_batch:
                    qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points_batch)
                    total_upserted += len(points_batch)
                    print(f"✅ جاري الرفع: تم حفظ {total_upserted} مقطع في السحابة...")
                        
            except Exception as batch_err:
                print(f"⚠️ [خطأ في معالجة الدفعة]: {batch_err}. سيتم تجاوزها.")
                continue

        # رسالة النجاح النهائية
        print(f"🎉 [النظام]: تمت العملية! تم رفع إجمالي ({total_upserted}) مقطع هجين إلى Qdrant بنجاح!")
        return True
            
    except Exception as e:
        print(f"❌ [خطأ في معالجة Docling/Qdrant]: {e}")
        import traceback
        traceback.print_exc()
        
    return False


"""
"""
import os
import uuid
import time
import json
import gc  # مكتبة تنظيف الذاكرة (Garbage Collection)
from tqdm import tqdm
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, SparseVectorParams, SparseIndexParams, PayloadSchemaType
from qdrant_client import models

import os
import uuid
import time
import json
import gc  # مكتبة تنظيف الذاكرة (Garbage Collection)
from tqdm import tqdm
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, SparseVectorParams, SparseIndexParams, PayloadSchemaType
from qdrant_client import models
# افترض أن المكتبات الخاصة بـ Docling تم استدعاؤها في أعلى الملف
# from docling.document_converter import DocumentConverter, PdfFormatOption
# from docling.datamodel.pipeline_options import PdfPipelineOptions
# from docling.datamodel.base_models import InputFormat
# from docling.chunking import HierarchicalChunker
# from fastembed import SparseTextEmbedding

def create_vector_db_with_docling(pdf_path: str, db_directory: str = None) -> bool:
    global qdrant_client, current_google_key_index
    print(f"\n[النظام]: بدء معالجة المستند عبر Docling: [{os.path.basename(pdf_path)}]")
    
    safe_images_dir = "storage/images"
    checkpoints_dir = "storage/checkpoints"
    os.makedirs(safe_images_dir, exist_ok=True)
    os.makedirs(checkpoints_dir, exist_ok=True) # مجلد لحفظ النسخ الاحتياطية

    try:
        # 1. إعدادات Docling واستخراج النصوص والصور
        pipeline_options = PdfPipelineOptions()
        pipeline_options.generate_picture_images = True
        pipeline_options.generate_table_images = True

        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        result = converter.convert(pdf_path)
        doc = result.document
        file_name = os.path.basename(pdf_path)

        chunker = HierarchicalChunker()
        docling_chunks = chunker.chunk(doc)
        valid_chunks = []
        
        # نماذج التضمين
        sparse_embedding_model = SparseTextEmbedding(model_name="Qdrant/bm25")

        for i, chunk in enumerate(tqdm(docling_chunks, desc="تجهيز المقاطع الهرمية")):
            text_content = chunk.text.strip()
            if not text_content:
                continue
            
            # إصلاح النصوص العربية
            if 'fix_arabic_text_smart' in globals():
                text_content = fix_arabic_text_smart(text_content)

            pages = set()
            chunk_images = []
            
            try:
                if hasattr(chunk.meta, 'doc_items'):
                    for item in chunk.meta.doc_items:
                        if hasattr(item, 'prov') and item.prov:
                            for p in item.prov:
                                if hasattr(p, 'page_no'):
                                    pages.add(p.page_no)

                        if hasattr(item, 'get_image'):
                            try:
                                img = item.get_image(doc)
                                if img:
                                    p_no = list(pages)[0] if pages else "1"
                                    img_name = f"docling_{file_name}_p{p_no}_c{i}.png"
                                    img_path = os.path.join(safe_images_dir, img_name)
                                    img.save(img_path, "PNG")
                                    chunk_images.append(img_name)
                            except Exception:
                                pass
            except Exception:
                pass

            section_title = chunk.meta.heading if hasattr(chunk.meta, 'heading') and chunk.meta.heading else text_content[:50].replace('\n', ' ')
            
            # === [التعديل هنا لمطابقة الكود المرجعي دون الإخلال بالمشروع] ===
            # تجميع كافة الصفحات بدلاً من الصفحة الأولى فقط
            page_info = ", ".join(map(str, sorted(list(pages)))) if pages else "غير متوفر"
            
            valid_chunks.append({
                "text": text_content,
                "images": chunk_images,  # إرجاع القائمة كاملة لتشمل الصور والجداول (بدلاً من image_path)
                "page": page_info,       # إدراج جميع أرقام الصفحات
                "section": section_title,
                "filename": file_name
            })
            # ===============================================================

        # --- [ميزة إضافية]: حفظ نسخة احتياطية (Checkpoint) قبل التضمين ---
        checkpoint_path = os.path.join(checkpoints_dir, f"{file_name}_backup.json")
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(valid_chunks, f, ensure_ascii=False, indent=4)
        print(f"💾 تم حفظ نسخة احتياطية من المقاطع في: {checkpoint_path}")

        # 2. إعداد قاعدة البيانات Qdrant
        q_url = clean_credentials(os.getenv("QDRANT_URL", ""))
        q_key = clean_credentials(os.getenv("QDRANT_API_KEY", ""))
        
        if qdrant_client is None:
            if q_url and q_key:
                qdrant_client = QdrantClient(url=q_url, api_key=q_key, timeout=180.0)
            else:
                db_directory = db_directory or os.path.join("vector_dbs", "qdrant_db")
                os.makedirs(db_directory, exist_ok=True)
                qdrant_client = QdrantClient(path=db_directory, timeout=180.0)

        embeddings_model = get_dynamic_embeddings()
        test_vector = embeddings_model.embed_query("اختبار")

        collections = qdrant_client.get_collections().collections
        if not any(c.name == COLLECTION_NAME for c in collections):
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(size=len(test_vector), distance=models.Distance.COSINE),
                sparse_vectors_config={"text-sparse": models.SparseVectorParams(index=models.SparseIndexParams(on_disk=False))}
            )
            qdrant_client.create_payload_index(collection_name=COLLECTION_NAME, field_name="filename", field_schema=PayloadSchemaType.KEYWORD)

        # 3. نظام الرفع المرحلي (Batch Upsert) وتفريغ الذاكرة
        total_upserted = 0
        BATCH_SIZE = 40 # تم التعديل إلى 40 مقطعاً
        
        print(f"\n🚀 بدء عملية التضمين والرفع السحابي (حجم الدفعة: {BATCH_SIZE} مقطع)...")

        for i in range(0, len(valid_chunks), BATCH_SIZE):
            batch = valid_chunks[i:i+BATCH_SIZE]
            batch_texts = [str(c.get("text", "")) for c in batch]
            
            # مصفوفة مؤقتة لهذه الدفعة فقط
            points_batch = [] 
                
            try:
                sparse_vecs = list(sparse_embedding_model.embed(batch_texts))
                dense_vecs = []
                    
                for t in batch_texts:
                    time.sleep(2) 
                    success = False
                    attempts = 0
                    while not success and attempts < 3:
                        try:
                            d_vec = embeddings_model.embed_query(t)
                            dense_vecs.append(d_vec)
                            success = True
                        except Exception as e:
                            err_msg = str(e).lower()
                            if "429" in err_msg or "quota" in err_msg or "exhausted" in err_msg:
                                print(f"\n⏳ [القيود المجانية]: الدفعة ({i//BATCH_SIZE + 1}). السيرفر سينتظر 45 ثانية للتعافي...")
                                time.sleep(45)
                                attempts += 1
                                global current_google_key_index
                                if 'GOOGLE_KEYS' in globals() and current_google_key_index < len(GOOGLE_KEYS) - 1:
                                    current_google_key_index += 1
                                    embeddings_model = get_dynamic_embeddings()
                                    print("🔄 تم التبديل لمفتاح API جديد.")
                            else:
                                print(f"⚠️ [خطأ في التضمين]: {e}")
                                break 

                if len(dense_vecs) != len(batch) or len(sparse_vecs) != len(batch):
                    print(f"⚠️ [تخطي دفعة]: السيرفر لم يرجع متجهات كاملة للدفعة الحالية.")
                    continue
                        
                for j, chunk in enumerate(batch):
                    point_id = str(uuid.uuid4())
                    s_vec = sparse_vecs[j]
                    q_sparse = models.SparseVector(indices=s_vec.indices.tolist(), values=s_vec.values.tolist())
                        
                    points_batch.append(models.PointStruct(
                        id=point_id,
                        vector={"": dense_vecs[j], "text-sparse": q_sparse},
                        payload=chunk
                    ))
                
                # الرفع المرحلي للسحابة
                if points_batch:
                    qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points_batch)
                    total_upserted += len(points_batch)
                    print(f"✅ تم رفع دفعة بنجاح! الإجمالي المرفوع حتى الآن: ({total_upserted}/{len(valid_chunks)}) مقطع.")
                
                # ==========================================
                # التفريغ الصريح للذاكرة (Memory Cleanup)
                # ==========================================
                points_batch.clear() # تفريغ القائمة
                del dense_vecs       # حذف المتجهات الكثيفة من الذاكرة
                del sparse_vecs      # حذف المتجهات المتناثرة
                gc.collect()         # إجبار بايثون على تنظيف الـ RAM فوراً
                    
            except Exception as batch_err:
                print(f"⚠️ [خطأ في معالجة الدفعة]: {batch_err}. سيتم تجاوزها واستكمال الباقي.")
                continue

        print(f"🎉 [النظام]: تمت العملية! تم رفع إجمالي ({total_upserted}) مقطع هجين إلى Qdrant بنجاح!")
        return True
            
    except Exception as e:
        print(f"❌ [خطأ عام في معالجة Docling/Qdrant]: {e}")
        import traceback
        traceback.print_exc()
        return False
"""  
    
import os
import uuid
import time
import json
import gc  # مكتبة تنظيف الذاكرة (Garbage Collection)
from tqdm import tqdm
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, SparseVectorParams, SparseIndexParams, PayloadSchemaType
from qdrant_client import models

def create_vector_db_with_docling(pdf_path: str, db_directory: str = None) -> bool:
    global qdrant_client, current_google_key_index
    print(f"\n[النظام]: بدء معالجة المستند عبر Docling: [{os.path.basename(pdf_path)}]")
    
    safe_images_dir = "storage/images"
    checkpoints_dir = "storage/checkpoints"
    os.makedirs(safe_images_dir, exist_ok=True)
    os.makedirs(checkpoints_dir, exist_ok=True) # مجلد لحفظ النسخ الاحتياطية

    try:
        # 1. إعدادات Docling واستخراج النصوص والصور
        pipeline_options = PdfPipelineOptions()
        pipeline_options.generate_picture_images = True
        pipeline_options.generate_table_images = True

        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        result = converter.convert(pdf_path)
        doc = result.document
        file_name = os.path.basename(pdf_path)

        chunker = HierarchicalChunker()
        docling_chunks = chunker.chunk(doc)
        valid_chunks = []
        
        # نماذج التضمين
        sparse_embedding_model = SparseTextEmbedding(model_name="Qdrant/bm25")

        for i, chunk in enumerate(tqdm(docling_chunks, desc="تجهيز المقاطع الهرمية")):
            text_content = chunk.text.strip()
            if not text_content:
                continue
            
            # إصلاح النصوص العربية
            if 'fix_arabic_text_smart' in globals():
                text_content = fix_arabic_text_smart(text_content)

            pages = set()
            chunk_images = []
            
            try:
                if hasattr(chunk.meta, 'doc_items'):
                    for item in chunk.meta.doc_items:
                        if hasattr(item, 'prov') and item.prov:
                            for p in item.prov:
                                if hasattr(p, 'page_no'):
                                    pages.add(p.page_no)

                        if hasattr(item, 'get_image'):
                            try:
                                img = item.get_image(doc)
                                if img:
                                    p_no = list(pages)[0] if pages else "1"
                                    img_name = f"docling_{file_name}_p{p_no}_c{i}.png"
                                    img_path = os.path.join(safe_images_dir, img_name)
                                    img.save(img_path, "PNG")
                                    chunk_images.append(img_name)
                            except Exception:
                                pass
            except Exception:
                pass

            section_title = chunk.meta.heading if hasattr(chunk.meta, 'heading') and chunk.meta.heading else text_content[:50].replace('\n', ' ')
            
            # === [التعديل هنا لمطابقة الكود المرجعي دون الإخلال بالمشروع] ===
            # تجميع كافة الصفحات بدلاً من الصفحة الأولى فقط
            page_info = ", ".join(map(str, sorted(list(pages)))) if pages else "غير متوفر"
            
            valid_chunks.append({
                "text": text_content,
                "images": chunk_images,  # إرجاع القائمة كاملة لتشمل الصور والجداول (بدلاً من image_path)
                "page": page_info,       # إدراج جميع أرقام الصفحات
                "section": section_title,
                "filename": file_name
            })
            # ===============================================================

        # --- [ميزة إضافية]: حفظ نسخة احتياطية (Checkpoint) قبل التضمين ---
        checkpoint_path = os.path.join(checkpoints_dir, f"{file_name}_backup.json")
        with open(checkpoint_path, "w", encoding="utf-8") as f:
            json.dump(valid_chunks, f, ensure_ascii=False, indent=4)
        print(f"💾 تم حفظ نسخة احتياطية من المقاطع في: {checkpoint_path}")

        # 2. إعداد قاعدة البيانات Qdrant
        q_url = clean_credentials(os.getenv("QDRANT_URL", ""))
        q_key = clean_credentials(os.getenv("QDRANT_API_KEY", ""))
        
        if qdrant_client is None:
            if q_url and q_key:
                qdrant_client = QdrantClient(url=q_url, api_key=q_key, timeout=300.0)
            else:
                db_directory = db_directory or os.path.join("vector_dbs", "qdrant_db")
                os.makedirs(db_directory, exist_ok=True)
                qdrant_client = QdrantClient(path=db_directory, timeout=300.0)

        embeddings_model = get_dynamic_embeddings()
        test_vector = embeddings_model.embed_query("اختبار")

        collections = qdrant_client.get_collections().collections
        if not any(c.name == COLLECTION_NAME for c in collections):
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(size=len(test_vector), distance=models.Distance.COSINE),
                sparse_vectors_config={"text-sparse": models.SparseVectorParams(index=models.SparseIndexParams(on_disk=False))}
            )
            qdrant_client.create_payload_index(collection_name=COLLECTION_NAME, field_name="filename", field_schema=PayloadSchemaType.KEYWORD)

        # 3. نظام الرفع المرحلي (Batch Upsert) وتفريغ الذاكرة
        total_upserted = 0
        BATCH_SIZE = 40 # تم التعديل إلى 40 مقطعاً
        
        print(f"\n🚀 بدء عملية التضمين والرفع السحابي (حجم الدفعة: {BATCH_SIZE} مقطع)...")

        for i in range(0, len(valid_chunks), BATCH_SIZE):
            batch = valid_chunks[i:i+BATCH_SIZE]
            batch_texts = [str(c.get("text", "")) for c in batch]
            
            # مصفوفة مؤقتة لهذه الدفعة فقط
            points_batch = [] 
                
            try:
                sparse_vecs = list(sparse_embedding_model.embed(batch_texts))
                dense_vecs = []
                    
                for t in batch_texts:
                    time.sleep(2) 
                    success = False
                    attempts = 0
                    while not success and attempts < 3:
                        try:
                            d_vec = embeddings_model.embed_query(t)
                            dense_vecs.append(d_vec)
                            success = True
                        except Exception as e:
                            err_msg = str(e).lower()
                            if "429" in err_msg or "quota" in err_msg or "exhausted" in err_msg:
                                print(f"\n⏳ [القيود المجانية]: الدفعة ({i//BATCH_SIZE + 1}). السيرفر سينتظر 45 ثانية للتعافي...")
                                time.sleep(45)
                                attempts += 1
                                global current_google_key_index
                                if 'GOOGLE_KEYS' in globals() and current_google_key_index < len(GOOGLE_KEYS) - 1:
                                    current_google_key_index += 1
                                    embeddings_model = get_dynamic_embeddings()
                                    print("🔄 تم التبديل لمفتاح API جديد.")
                            else:
                                print(f"⚠️ [خطأ في التضمين]: {e}")
                                break 

                if len(dense_vecs) != len(batch) or len(sparse_vecs) != len(batch):
                    print(f"⚠️ [تخطي دفعة]: السيرفر لم يرجع متجهات كاملة للدفعة الحالية.")
                    continue
                        
                for j, chunk in enumerate(batch):
                    point_id = str(uuid.uuid4())
                    s_vec = sparse_vecs[j]
                    q_sparse = models.SparseVector(indices=s_vec.indices.tolist(), values=s_vec.values.tolist())
                        
                    points_batch.append(models.PointStruct(
                        id=point_id,
                        vector={"": dense_vecs[j], "text-sparse": q_sparse},
                        payload=chunk
                    ))
                
                # =================================================================
                # الرفع المرحلي للسحابة مع آلية التعامل مع انقطاع الاتصال (Timeout)
                # =================================================================
                if points_batch:
                    max_retries = 3
                    upsert_success = False
                    
                    for attempt in range(max_retries):
                        try:
                            qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points_batch)
                            total_upserted += len(points_batch)
                            print(f"✅ تم رفع دفعة بنجاح! الإجمالي المرفوع حتى الآن: ({total_upserted}/{len(valid_chunks)}) مقطع.")
                            upsert_success = True
                            break # الخروج من حلقة المحاولات عند النجاح
                            
                        except Exception as upsert_err:
                            err_str = str(upsert_err).lower()
                            # التحقق الشامل من أي خطأ يتعلق بانقطاع الاتصال (Read/Write Timeout)
                            if any(kw in err_str for kw in ["time", "timeout", "read", "write", "connect", "network"]):
                                current_batch_num = (i // BATCH_SIZE) + 1
                                print(f"⚠️ [انقطاع الاتصال]: حدث خطأ (Timeout) في الدفعة رقم ({current_batch_num}).")
                                print(f"🔄 جاري إنشاء اتصال جديد بقاعدة البيانات وإعادة الإرسال ({attempt + 1}/{max_retries})...")
                                time.sleep(5) # الانتظار قليلاً قبل إعادة الاتصال
                                
                                # محاولة بناء اتصال جديد بـ Qdrant مع زيادة مهلة الانتظار إلى 300 ثانية
                                try:
                                    if q_url and q_key:
                                        qdrant_client = QdrantClient(url=q_url, api_key=q_key, timeout=300.0)
                                    else:
                                        db_dir = db_directory or os.path.join("vector_dbs", "qdrant_db")
                                        qdrant_client = QdrantClient(path=db_dir, timeout=300.0)
                                    print("✅ تم تجديد الاتصال بقاعدة البيانات بنجاح.")
                                except Exception as conn_err:
                                    print(f"❌ فشل تجديد الاتصال: {conn_err}")
                            else:
                                # إذا كان الخطأ من نوع آخر، ارفع الاستثناء ليتم التقاطه وتجاوزه
                                raise upsert_err
                                
                    # إذا استنفذ المحاولات الثلاث ولم ينجح
                    if not upsert_success:
                        raise Exception(f"تعذر رفع الدفعة ({(i//BATCH_SIZE) + 1}) نهائياً بعد استنفاد {max_retries} محاولات إعادة الاتصال.")
                
                # ==========================================
                # التفريغ الصريح للذاكرة (Memory Cleanup)
                # ==========================================
                points_batch.clear() # تفريغ القائمة
                del dense_vecs       # حذف المتجهات الكثيفة من الذاكرة
                del sparse_vecs      # حذف المتجهات المتناثرة
                gc.collect()         # إجبار بايثون على تنظيف الـ RAM فوراً
                    
            except Exception as batch_err:
                print(f"⚠️ [خطأ في معالجة الدفعة]: {batch_err}. سيتم تجاوزها واستكمال الباقي.")
                continue

        print(f"🎉 [النظام]: تمت العملية! تم رفع إجمالي ({total_upserted}) مقطع هجين إلى Qdrant بنجاح!")
        return True
            
    except Exception as e:
        print(f"❌ [خطأ عام في معالجة Docling/Qdrant]: {e}")
        import traceback
        traceback.print_exc()
        return False
# ==========================================
# 5. بناء الوكيل الذكي (LangGraph)
# ==========================================
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    question: str
    context: str
    answer: str
    retries: int
    search_mode: str
    
async def chat_node(state: AgentState, config: RunnableConfig):
    messages = state.get("messages", [])
    
    prompt = ChatPromptTemplate.from_messages([
        ("system",
        """أنت أستاذ أكاديمي خبير ومساعد برمجي لمنصة DKM.
        
        القواعد الأساسية للتعامل مع رسائل الطالب:
        1. 💬 الدردشة والتحية: إذا كان الطالب يلقي التحية أو يسأل سؤالاً عاماً لا يحتاج لكود، **يجب عليك الرد بنص عادي ومرحب** ولا تقم باستدعاء أي أداة إطلاقاً.
        2. 📝 لكتابة أو عرض كود برمجي: استدعِ أداة generate_code_block حصراً.
        3. 🚀 لتنفيذ أو اختبار كود بايثون: استدعِ أداة Python_REPL حصراً.
        
        تعليمات متقدمة (Function Calling): 
        - استخدم الأدوات (Tools) **فقط** إذا كان طلب الطالب يخص البرمجة صراحةً.
        - لا تقم بكتابة الكود في نص الرد العادي إطلاقاً، استخدم استدعاء الدوال دائماً.
        - إذا أعطاك الطالب كوداً غير منسق (في سطر واحد)، يجب عليك إعادة تنسيقه داخلياً بالمسافات البادئة الصحيحة قبل إرساله لأداة Python_REPL.
        """),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    response = await (prompt | llm_with_tools).ainvoke({"messages": messages}, config)
    return {"answer": response.content, "messages": [response]}




async def retrieve_node(state: AgentState) -> dict:
    """استرجاع متزامن للنصوص من Qdrant (مع Reranking) والفيديوهات من TwelveLabs"""
    question = state.get("question", "")
    search_mode = state.get("search_mode", "docs")
    formatted_texts = []

    async def search_docs_task():
            docs_texts = []
            if search_mode in ["docs", "both"] and qdrant_client is not None:
                print(f"\n[النظام]: بدء طلب البحث الهجين في المستندات (Qdrant)...")
                try:
                    current_embeddings = get_dynamic_embeddings()
                    query_dense = current_embeddings.embed_query(question)
                    query_sparse_gen = list(sparse_embedding_model.query_embed(question))[0]
                    query_sparse = models.SparseVector(
                        indices=query_sparse_gen.indices.tolist(),
                        values=query_sparse_gen.values.tolist()
                    )

                    search_response = await asyncio.to_thread(
                        qdrant_client.query_points,
                        collection_name=COLLECTION_NAME,
                        prefetch=[
                            models.Prefetch(query=query_dense, using="", limit=10),
                            models.Prefetch(query=query_sparse, using="text-sparse", limit=10)
                        ],
                        query=models.FusionQuery(fusion=models.Fusion.RRF),
                        limit=8
                    )

                    for hit in search_response.points:
                        payload = hit.payload
                        file_name = payload.get("filename", "مجهول")
                        page_num = payload.get("page", "?")
                        text_block = f"المستند: {file_name} | صفحة: {page_num}\n{payload.get('text', '')}"

                        # دعم المتغير القديم والجديد لضمان التوافق
                        img_path = payload.get("image_path")
                        if not img_path and payload.get("images"):
                            img_data = payload.get("images")
                            img_path = img_data[0] if isinstance(img_data, list) and len(img_data) > 0 else None

                        # ==========================================================
                        # التعديل الجذري: حماية التوكنز ومنع الانهيار (لا نرسل Base64 لـ Groq أبداً)
                        # ==========================================================
                        if img_path:
                            local_file_path = os.path.join("storage/images", img_path)
                            
                            if os.path.exists(local_file_path):
                                # 1. نرسل مسار مخفي فقط لـ Llama (يستهلك 15 توكن فقط بدلاً من 100 ألف)
                                img_placeholder = f'<div data-local-path="{local_file_path}" style="color:#10b981; font-weight:bold; margin-top:10px;">🖼️ [تم استرجاع صورة توضيحية سيتم عرضها وشرحها بالأسفل]</div>'
                                
                                # 2. إجبار Llama على طباعة هذا العنصر النائب فقط
                                text_block += f"\n\n[ أمر إجباري: اطبع هذا الكود كما هو تماماً في نهاية النقطة التي تشرحها لتحديد مكان الصورة:\n {img_placeholder} \n]\n"
                            else:
                                print(f"⚠️ [النظام]: الصورة غير موجودة فعلياً في المجلد المحلي: {local_file_path}")
                        # ==========================================================

                        docs_texts.append(text_block)

                    if docs_texts:
                        print(f"تم سحب ({len(docs_texts)}) مقاطع هجينة من المستندات.")
                    else:
                        print("لم يتم العثور على إجابة في المستندات.")

                except Exception as e:
                    print(f"خطأ استرجاع المستندات: {e}")
            return docs_texts
        
        
    async def search_videos_task():
        video_texts = []
        if search_mode in ["video", "both"] and TL_API_KEY and TL_INDEX_ID and tl_client:
            try:
                results = await asyncio.to_thread(
                    tl_client.search.query,
                    index_id=TL_INDEX_ID, query_text=question, search_options=["visual", "audio"]
                )
                for clip in list(results)[:2]:
                    analysis = await asyncio.to_thread(
                        tl_client.analyze,
                        video_id=clip.video_id,
                        prompt=f"هل يحتوي هذا المقطع على إجابة السؤال: {question}؟ أجب بنعم أو لا ثم قدم الشرح."
                    )
                    if "لا" in str(analysis.data).lower() or "no" in str(analysis.data).lower():
                        continue

                    start_time, end_time = round(clip.start, 2), round(clip.end, 2)
                    with Session(engine) as session:
                        record = session.exec(select(VideoMapping).where(VideoMapping.twelvelabs_asset_id == clip.video_id)).first()
                        mux_id = record.mux_playback_id if record else None

                    if mux_id:
                        btn = f'<a href="#" class="mux-jump-btn" data-playback-id="{mux_id}" data-start="{start_time}" data-end="{end_time}">شاهد الإجابة في الفيديو</a>'
                        video_texts.append(f"مصدر مرئي مؤكد:\n{analysis.data}\n{btn}")
            except Exception as e:
                print(f" [خطأ في استرجاع الفيديو]: {e}")
        return video_texts

    docs_res, videos_res = await asyncio.gather(search_docs_task(), search_videos_task())
    formatted_texts.extend(docs_res)
    formatted_texts.extend(videos_res)

    final_context = "\n---\n".join(formatted_texts) if formatted_texts else ""
    return {"context": final_context, "question": question}



async def generate_node(state: AgentState, config: RunnableConfig): 
    context = state.get("context", "").strip()
    search_mode = state.get("search_mode", "docs")
    
    print(f"\n\n[السياق المرسل للنموذج]:\n{context}\n\n")
    
    if not context or len(context) < 15 or "لا يوجد سياق متطابق" in context:
        safe_message = "عذراً، لم أتمكن من العثور على معلومات حول هذا الموضوع في المناهج أو الفيديوهات الخاصة بالمنصة. يرجى التأكد من أن سؤالك يخص المقررات الدراسية."
        return {"answer": safe_message, "messages": [AIMessage(content=safe_message)]}

    if "مصدر الفيديو:" in context and "الشرح المستخرج من الفيديو" not in context:
        safe_message = f"لقد وجدت لك الشرح المرئي المطلوب في المحاضرات. تفضل بمشاهدته:\n\n{context}"
        return {"answer": safe_message, "messages": [AIMessage(content=safe_message)]}

    if search_mode == "both":
        format_instructions = """
يجب عليك تحليل السياق المسترجع، وتقسيم إجابتك بشكل إجباري إلى قسمين واضحين:

**الإجابة من المستندات:**
(اكتب هنا الشرح المستخرج من النصوص التي تبدأ بكلمة [المستند: ...])
- 📚 التوثيق: يجب ذكر اسم المستند ورقم الصفحة بدقة.
- 🖼️ عرض الصور: **إياك أن تخترع أو تؤلف رابط صورة من عندك!** قم بطباعة كود HTML للصورة (<img>) **فقط وحصرياً** إذا كان مكتوباً حرفياً أمامك داخل السياق المسترجع. إذا لم تجد كود الصورة في السياق، لا تكتب هذا العنصر تماماً.

**الإجابة من الفيديو:**
(اكتب هنا الشرح المستخرج من النصوص التي تبدأ بكلمة [مصدر مرئي مؤكد])
- 🎥 التعامل مع الفيديو: يجب عليك إدراج جميع أزرار <a class="mux-jump-btn" ...> الموجودة في السياق كما هي كنص عادي، وضعها أسفل بعضها.

⚠️ ملاحظة هامة: إذا لم تجد معلومات لأحد القسمين في السياق، لا تكتب عنوانه من الأساس.
"""
    elif search_mode == "video":
        format_instructions = """
قم بصياغة الإجابة بناءً على المصادر المرئية فقط المسترجعة في السياق.
- 🎥 التعامل مع الفيديو: يجب عليك إدراج جميع أزرار <a class="mux-jump-btn" ...> الموجودة في السياق كما هي كنص عادي.
"""
    else: 
        format_instructions = """
قم بصياغة الإجابة بناءً على المستندات النصية المسترجعة في السياق.
- 📚 التوثيق: يجب ذكر اسم المستند ورقم الصفحة بدقة في نهاية كل معلومة.
-
قواعد صارمة لا تقبل التجاوز أبداً:
١. التجميع الشامل (مهم جداً): ابحث في كل النصوص المسترجعة واجمع كل الجوانب المتعلقة بالسؤال (مثل: التعريف، الخصائص، الاستخدام، الآلية، إلخ) وضعها في نقاط متعددة ومستقلة يفصل بينها خط. لا تكتفِ بنقطة واحدة إذا كان هناك المزيد من المعلومات.
٢. ثبات الصياغة: لا تقم بإعادة صياغة التعاريف من عندك. انقلها كما وردت في المستند لضمان تطابق الإجابة في كل مرة.
٣. حل المسائل الجديدة: إذا أعطاك مسألة بأرقام جديدة، استخرج القانون وحلها فعلياً خطوة بخطوة بالأرقام الجديدة.
٤. ترتيب الفقرات ودقة المصادر: التزم بالهيكلة المحددة أدناه حرفياً، مع وضع رقم الصفحة واسم الملف داخل الوسم <small>.

٥. قالب المسائل الرياضية (التزم بالهيكل والرموز):
📌 السؤال
═════════════════════
[نص السؤال]
════════════════════════════════════
✅ الإجابة المختصرة
════════════════════════
[ملخص الإجابة أو الجدول]
══════════════════════════════════
📝 خطوات الحل
════════════════════════
① [اسم الخطوة]
[القانون الرياضي والتعويض بالأرقام الجديدة]
──────────────────────────────────────
══════════════════════════════
📚 المراجع
═══════════════════════════════════
<small>• [اسم الملف] - صفحة: [رقم الصفحة]</small>

٦. قالب الأسئلة النظرية (التزم بالهيكل والرموز):
📌 السؤال
════════════════════════════════
[نص السؤال]
═════════════════════════════
📖 الإجابة
═════════════════════════════
🔹 **[عنوان النقطة الأولى مثلاً: التعريف]**
[  كتابة نص المقتبس من المستند بشكل مطابق للكلمات والمصطلحات]
<small>📚 **المصدر:** [اسم الملف] — الصفحة [رقم الصفحة]</small>
───────────────────────────
🔹 **[عنوان النقطة الثانية مثلاً: الاستخدام أو الخصائص]**
[  كتابة نص المقتبس من المستند بشكل مطابق للكلمات والمصطلحات]
<small>📚 **المصدر:** [اسم الملف] — الصفحة [رقم الصفحة]</small>
─────────────────────────────

- 🖼️ عرض الصور: **إياك أن تخترع أو تؤلف رابط صورة من عندك!** قم بطباعة كود HTML للصورة (<img>) **فقط وحصرياً** إذا كان مكتوباً حرفياً أمامك داخل السياق المسترجع.
"""

    system_prompt_text = f"""أنت مساعد ذكي مخصص لاستخراج المعلومات من المستندات المرفقة فقط لمنصة DKM.
يجب عليك الالتزام بالقواعد الحديدية التالية عند الإجابة:

1. **الالتزام الحرفي بالسياق (Zero-Hallucination):** استخرج الإجابة من النص المرفق فقط. يُمنع منعاً باتاً إضافة أي معلومات، استنتاجات، أمثلة، أو شروحات من معلوماتك العامة مهما كانت صحيحة.
2. **الرموز والمتغيرات:** استخدم نفس الرموز الرياضية والصيغ الرياضية والمتغيرات المذكورة في النص حرفياً (مثل r أو p أو غيرها). لا تقم بتعديلها أو تصحيحها بناءً على معرفتك.
3. **الدقة في التوثيق:** عندما تذكر معلومة، يجب أن ترفق معها رقم الصفحة الصحيح [صفحة: X] كما هو وارد في السياق المرفق أمامك. إياك أن تخمن رقم الصفحة.
4. **آلية الرفض:** إذا كان سؤال المستخدم يحتوي على استنتاج غير موجود صراحة في النص، أو يسأل عن معلومة غير متوفرة في السياق، يجب عليك أن تقول حرفياً: "عذراً، هذه المعلومة غير متوفرة بشكل صريح في المستندات المسترجعة."

قواعد صارمة جداً لا تقبل التجاوز:
١. تصنيف السؤال: إذا كان يحتوي على أرقام ويطلب حسابات، استخدم "قالب المسائل الرياضية". إذا كان يسأل عن تعريف أو شرح، استخدم "قالب الأسئلة النظرية".
٢. قالب المسائل الرياضية:
📌
٤. حل المسائل الجديدة (القياس): ابحث عن قانون أو مثال في المستندات، ثم قم بتطبيقه فعلياً على الأرقام الجديدة المعطاة في السؤال. إياك أن تنسخ الأرقام القديمة.
٥. عرض الصور والفيديوهات: قم بطباعة كود HTML للصورة (<img src="...">) أو زر الفيديو (<a class="mux-jump-btn" ...>) كما هو مكتوب حرفياً أمامك داخل السياق المسترجع ليتمكن الطالب من مشاهدته.
٦. يمنع منعا باتا حل تمرين أو مسائل رياضية لا يوجد مثلها في المستندات. إذا لم تجد الإجابة رد بـ: "عذراً، لم أتمكن من العثور على معلومات متطابقة في السياق المسترجع."

**آلية التفكير (Chain of Thought):**
قبل كتابة الإجابة النهائية، فكر داخلياً خطوة بخطوة: هل هذه الجملة أو المعادلة موجودة حرفياً في النص؟ إذا نعم، اكتبها. إذا لا، احذفها فوراً.

التعليمات الصارمة للاستجابة وتنسيق الإجابة:
{format_instructions}

تعليمات عامة للأمان (إجباري جداً):
1. 🚫 منع الهلوسة: التزم حرفياً بالمعلومات الموجودة في السياق. يُمنع منعاً باتاً الإجابة من معلوماتك العامة، ويُمنع تأليف نصوص أو اختراع روابط صور غير موجودة في السياق.
2. ⚠️ تنسيق الأكواد: يُمنع استخدام تنسيق الأكواد (```) عند طباعة الصور أو أزرار الفيديو. ضعها مباشرة في الرد لكي يتعرف عليها المتصفح.

السياق المسترجع:
{{context}}"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt_text),
        MessagesPlaceholder(variable_name="messages")
    ])
    
    response = await (prompt | llm).ainvoke({
        "messages": state.get("messages", []), 
        "context": context
    }, config)
    
    return {"answer": response.content, "messages": [response]}

def check_relevance(state: AgentState) -> str:
    return "generate"

def rewrite_node(state: AgentState):
    question = state.get("question", "")
    prompt = ChatPromptTemplate.from_template("أعد صياغة هذا السؤال للبحث:\n{question}\nالسؤال المعدل فقط:")
    try:
        better_question = (prompt | llm | StrOutputParser()).invoke({"question": question}).strip()
        return {"question": better_question or question, "retries": state.get("retries", 0) + 1}
    except:
        return {"question": question, "retries": state.get("retries", 0) + 1}
def route_question(state: AgentState) -> str:
    last_message = state.get("messages", [])[-1].content.strip()
    
    prompt = ChatPromptTemplate.from_template("""صنف رسالة الطالب إلى مسار واحد فقط بناءً على نيته:

إذا كان الطالب يطلب "تنفيذ كود"، "كتابة كود بايثون"، أو يدردش دردشة اجتماعية عامة (ترحيب، كيف حالك، مواضيع خارج الدراسة، تعارف) -> أجب بكلمة: chat

إذا كان الطالب يسأل عن معلومة في "المنهج"، مفهوم علمي نظري، "كتاب"، "فيديو"، "محاضرة"، أو أي طلب يستدعي البحث في المصادر -> أجب بكلمة: retrieve

رسالة الطالب: {text}
الإجابة (كلمة واحدة فقط):""")
    
    try:
        decision = (prompt | llm | StrOutputParser()).invoke({"text": last_message}).strip().lower()
        print(f"🔀 [شرطي المرور]: تم توجيه الرسالة إلى مسار: {decision}")
        return "retrieve" if "retrieve" in decision else "chat"
    except Exception as e:
        print(f"⚠️ خطأ في توجيه السؤال، التوجيه الافتراضي الآمن هو retrieve. الخطأ: {e}")
        return "retrieve"

# ==========================================
# 6. بناء الخريطة وتجميع الوكيل
# ==========================================
workflow = StateGraph(AgentState)
workflow.add_node("chat", chat_node)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("rewrite", rewrite_node)
workflow.add_node("generate", generate_node)
workflow.add_node("tools", ToolNode(tools))

workflow.add_conditional_edges(START, route_question)
workflow.add_conditional_edges("chat", tools_condition)
workflow.add_edge("tools", END) 
workflow.add_conditional_edges("retrieve", check_relevance)
workflow.add_edge("rewrite", "retrieve")
workflow.add_edge("generate", END)

dkm_agent = workflow.compile(checkpointer=MemorySaver())

# ==========================================
# 7. دوال تحميل قواعد البيانات والبث
# ==========================================

"""
def load_latest_vectorstore():
    global qdrant_client
    
    q_url = os.getenv("QDRANT_URL")
    q_key = os.getenv("QDRANT_API_KEY")
    
    try:
        if q_url and q_key:
            # الاتصال السحابي عبر API و URL
            qdrant_client = QdrantClient(url=q_url, api_key=q_key)
            print("[النظام]: تم الاتصال بقاعدة بيانات Qdrant السحابية (Cloud) بنجاح!")
        else:
            # الاتصال المحلي (Fallback)
            db_path = os.path.join("vector_dbs", "qdrant_db")
            os.makedirs(db_path, exist_ok=True)
            qdrant_client = QdrantClient(path=db_path)
            print("[النظام]: تم تهيئة قاعدة بيانات Qdrant المركزية محلياً بنجاح!")
    except Exception as e:
        print(f"[النظام]: فشل الاتصال بقاعدة بيانات Qdrant: {e}")



async def ask_dkm_agent(question: str, thread_id: str, search_mode: str = "docs"):
    config = {"configurable": {"thread_id": thread_id}}
    
    inputs = {
        "messages": [HumanMessage(content=question)],
        "question": question,
        "context": "",
        "answer": "",
        "retries": 0,
        "search_mode": search_mode 
    }
    
    print(f"\n💬 [بدء المحادثة] مع الطالب (Thread: {thread_id}). نمط البحث: {search_mode}")
    print("جاري توليد الرد...\n")
    
    has_output = False
    try:
        async for event in dkm_agent.astream_events(inputs, config, version="v2"):
            kind = event["event"]
            
            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = getattr(chunk, "content", None)
                tool_calls = getattr(chunk, "tool_call_chunks", None)
                
                if content:
                    has_output = True
                    print(content, end="", flush=True)
                    yield content
                elif tool_calls:
                    has_output = True
                    
            elif kind == "on_tool_start":
                has_output = True
                tool_name = event.get("name", "")
                
                if tool_name == "generate_code_block":
                    msg = "\n\n✍️ *[جاري كتابة وتنسيق الكود...]*\n\n"
                elif tool_name == "Python_REPL":
                    msg = "\n\n⚙️ *[جاري اختبار الكود في السيرفر...]*\n\n"
                else:
                    msg = "\n\n⚙️ *[جاري معالجة الأداة...]*\n\n"
                    
                print(msg, end="", flush=True)
                yield msg
                
            elif kind == "on_tool_end":
                tool_name = event.get("name", "")
                tool_output = event["data"].get("output", "")
                output_text = ""
                
                if hasattr(tool_output, "content"):
                    output_text = tool_output.content
                elif isinstance(tool_output, dict) and "messages" in tool_output:
                    output_text = tool_output["messages"][0].content
                else:
                    output_text = str(tool_output)
                    
                if tool_name == "generate_code_block":
                    msg = f"\n\n💡 **إليك هذا الكود جاهز:**\n{output_text}\n\n"
                elif tool_name == "Python_REPL":
                    msg = f"\n\n🖥️ **خرج الكود سيكون:**\n<div dir=\"ltr\" style=\"text-align: left; direction: ltr;\">\n```text\n{output_text}\n```\n</div>\n\n"
                else:
                    msg = f"\n\n💻 *[الخرج الحقيقي من السيرفر]:*\n<div dir=\"ltr\" style=\"text-align: left; direction: ltr;\">\n```text\n{output_text}\n```\n</div>\n\n"
                    
                print(msg, end="", flush=True)
                yield msg
                
        if not has_output:
            yield "عذراً، لم أتمكن من توليد إجابة. يرجى المحاولة بصيغة أخرى."
            
        print("\n\n✅ [انتهاء المحادثة] تم إرسال الرد بالكامل.")
        
    except Exception as e:
        print(f"\n❌ [خطأ داخلي أثناء توليد الرد]: {e}")
        import traceback
        traceback.print_exc()
        yield "عذراً، حدث خطأ في النظام. يرجى مراجعة نافذة السيرفر."
     

    
"""
def load_latest_vectorstore():
    global qdrant_client
    q_url = os.getenv("QDRANT_URL")
    q_key = os.getenv("QDRANT_API_KEY")
    
    try:
        if q_url and q_key:
            # الاتصال السحابي عبر API و URL مع زيادة مهلة الانتظار لمنع انقطاع البحث الهجين
            qdrant_client = QdrantClient(url=q_url, api_key=q_key, timeout=120.0)
            print("[النظام]: تم الاتصال بقاعدة بيانات Qdrant السحابية (Cloud) بنجاح")
        else:
            # الاتصال المحلي (Fallback) مع زيادة مهلة الانتظار
            db_path = os.path.join("vector_dbs", "qdrant_db")
            os.makedirs(db_path, exist_ok=True)
            qdrant_client = QdrantClient(path=db_path, timeout=120.0)
            print("[النظام]: تم تهيئة قاعدة بيانات Qdrant المركزية محلياً بنجاح!")
            
    except Exception as e:
        print(f"[النظام]: فشل الاتصال بقاعدة بيانات Qdrant: {e}")
import re
import os
import re
from langchain_core.messages import HumanMessage

import os
import re
from langchain_core.messages import HumanMessage

async def ask_dkm_agent(question: str, thread_id: str, search_mode: str = "docs"):
    config = {"configurable": {"thread_id": thread_id}}
    
    inputs = {
        "messages": [HumanMessage(content=question)],
        "question": question,
        "context": "",
        "answer": "",
        "retries": 0,
        "search_mode": search_mode 
    }
    
    print(f"\n💬 [بدء المحادثة] مع الطالب (Thread: {thread_id}). نمط البحث: {search_mode}")
    print("جاري توليد الرد...\n")
    
    has_output = False
    
    # ==========================================================
    # 🛡️ الإضافة الهندسية (الشبكة الشاملة المضادة للأخطاء):
    # متغير نصي عملاق سنرمي فيه أي شيء يمر في النظام بصيغة آمنة str()
    # (سواء إجابة Llama، أو مخرجات الأدوات، أو البيانات المسترجعة)
    # لضمان عدم إفلات مسار الصورة أبداً وتجنب أي خطأ برمجي (TypeError).
    # ==========================================================
    all_scanned_text = ""  
    
    try:
        async for event in dkm_agent.astream_events(inputs, config, version="v2"):
            kind = event["event"]
            
            # التقاط مخرجات أي عقدة (Node/Chain) في LangGraph وإضافتها للشبكة بأمان
            if kind in ["on_chain_end", "on_node_end"]:
                node_output = event.get("data", {}).get("output", "")
                all_scanned_text += str(node_output)

            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = getattr(chunk, "content", None)
                tool_calls = getattr(chunk, "tool_call_chunks", None)
                
                if content:
                    has_output = True
                    all_scanned_text += content  # التقاط ما يطبعه النموذج
                    print(content, end="", flush=True)
                    yield content
                elif tool_calls:
                    has_output = True
                    
            elif kind == "on_tool_start":
                has_output = True
                tool_name = event.get("name", "")
                
                if tool_name == "generate_code_block":
                    msg = "\n\n✍️ *[جاري كتابة وتنسيق الكود...]*\n\n"
                elif tool_name == "Python_REPL":
                    msg = "\n\n⚙️ *[جاري اختبار الكود في السيرفر...]*\n\n"
                else:
                    msg = "\n\n⚙️ *[جاري معالجة الأداة...]*\n\n"
                    
                print(msg, end="", flush=True)
                yield msg
                
            elif kind == "on_tool_end":
                tool_name = event.get("name", "")
                tool_output = event["data"].get("output", "")
                output_text = ""
                
                if hasattr(tool_output, "content"):
                    output_text = tool_output.content
                elif isinstance(tool_output, dict) and "messages" in tool_output:
                    output_text = tool_output["messages"][0].content
                else:
                    output_text = str(tool_output)
                    
                all_scanned_text += str(output_text)  # التقاط مخرجات الأدوات بالكامل
                
                if tool_name == "generate_code_block":
                    msg = f"\n\n💡 **إليك هذا الكود جاهز:**\n{output_text}\n\n"
                elif tool_name == "Python_REPL":
                    msg = f"\n\n🖥️ **خرج الكود سيكون:**\n<div dir=\"ltr\" style=\"text-align: left; direction: ltr;\">\n```text\n{output_text}\n```\n</div>\n\n"
                else:
                    msg = f"\n\n💻 *[الخرج الحقيقي من السيرفر]:*\n<div dir=\"ltr\" style=\"text-align: left; direction: ltr;\">\n```text\n{output_text}\n```\n</div>\n\n"
                    
                print(msg, end="", flush=True)
                yield msg
                
        if not has_output:
            yield "عذراً، لم أتمكن من توليد إجابة. يرجى المحاولة بصيغة أخرى."
            return

        # ==========================================================
        # العرض الإجباري: البحث في (الشبكة الشاملة) التي ضمنا أنها تحتوي على كل المسارات
        # ==========================================================
        image_paths = re.findall(r'data-local-path="([^"]+)"', all_scanned_text)
        unique_image_paths = list(set(image_paths))

        if unique_image_paths:
            yield "\n\n<div dir='rtl' style='background:#1e293b; padding:12px; border-radius:8px; margin-top:10px; border-right: 4px solid #10b981; color:#10b981; font-weight:bold;'>💡 جاري جلب الصورة وتحليلها إحصائياً...</div>\n"
            
            for path in unique_image_paths:
                if os.path.exists(path):
                    try:
                        import base64
                        with open(path, "rb") as image_file:
                            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                        
                        # بث الصورة كـ Base64 فوراً للواجهة ليراها الطالب
                        img_html = f"\n\n<img src='data:image/png;base64,{encoded_string}' style='max-width: 100%; border-radius: 8px; margin-top: 15px; border: 2px solid #334155;'>\n"
                        yield img_html
                        
                        # إرسال الصورة لـ Gemini للتحليل
                        vision_prompt = "أنت خبير أكاديمي وإحصائي. اشرح هذه الصورة أو الجدول بالتفصيل وبشكل دقيق وبسيط مختصر باللغة العربية. استخرج الأرقام أو المعاني المهمة والمصطلحات."
                        explanation_text = await explain_image(encoded_string, vision_prompt)
                        
                        if explanation_text:
                            # بث شرح جيميناي
                            explanation_html = f"<div dir='rtl' style='background:#334155; padding:12px; border-radius:8px; margin-top:5px; border-right: 4px solid #3b82f6;'><strong style='color:#3b82f6;'>🧠 شرح الذكاء الاصطناعي (Gemini):</strong><br><span style='color:#e2e8f0; font-size:14px; line-height: 1.6;'>{explanation_text}</span></div>\n\n"
                            yield explanation_html
                    except Exception as e:
                        print(f"⚠️ تعذر عرض أو تحليل الصورة في نهاية البث: {e}")
        # ==========================================================
            
        print("\n\n✅ [انتهاء المحادثة] تم إرسال الرد بالكامل.")
        
    except Exception as e:
        print(f"\n❌ [خطأ داخلي أثناء توليد الرد]: {e}")
        import traceback
        traceback.print_exc()
        yield "عذراً، حدث خطأ في النظام. يرجى مراجعة نافذة السيرفر."