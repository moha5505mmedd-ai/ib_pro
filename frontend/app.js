// app.js - الواجهة الأمامية لتطبيق IBB

//const BASE_URL = "http://127.0.0.1:8000";
// استبدل المنفذ القديم 8000 بالمنفذ الجديد 8001
const BASE_URL = "http://127.0.0.1:8888";
//const BASE_URL = "https://fristproject-production.up.railway.app";
// العناصر
const navbar = document.getElementById("navbar");
const sections = {
    auth: document.getElementById("auth-section"),
    home: document.getElementById("home-section"),
    upload: document.getElementById("upload-section"),
    query: document.getElementById("query-section"),
    chat: document.getElementById("chat-section")
};

// ==========================================
// 1. نظام التنقل بين الصفحات (SPA Routing)
// ==========================================
function navigate(targetPage) {
    Object.values(sections).forEach(sec => sec.classList.add("hidden"));
    sections[targetPage].classList.remove("hidden");
}

window.onload = () => {
    const token = localStorage.getItem("token");
    if (token) {
        navbar.classList.remove("hidden");
        navigate('home');
    } else {
        navbar.classList.add("hidden");
        navigate('auth');
    }
};

function logout() {
    localStorage.removeItem("token");
    navbar.classList.add("hidden");
    navigate('auth');
}

// ==========================================
// 2. إدارة تسجيل الدخول والإنشاء
// ==========================================
document.getElementById("register-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("register-id").value;
    const name = document.getElementById("register-name").value;
    const pwd = document.getElementById("register-password").value;
    const msg = document.getElementById("auth-message");

    try {
        const res = await fetch(`${BASE_URL}/students/register/?university_id=${id}&full_name=${name}&password=${pwd}`, { method: "POST" });
        if (res.ok) { msg.innerText = "تم إنشاء الحساب ✅"; e.target.reset(); }
        else { const data = await res.json(); msg.innerText = data.detail || "فشل الإنشاء"; }
    } catch { msg.innerText = "تعذر الاتصال بالسيرفر"; }
});

document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("login-id").value;
    const pwd = document.getElementById("login-password").value;
    const msg = document.getElementById("auth-message");

    const formData = new URLSearchParams();
    formData.append("username", id);
    formData.append("password", pwd);

    try {
        const res = await fetch(`${BASE_URL}/token`, {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData
        });
        if (res.ok) {
            const data = await res.json();
            localStorage.setItem("token", data.access_token);
            navbar.classList.remove("hidden");
            navigate('home');
        } else { msg.innerText = "بيانات الدخول خاطئة"; }
    } catch { msg.innerText = "فشل الاتصال"; }
});

// ==========================================
// 3. رفع المناهج (PDF)
// ==========================================
document.getElementById("upload-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = document.getElementById("pdf-file").files[0];
    const msg = document.getElementById("upload-message");
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    msg.innerText = "جاري الرفع والمعالجة...";

    try {
        const res = await fetch(`${BASE_URL}/documents/upload/`, {
            method: "POST",
            headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
            body: formData
        });
        if (res.ok) { msg.innerText = "تمت المعالجة بنجاح ✅"; e.target.reset(); }
        else { msg.innerText = "فشل الرفع"; }
    } catch { msg.innerText = "تعذر الاتصال بالسيرفر"; }
});
// ==========================================
// رفع المحاضرات المرئية (فيديو)
// ==========================================
document.getElementById("upload-video-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    
    const file = document.getElementById("video-file").files[0];
    const msg = document.getElementById("upload-video-message");
    
    if (!file) return;
    
    const formData = new FormData();
    formData.append("file", file);
    
    // إظهار رسالة تفاعلية 
    msg.innerText = "⏳ جاري الرفع للسيرفر، يرجى الانتظار (قد يستغرق وقتاً حسب حجم الفيديو)...";
    msg.style.color = "#fbbf24"; 
    
    try {
        const res = await fetch(`${BASE_URL}/documents/upload-video/`, {
            method: "POST",
            headers: { 
                "Authorization": `Bearer ${localStorage.getItem("token")}`
            },
            body: formData
        });
        
        if (res.ok) {
            const data = await res.json();
            msg.innerText = "✅ " + data.message;
            msg.style.color = "#10b981";
            e.target.reset();
        } else {
            const errorData = await res.json();
            msg.innerText = "❌ فشل الرفع: " + (errorData.detail || "خطأ غير معروف");
            msg.style.color = "#ef4444";
        }
    } catch (error) {
        msg.innerText = "❌ تعذر الاتصال بالسيرفر.";
        msg.style.color = "#ef4444";
    }
});

// ==========================================
// 4. غرفة المحادثة (النسخة الاحترافية لـ SPA Hybrid RAG)
// ==========================================
const chatInput = document.getElementById("chat-input");
const chatBox = document.getElementById("chat-box");
const loading = document.getElementById("loading");

// عناصر مشغل الفيديو المدمج الجديد
const videoViewer = document.getElementById("embedded-video-viewer");
const spaPlayer = document.getElementById("main-spa-player");
const clipTitleDisplay = document.getElementById("current-clip-title");
const clipTimeDisplay = document.getElementById("current-clip-time");

document.getElementById("send-btn").addEventListener("click", sendMessage);
chatInput.addEventListener("keydown", (e) => { 
    // إذا ضغط على Enter بدون زر Shift
    if (e.key === "Enter" && !e.shiftKey) { 
        e.preventDefault(); // نمنع المتصفح من النزول لسطر جديد
        sendMessage();      // نرسل الرسالة
    }
    // أما إذا ضغط Shift + Enter، سيقوم المتصفح طبيعياً بالنزول لسطر جديد داخل الـ textarea
});
chatInput.addEventListener("input", function() {
    this.style.height = '45px'; // الارتفاع الأساسي الجديد
    this.style.height = (this.scrollHeight) + 'px'; // يتمدد حسب النص
});
async function sendMessage() {
    const question = chatInput.value.trim();
    const searchMode = document.getElementById("search-mode").value; 
    
    if (!question) return;

    addMessage(question, "user-message");
    
    chatInput.value = ""; 
    chatInput.style.height = '45px'; 
    
    // 1. إظهار تأثير Thinking...
    loading.classList.remove("hidden");

    try {
        const res = await fetch(`${BASE_URL}/chat/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${localStorage.getItem("token")}`
            },
            body: JSON.stringify({ 
                question: question,
                search_mode: searchMode 
            })
        });

        // 2. السيرفر بدأ بالرد، نخفي تأثير Thinking...
        loading.classList.add("hidden");

        if (!res.ok) {
            addMessage("حدث خطأ في السيرفر", "ai-message");
            return;
        }

        const aiMessageSpan = createEmptyAiMessage();
        
        // مسح أي نص افتراضي قد يكون موجوداً (مثل رسالة الاعتذار)
        aiMessageSpan.innerHTML = ""; 

        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let fullResponseText = ""; 

        while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
                // إذا انتهى الرد وكان فارغاً تماماً (بسبب انقطاع النت أو السيرفر)
                if (fullResponseText.trim() === "") {
                    aiMessageSpan.innerHTML = "عذراً، استغرق البحث وقتاً طويلاً. يرجى المحاولة مرة أخرى.";
                } else {
                    processStreamingFinished(aiMessageSpan, fullResponseText);
                }
                break;
            }
            
            const chunk = decoder.decode(value, { stream: true });
            fullResponseText += chunk;
            
            aiMessageSpan.innerHTML = fullResponseText; 
            chatBox.scrollTop = chatBox.scrollHeight;
        }

    } catch (error) {
        loading.classList.add("hidden");
        addMessage("فشل الاتصال بالسيرفر بسبب ضعف الإنترنت أو تأخر الرد.", "ai-message");
    }
}

// دالة تعالج النص بعد انتهاء البث للبحث عن الفيديوهات
// دالة لالتقاط أزرار Mux القادمة من الـ الذكاء الاصطناعي بعد انتهاء البث
function processStreamingFinished(textSpanElement, textContent) {
    // 1. تحويل النص إلى HTML ليتم تفعيل الأزرار
    textSpanElement.innerHTML = textContent;

    // 2. البحث عن كل الأزرار التي تحتوي على كلاس mux-jump-btn
    const muxButtons = textSpanElement.querySelectorAll('.mux-jump-btn');
    
    muxButtons.forEach(btn => {
        // تصميم الزر ليكون واضحاً وجذاباً للطالب
        btn.style.display = "inline-block";
        btn.style.marginTop = "10px";
        btn.style.padding = "8px 15px";
        btn.style.background = "#e74c3c";
        btn.style.color = "white";
        btn.style.borderRadius = "5px";
        btn.style.textDecoration = "none";
        btn.style.fontWeight = "bold";




        // اعتراض النقرة لتشغيل Mux
        btn.onclick = (e) => {
            e.preventDefault();
            const playbackId = btn.getAttribute('data-playback-id'); // التقاط المفتاح الديناميكي
            const startTime = parseFloat(btn.getAttribute('data-start'));
            const endTime = parseFloat(btn.getAttribute('data-end'));
            const title = btn.innerText;
    
    // تمريره لدالة التشغيل
            playMuxVideoInSPA(playbackId, startTime, endTime, title);
        };
    });

    // فحص تصاميم الويب العادية (إن وجدت)
    checkAndAddHtmlButton(textSpanElement.parentElement, textContent);
}

// العقل المدبر لتشغيل Mux والقفز للتوقيت المحدد (محرر الفيديو التلقائي)
function playMuxVideoInSPA(playbackId, startTime, endTime, title) {
    const videoViewer = document.getElementById("embedded-video-viewer");
    const muxPlayer = document.getElementById("main-spa-player");
    const clipTitleDisplay = document.getElementById("current-clip-title");
    if (!muxPlayer) return;
    // 1. التحديث الديناميكي لمصدر الفيديو (تعيين Playback ID الجديد)
    muxPlayer.setAttribute('playback-id', playbackId);

    // 2. إظهار الحاوية وتحديث العنوان
    videoViewer.classList.remove("hidden");
    clipTitleDisplay.innerText = "جاري العرض: " + title;

    // 3. القفز للتوقيت المحدد وبدء التشغيل
    // نستخدم مهلة زمنية بسيطة (150 ملي ثانية) لضمان تحميل Mux لمعرف الفيديو الجديد قبل القفز بالزمن
    setTimeout(() => {
        muxPlayer.currentTime = startTime;
        muxPlayer.play();
    }, 150); 

    // 4. مستمع ذكي لإيقاف الفيديو تلقائياً عند نهاية النقطة التي حددها Twelve Labs
    const autoPause = () => {
        if (muxPlayer.currentTime >= endTime) {
            muxPlayer.pause();
            muxPlayer.removeEventListener('timeupdate', autoPause); // تنظيف الذاكرة لمنع تداخل الأوامر
        }
    };
    
    // إزالة أي مستمعات قديمة (لفيديوهات سابقة) ثم إضافة المستمع الجديد
    muxPlayer.removeEventListener('timeupdate', autoPause);
    muxPlayer.addEventListener('timeupdate', autoPause);

    // 5. تمرير الشاشة للأسفل لرؤية المشغل بوضوح
    const chatBox = document.getElementById("chat-box");
    chatBox.scrollTop = chatBox.scrollHeight;
}
// دالة الإغلاق
function closeVideoViewer() {
    const videoViewer = document.getElementById("embedded-video-viewer");
    const muxPlayer = document.getElementById("main-spa-player");
    muxPlayer.pause();
    videoViewer.classList.add("hidden");
}



// دالة لإغلاق مشغل الفيديو والعودة لوضع الدردشة الكاملة
function closeVideoViewer() {
    spaPlayer.pause();
    spaPlayer.src = ""; // تفريغ المصدر لتوفير الموارد
    videoViewer.classList.add("hidden");
}

// كود الأيقونة الحديثة (مربعين متداخلين) لتسهيل استخدامه في الدالتين
const copyIconSVG = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`;

function addMessage(text, className) {
    const div = document.createElement("div");
    div.className = `message ${className}`;

    const textSpan = document.createElement("span");
    textSpan.style.whiteSpace = "pre-wrap"; 
    textSpan.innerText = text;
    div.appendChild(textSpan);

    const copyBtn = document.createElement("button");
    copyBtn.innerHTML = copyIconSVG; 
    copyBtn.style.marginRight = "10px";
    copyBtn.style.marginLeft = "10px";
    copyBtn.style.cursor = "pointer";
    copyBtn.style.background = "transparent";
    copyBtn.style.border = "none";
    copyBtn.style.color = "#94a3b8"; // لون رمادي أنيق للأيقونة
    copyBtn.title = "نسخ النص";
    
    // تأثير بسيط عند تمرير الماوس
    copyBtn.onmouseover = () => copyBtn.style.color = "#3b82f6";
    copyBtn.onmouseout = () => copyBtn.style.color = "#94a3b8";
    
    copyBtn.onclick = () => {
        navigator.clipboard.writeText(text).then(() => {
            copyBtn.innerHTML = "✅";
            copyBtn.style.color = "#10b981"; // لون أخضر عند النجاح
            setTimeout(() => {
                copyBtn.innerHTML = copyIconSVG;
                copyBtn.style.color = "#94a3b8";
            }, 2000);
        });
    };
    div.appendChild(copyBtn);

    // إضافة زر عرض التصميم للرسائل الجاهزة
    if (className === "ai-message") {
        checkAndAddHtmlButton(div, text);
    }

    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function createEmptyAiMessage() {
    const div = document.createElement("div");
    div.className = `message ai-message`;
    
    const textSpan = document.createElement("span");
    textSpan.style.whiteSpace = "pre-wrap"; 
    
    const copyBtn = document.createElement("button");
    copyBtn.innerHTML = copyIconSVG;
    copyBtn.style.marginRight = "10px";
    copyBtn.style.cursor = "pointer";
    copyBtn.style.background = "transparent";
    copyBtn.style.border = "none";
    copyBtn.style.color = "#94a3b8"; // لون رمادي أنيق للأيقونة
    copyBtn.title = "نسخ النص";
    
    // تأثير بسيط عند تمرير الماوس
    copyBtn.onmouseover = () => copyBtn.style.color = "#3b82f6";
    copyBtn.onmouseout = () => copyBtn.style.color = "#94a3b8";
    
    copyBtn.onclick = () => {
        navigator.clipboard.writeText(textSpan.innerText).then(() => {
            copyBtn.innerHTML = "✅";
            copyBtn.style.color = "#10b981"; // لون أخضر عند النجاح
            setTimeout(() => {
                copyBtn.innerHTML = copyIconSVG;
                copyBtn.style.color = "#94a3b8";
            }, 2000);
        });
    };

    div.appendChild(copyBtn);
    div.appendChild(textSpan);
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;

    return textSpan; 
}






// دالة مساعدة معزولة للبحث عن كود HTML (تصاميم الويب) وإضافة زر "عرض التصميم"
// (ملاحظة: تم تعديلها لتجاهل أكواد الفيديو لأنها تُعالج الآن في playVideoInSPA)
function checkAndAddHtmlButton(messageDiv, text) {
    const backticks = "```";
    const regexString = backticks + "(?:html|xml)\\n([\\s\\S]*?)" + backticks;
    const regex = new RegExp(regexString, "i");
    
    const htmlMatch = text.match(regex);
    
    if (htmlMatch && htmlMatch[1]) {
        if (messageDiv.querySelector('.html-view-btn') || messageDiv.querySelector('.video-container')) {
            return;
        }
        
        const htmlCode = htmlMatch[1];
        
        // نتجاهل أكواد الفيديو هنا لأنها تُعالج الآن عبر روابط A المخصصة
        // التعديل: نتجاهل أكواد الفيديو والصور معاً لكي لا تتحول إلى زر "عرض التصميم"
        if (htmlCode.includes('<video') || htmlCode.includes('<img')) {
            return; 
        }
        // كود HTML عادي (تصميم ويب)
        const viewBtn = document.createElement("button");
        viewBtn.innerHTML = "🌐 عرض التصميم";
        viewBtn.className = "html-view-btn";
        viewBtn.style.background = "#059669";
        viewBtn.style.color = "white";
        viewBtn.style.marginTop = "15px";
        viewBtn.style.display = "block";
        viewBtn.style.padding = "8px 12px";
        viewBtn.style.border = "none";
        viewBtn.style.borderRadius = "6px";
        viewBtn.style.cursor = "pointer";
        
        viewBtn.onclick = () => {
            const newWindow = window.open("", "_blank");
            newWindow.document.write(htmlCode);
            newWindow.document.close();
        };
        
        messageDiv.appendChild(viewBtn);
    }
}



async function performQuery() {
    const resultsDiv = document.getElementById("query-results");
    
    try {
        const queryType = document.getElementById("query-type").value;
        const queryText = document.getElementById("query-input").value.trim().toLowerCase();
        
        // 1. رسالة واضحة لبدء التحميل
        resultsDiv.innerHTML = `<p style="color: #3b82f6; text-align:center; padding: 20px;">⏳ جاري الاتصال بالسيرفر وجلب البيانات...</p>`;

        const endpoint = queryType === 'students' ? '/students/' : '/documents/';
        const token = localStorage.getItem("token");

        // 2. التحقق من وجود التوكن
        if (!token) {
            resultsDiv.innerHTML = `<p style="color: #ef4444; text-align:center; padding: 20px;">❌ غير مصرح لك! يرجى تسجيل الدخول أولاً.</p>`;
            return;
        }

        // الاتصال بالسيرفر
        const res = await fetch(`${BASE_URL}${endpoint}`, {
            method: "GET",
            headers: { 
                "Authorization": `Bearer ${token}` 
            }
        });

        // 3. التقاط أخطاء السيرفر (مثل 401 انتهاء الجلسة، أو 500 خطأ داخلي)
        if (!res.ok) {
            const errText = await res.text();
            resultsDiv.innerHTML = `<p style="color: #ef4444; text-align:center; padding: 20px;">❌ رفض السيرفر الطلب (الرمز: ${res.status}).<br>التفاصيل: ${errText}<br>💡 الحل: جرب تسجيل الخروج ثم الدخول مجدداً.</p>`;
            return;
        }

        // 4. تحليل البيانات
        const data = await res.json();
        
        // التحقق من أن السيرفر أرسل قائمة (Array)
        if (!Array.isArray(data)) {
            resultsDiv.innerHTML = `<p style="color: #ef4444; text-align:center; padding: 20px;">❌ السيرفر أرجع بيانات غير متوقعة (ليست قائمة).</p>`;
            return;
        }

        // ================= عرض الطلاب =================
        if (queryType === 'students') {
            const filtered = data.filter(s => 
                (s.full_name && s.full_name.toLowerCase().includes(queryText)) || 
                (s.university_id && String(s.university_id).includes(queryText))
            );

            if (filtered.length === 0) {
                resultsDiv.innerHTML = `<p style="color: #fbbf24; text-align:center; padding: 20px;">⚠️ لا يوجد طلاب يطابقون بحثك.</p>`;
                return;
            }

            let html = `<table style="width:100%; text-align:right; border-collapse: collapse; margin-top: 15px; background: #1e293b; border-radius: 8px; overflow: hidden;">
                            <thead>
                                <tr style="background: #334155; color: #e2e8f0;">
                                    <th style="padding: 12px; width: 20%;">ID</th>
                                    <th style="padding: 12px; width: 30%;">الرقم الجامعي</th>
                                    <th style="padding: 12px; width: 50%;">الاسم</th>
                                </tr>
                            </thead>
                            <tbody>`;
            filtered.forEach(s => {
                html += `<tr style="border-bottom: 1px solid #334155; transition: 0.3s;" onmouseover="this.style.background='#475569'" onmouseout="this.style.background='transparent'">
                            <td style="padding: 12px; color: #94a3b8;">#${s.id}</td>
                            <td style="padding: 12px; color: #3b82f6; font-weight: bold;">${s.university_id}</td>
                            <td style="padding: 12px;">${s.full_name}</td>
                         </tr>`;
            });
            html += `</tbody></table>`;
            resultsDiv.innerHTML = html;

        // ================= عرض المناهج =================
        } else if (queryType === 'documents') {
            const filtered = data.filter(d => {
                const docName = d.filename || d.title || d.name || ""; 
                return docName.toLowerCase().includes(queryText);
            });

            if (filtered.length === 0) {
                resultsDiv.innerHTML = `<p style="color: #fbbf24; text-align:center; padding: 20px;">⚠️ لم يتم العثور على مناهج.</p>`;
                return;
            }

            let html = `<table style="width:100%; text-align:right; border-collapse: collapse; margin-top: 15px; background: #1e293b; border-radius: 8px; overflow: hidden;">
                            <thead>
                                <tr style="background: #0f766e; color: #e2e8f0;">
                                    <th style="padding: 12px; width: 20%;">رقم الملف</th>
                                    <th style="padding: 12px; width: 60%;">اسم المنهج</th>
                                    <th style="padding: 12px; width: 20%;">الحالة</th>
                                </tr>
                            </thead>
                            <tbody>`;
            filtered.forEach(d => {
                const docName = d.filename || d.title || d.name || "مستند بدون اسم";
                html += `<tr style="border-bottom: 1px solid #334155; transition: 0.3s;" onmouseover="this.style.background='#475569'" onmouseout="this.style.background='transparent'">
                            <td style="padding: 12px; color: #94a3b8;">#${d.id || '-'}</td>
                            <td style="padding: 12px; color: #10b981; font-weight: bold;">${docName}</td>
                            <td style="padding: 12px; color: #fbbf24;">جاهز في RAG</td>
                         </tr>`;
            });
            html += `</tbody></table>`;
            resultsDiv.innerHTML = html;
        }

    } catch (error) {
        // 5. التقاط الانهيارات البرمجية (Exceptions)
        resultsDiv.innerHTML = `<p style="color: #ef4444; text-align:center; padding: 20px;">💥 حدث خطأ برمجي مفاجئ: <br><br> ${error.message}</p>`;
        console.error("Query Error: ", error);
    }
}


// افتراض أنك تلتقط النقر على زر الفيديو داخل شاشة الدردشة
document.addEventListener('click', function(e) {
    if (e.target && e.target.classList.contains('mux-jump-btn')) {
        e.preventDefault();
        
        const playbackId = e.target.getAttribute('data-playback-id');
        const startTime = parseFloat(e.target.getAttribute('data-start'));
        const endTime = parseFloat(e.target.getAttribute('data-end'));
        
        // جلب عناصر المشغل من الواجهة
        const viewerContainer = document.getElementById('video-viewer-container');
        const player = document.getElementById('main-mux-player');
        
        if (viewerContainer && player) {
            viewerContainer.classList.remove('hidden'); // إظهار حاوية الفيديو
            
            // 1. استخدام خاصية Mux الذكية للقفز الآمن قبل التشغيل
            player.setAttribute('playback-id', playbackId);
            player.setAttribute('start-time', startTime);
            
            // 2. التشغيل الآمن
            player.play().catch(err => console.log("تحذير تشغيل Mux:", err));
            
            // 3. آلية التوقف التلقائي (Auto-Pause)
            const autoPause = () => {
                if (player.currentTime >= endTime) {
                    player.pause();
                    player.removeEventListener('timeupdate', autoPause);
                    console.log("انتهت اللقطة الأكاديمية المطلوبة.");
                }
            };
            
            player.removeEventListener('timeupdate', autoPause);
            player.addEventListener('timeupdate', autoPause);
        }
    }
});