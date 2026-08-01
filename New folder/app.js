/* ═══════════════════════════════════════════════════════════════
   DKM SMART UNIVERSITY — app.js (Production Version - Real API)
   ═══════════════════════════════════════════════════════════════ */

/* ─────────────────────────────────────────────────────────────
   1. CONFIGURATION
   ───────────────────────────────────────────────────────────── */
//const CONFIG = {
 // API_BASE_URL: 'https://fristproject-production.up.railway.app', // رابط السيرفر الحقيقي
 // USE_MOCK: false, 
  //ITEMS_PER_PAGE: 8,
//};
const CONFIG = {
  API_BASE_URL: 'http://127.0.0.1:8000', // الرابط المحلي للتجربة
  USE_MOCK: false, 
  ITEMS_PER_PAGE: 8,
};/* ─────────────────────────────────────────────────────────────
   2. APP STATE
   ───────────────────────────────────────────────────────────── */
const AppState = {
  currentUser: null,
  currentScreen: 'dashboard',
  theme: localStorage.getItem('dkm-theme') || 'dark',
  sidebarCollapsed: false,
  chatMode: 'docs', // الافتراضي هو المستندات
  chatMessages: [],
  activeChatId: 'ch-main',
  queryData: [],
  queryPage: 1,
  queryTotal: 0,
  querySortKey: 'id',
  querySortAsc: true,
  queryFilter: { type: 'all', status: 'all', search: '' },
  uploadedFiles: [],
};

/* ─────────────────────────────────────────────────────────────
   3. REAL API LAYER (الارتباط المباشر بالباك إند)
   ───────────────────────────────────────────────────────────── */
const API = {
  async login(universityId, password) {
    const formData = new URLSearchParams();
    formData.append("username", universityId);
    formData.append("password", password);

    const res = await fetch(`${CONFIG.API_BASE_URL}/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: formData
    });

    if (!res.ok) throw new Error('الرقم الجامعي أو كلمة المرور غير صحيحة');
    const data = await res.json();
    localStorage.setItem("token", data.access_token);
    return { user: { id: universityId, name: "طالب مسجل", role: 'طالب' }, token: data.access_token };
  },

  async register({ name, universityId, password }) {
    const res = await fetch(`${CONFIG.API_BASE_URL}/students/register/?university_id=${universityId}&full_name=${name}&password=${password}`, {
      method: "POST"
    });
    if (!res.ok) throw new Error('هذا الرقم الجامعي مسجل مسبقاً أو حدث خطأ');
    return await res.json();
  },

  async getFiles() {
    const token = localStorage.getItem("token");
    const res = await fetch(`${CONFIG.API_BASE_URL}/documents/`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${token}` }
    });
    if (!res.ok) return [];
    const data = await res.json();
    // تحويل صيغة الباك إند لتناسب الواجهة
    return data.map(d => ({
        id: d.id || Date.now(),
        name: d.filename || d.title || d.name || "مستند",
        type: (d.filename && String(d.filename).endsWith('.mp4')) ? 'video' : 'pdf',
        size: '-',
        date: 'مكتمل',
        status: 'done'
    }));
  },

  async uploadFile(file, type, onProgress) {
    const token = localStorage.getItem("token");
    const formData = new FormData();
    formData.append("file", file);
    const endpoint = type === 'video' ? "/documents/upload-video/" : "/documents/upload/";
    
    // محاكاة بصرية للشريط التقدم ثم الإرسال الفعلي
    onProgress(50);
    const res = await fetch(`${CONFIG.API_BASE_URL}${endpoint}`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${token}` },
        body: formData
    });
    
    if (!res.ok) throw new Error("فشل الرفع للسيرفر");
    onProgress(100);
    return { id: Date.now(), name: file.name, type, size: formatFileSize(file.size), date: 'الآن', status: 'done' };
  },

  async getQueryData(params) {
    const token = localStorage.getItem("token");
    // تحديد مسار البحث بناء على الفلتر
    let typeToFetch = params.type === 'curriculum' ? 'documents' : 'students';
    if (params.type === 'all') typeToFetch = 'students'; // الافتراضي

    const res = await fetch(`${CONFIG.API_BASE_URL}/${typeToFetch}/`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${token}` }
    });

    if (!res.ok) return { rows: [], total: 0 };
    const data = await res.json();

    let rows = data.map(item => ({
        id: item.id || item.university_id,
        name: item.full_name || item.filename || item.title || "غير معروف",
        type: typeToFetch === 'students' ? 'student' : 'curriculum',
        date: 'نشط',
        status: 'active'
    }));

    if (params.search) {
      const q = params.search.toLowerCase();
      rows = rows.filter(r => r.name.toLowerCase().includes(q) || String(r.id).includes(q));
    }
    return { rows, total: rows.length };
  },

  async sendChatMessageStream(message, mode) {
    const token = localStorage.getItem("token");
    const res = await fetch(`${CONFIG.API_BASE_URL}/chat/`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ question: message, search_mode: mode || "docs" })
    });
    if (!res.ok) throw new Error("حدث خطأ في سيرفر الذكاء الاصطناعي");
    return res.body.getReader(); // استرجاع البث
  }
};

/* ─────────────────────────────────────────────────────────────
   4. UTILITY HELPERS
   ───────────────────────────────────────────────────────────── */
function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  return (bytes / 1024 / 1024 / 1024).toFixed(1) + ' GB';
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function typeLabels(type) {
  const map = { student: 'طالب', curriculum: 'منهج', session: 'جلسة' };
  return map[type] || type;
}
function typeBadge(type) {
  const map = { student: 'badge-blue', curriculum: 'badge-green', session: 'badge-purple' };
  return map[type] || 'badge-gray';
}
function statusLabel(s) {
  const map = { active: 'نشط', pending: 'معلق', done: 'مكتمل', error: 'خطأ' };
  return map[s] || s;
}
function statusBadge(s) {
  const map = { active: 'badge-green', pending: 'badge-yellow', done: 'badge-blue', error: 'badge-red', processing: 'badge-yellow' };
  return map[s] || 'badge-gray';
}

function showToast(type, message, duration = 3500) {
  const icons = { success: 'fa-circle-check', error: 'fa-circle-xmark', info: 'fa-circle-info', warning: 'fa-triangle-exclamation' };
  const container = document.getElementById('toast-container');
  if(!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<i class="fa-solid ${icons[type] || 'fa-circle-info'}"></i><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('removing');
    setTimeout(() => toast.remove(), 350);
  }, duration);
}

function freezeFeature(msg = "هذه الميزة قيد التطوير وسيتم إتاحتها قريباً") {
  showToast('warning', msg);
}

/* ─────────────────────────────────────────────────────────────
   5. THEME & NAVIGATION
   ───────────────────────────────────────────────────────────── */
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  AppState.theme = theme;
  localStorage.setItem('dkm-theme', theme);
  const icon = theme === 'dark' ? 'fa-sun' : 'fa-moon';
  document.querySelectorAll('#theme-toggle, #theme-toggle-mobile').forEach(btn => {
    btn.innerHTML = `<i class="fa-solid ${icon}"></i>`;
  });
}

function toggleTheme() {
  applyTheme(AppState.theme === 'dark' ? 'light' : 'dark');
}

function navigateTo(screen) {
  if(screen === 'dashboard') {
    freezeFeature("لوحة الإحصائيات المركزية قريباً");
    return; // تعطيل صفحة الداشبورد لأنها غير متوفرة في الباك إند حالياً
  }

  document.querySelectorAll('.app-screen').forEach(s => s.classList.remove('active'));
  document.getElementById(`screen-${screen}`)?.classList.add('active');

  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`nav-${screen}`)?.classList.add('active');

  document.querySelectorAll('.bottom-nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`bn-${screen}`)?.classList.add('active');

  AppState.currentScreen = screen;
  closeMobileSidebar();

  if (screen === 'upload') loadUploadScreen();
  if (screen === 'query') loadQueryScreen();
  if (screen === 'chat') loadChatScreen();
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  if(sidebar) {
      AppState.sidebarCollapsed = !AppState.sidebarCollapsed;
      sidebar.classList.toggle('collapsed', AppState.sidebarCollapsed);
  }
}
function toggleMobileSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  if(sidebar && overlay) {
      sidebar.classList.toggle('mobile-open');
      overlay.classList.toggle('hidden', !sidebar.classList.contains('mobile-open'));
  }
}
function closeMobileSidebar() {
  document.getElementById('sidebar')?.classList.remove('mobile-open');
  document.getElementById('sidebar-overlay')?.classList.add('hidden');
}

/* ─────────────────────────────────────────────────────────────
   6. AUTHENTICATION
   ───────────────────────────────────────────────────────────── */
function switchAuthTab(tab) {
  document.getElementById('form-login').classList.toggle('hidden', tab !== 'login');
  document.getElementById('form-register').classList.toggle('hidden', tab !== 'register');
  document.getElementById('tab-login').classList.toggle('active', tab === 'login');
  document.getElementById('tab-register').classList.toggle('active', tab === 'register');
}

async function handleLogin(e) {
  e.preventDefault();
  const id = document.getElementById('login-id').value.trim();
  const pw = document.getElementById('login-pass').value;
  if (!id || !pw) { showToast('warning', 'يرجى إدخال جميع الحقول'); return; }

  setButtonLoading('btn-login', true);
  try {
    const { user } = await API.login(id, pw);
    AppState.currentUser = user;
    enterApp(user);
    showToast('success', `مرحباً بك في نظام DKM 👋`);
  } catch (err) {
    showToast('error', err.message);
  } finally {
    setButtonLoading('btn-login', false);
  }
}

async function handleRegister(e) {
  e.preventDefault();
  const name = document.getElementById('reg-name').value.trim();
  const id   = document.getElementById('reg-id').value.trim();
  const pw   = document.getElementById('reg-pass').value;
  const pw2  = document.getElementById('reg-pass2').value;

  if (!name || !id || !pw) { showToast('warning', 'يرجى إدخال جميع الحقول'); return; }
  if (pw !== pw2) { showToast('error', 'كلمتا المرور غير متطابقتين'); return; }

  setButtonLoading('btn-register', true);
  try {
    // 1. إنشاء الحساب
    await API.register({ name, universityId: id, password: pw });
    showToast('success', `تم إنشاء الحساب! جاري تسجيل الدخول...`);
    
    // 2. تسجيل الدخول التلقائي بعد إنشاء الحساب
    const { user } = await API.login(id, pw);
    AppState.currentUser = user;
    enterApp(user);
  } catch (err) {
    showToast('error', err.message);
  } finally {
    setButtonLoading('btn-register', false);
  }
}

function setButtonLoading(btnId, loading) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.querySelector('.btn-text')?.classList.toggle('hidden', loading);
  btn.querySelector('.btn-spinner')?.classList.toggle('hidden', !loading);
  btn.disabled = loading;
}

function enterApp(user) {
  document.getElementById('screen-auth')?.classList.remove('active');
  document.getElementById('app-shell')?.classList.remove('hidden');

  const firstName = user.name.split(' ')[0];
  if(document.getElementById('sidebar-name')) document.getElementById('sidebar-name').textContent = user.name;
  if(document.getElementById('sidebar-avatar')) document.getElementById('sidebar-avatar').textContent = firstName[0];

  navigateTo('chat'); // توجيه مباشر للوكيل الذكي لأن الداشبورد مجمدة
}

function handleLogout() {
  localStorage.removeItem("token");
  AppState.currentUser = null;
  document.getElementById('app-shell')?.classList.add('hidden');
  document.getElementById('screen-auth')?.classList.add('active');
  document.getElementById('form-login')?.reset();
  showToast('info', 'تم تسجيل الخروج بنجاح');
}

function togglePassword(inputId, btn) {
  const input = document.getElementById(inputId);
  if(!input) return;
  const isPass = input.type === 'password';
  input.type = isPass ? 'text' : 'password';
  btn.innerHTML = `<i class="fa-solid ${isPass ? 'fa-eye-slash' : 'fa-eye'}"></i>`;
}

/* ─────────────────────────────────────────────────────────────
   7. UPLOAD SCREEN
   ───────────────────────────────────────────────────────────── */
async function loadUploadScreen() {
  renderFilesList();
}

function handleDragOver(e, zoneId) { e.preventDefault(); document.getElementById(zoneId)?.classList.add('drag-over'); }
function handleDragLeave(zoneId) { document.getElementById(zoneId)?.classList.remove('drag-over'); }
function handleDrop(e, type) {
  e.preventDefault();
  const zoneId = type === 'pdf' ? 'pdf-drop-zone' : 'video-drop-zone';
  document.getElementById(zoneId)?.classList.remove('drag-over');
  const files = Array.from(e.dataTransfer.files);
  files.forEach(file => startUpload(file, type));
}
function handleFileSelect(e, type) {
  Array.from(e.target.files).forEach(file => startUpload(file, type));
  e.target.value = '';
}

async function startUpload(file, type) {
  const queueId = type === 'pdf' ? 'pdf-queue' : 'video-queue';
  const itemId  = 'upload-' + Date.now();
  const queue = document.getElementById(queueId);
  if(!queue) return;

  const item  = document.createElement('div');
  item.className = 'upload-item';
  item.id = itemId;
  item.innerHTML = `
    <i class="fa-solid ${type === 'pdf' ? 'fa-file-pdf pdf-icon' : 'fa-film video-icon-c'} upload-item-icon"></i>
    <div class="upload-item-body">
      <div class="upload-item-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</div>
      <div class="progress-bar-wrap"><div class="progress-bar" id="pb-${itemId}" style="width:0%"></div></div>
    </div>
    <span class="upload-status status-uploading" id="st-${itemId}">جاري الرفع...</span>
  `;
  queue.appendChild(item);

  try {
    await API.uploadFile(file, type, (pct) => {
      const pb = document.getElementById(`pb-${itemId}`);
      if (pb) pb.style.width = pct + '%';
    });
    
    document.getElementById(`st-${itemId}`).textContent = 'مكتمل ✓';
    showToast('success', `تم إرسال "${file.name}" للسيرفر للمعالجة`);
    setTimeout(() => { item.remove(); renderFilesList(); }, 2000);
  } catch (err) {
    document.getElementById(`st-${itemId}`).textContent = 'فشل';
    showToast('error', `فشل رفع "${file.name}"`);
  }
}

let _allFiles = [];
async function renderFilesList() {
  const list = document.getElementById('files-list');
  if(!list) return;
  list.innerHTML = '<div class="activity-skeleton" style="margin:12px 18px;height:40px;border-radius:8px"></div>';
  _allFiles = await API.getFiles();
  renderFilesFiltered(_allFiles);
}

function renderFilesFiltered(files) {
  const list = document.getElementById('files-list');
  if(!list) return;
  if (!files.length) {
    list.innerHTML = '<p style="padding:24px;text-align:center;color:var(--text-muted)">لا توجد مناهج مرفوعة بعد</p>';
    return;
  }
  list.innerHTML = files.map(f => `
    <div class="file-row" data-type="${f.type}" data-id="${f.id}">
      <i class="fa-solid ${f.type === 'pdf' ? 'fa-file-pdf' : 'fa-film'} file-row-icon" style="color:${f.type === 'pdf' ? '#ef4444' : '#8b5cf6'}"></i>
      <span class="file-row-name">${escapeHtml(f.name)}</span>
      <span class="file-row-type">${f.type.toUpperCase()}</span>
      <span class="file-row-status"><span class="badge ${statusBadge(f.status)}">${statusLabel(f.status)}</span></span>
      <div class="file-row-actions">
        <button class="icon-btn" title="حذف" onclick="freezeFeature('ميزة الحذف ستتوفر قريباً')"><i class="fa-solid fa-trash-can" style="color:var(--clr-danger)"></i></button>
      </div>
    </div>
  `).join('');
}

function filterFiles(query) {
  const filtered = _allFiles.filter(f => f.name.toLowerCase().includes(query.toLowerCase()));
  renderFilesFiltered(filtered);
}

function filterByType(type, btn) {
  document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
  btn.classList.add('active');
  const filtered = type === 'all' ? _allFiles : _allFiles.filter(f => f.type === type);
  renderFilesFiltered(filtered);
}

/* ─────────────────────────────────────────────────────────────
   8. QUERY SCREEN
   ───────────────────────────────────────────────────────────── */
async function loadQueryScreen() {
  AppState.queryPage = 1;
  await fetchAndRenderQuery();
}

async function fetchAndRenderQuery() {
  const { rows, total } = await API.getQueryData({
    search:  AppState.queryFilter.search,
    type:    AppState.queryFilter.type,
  });
  AppState.queryTotal = total;
  renderQueryTable(rows);
  renderQueryCardsMobile(rows);
  renderPagination(total);
}

function handleQuerySearch(val) {
  AppState.queryFilter.search = val;
  clearTimeout(window._qsTimer);
  window._qsTimer = setTimeout(fetchAndRenderQuery, 350);
}

function applyQueryFilter() {
  const typeSelect = document.getElementById('filter-type');
  if(typeSelect) AppState.queryFilter.type = typeSelect.value;
  fetchAndRenderQuery();
}

function sortTable(key) {
  freezeFeature("الفرز المتقدم قريباً");
}

function renderQueryTable(rows) {
  const tbody = document.getElementById('query-tbody');
  if(!tbody) return;
  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:32px;color:var(--text-muted)">لا توجد بيانات مطابقة</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(r => `
    <tr>
      <td><span style="font-family:monospace;color:var(--text-muted)">#${r.id}</span></td>
      <td><strong>${escapeHtml(r.name)}</strong></td>
      <td><span class="badge ${typeBadge(r.type)}">${typeLabels(r.type)}</span></td>
      <td><span class="badge ${statusBadge(r.status)}">${statusLabel(r.status)}</span></td>
      <td>
        <div style="display:flex;gap:6px">
          <button class="icon-btn" title="تعديل/حذف" onclick="freezeFeature('التعديل والحذف قريباً')"><i class="fa-solid fa-ban" style="color:var(--text-muted)"></i></button>
        </div>
      </td>
    </tr>
  `).join('');
}

function renderQueryCardsMobile(rows) {
  const container = document.getElementById('query-cards-mobile');
  if(!container) return;
  if (!rows.length) {
    container.innerHTML = `<p style="text-align:center;color:var(--text-muted);padding:24px">لا توجد بيانات</p>`;
    return;
  }
  container.innerHTML = rows.map(r => `
    <div class="query-card-mobile">
      <div class="qcm-header">
        <span class="qcm-name">${escapeHtml(r.name)}</span>
        <span class="badge ${statusBadge(r.status)}">${statusLabel(r.status)}</span>
      </div>
      <div class="qcm-rows">
        <div class="qcm-row"><span class="qcm-label">المعرف</span><span class="qcm-value">#${r.id}</span></div>
        <div class="qcm-row"><span class="qcm-label">النوع</span><span class="badge ${typeBadge(r.type)}">${typeLabels(r.type)}</span></div>
      </div>
    </div>
  `).join('');
}

function renderPagination(total) {
  const container  = document.getElementById('query-pagination');
  if(!container) return;
  const totalPages = Math.ceil(total / CONFIG.ITEMS_PER_PAGE) || 1;
  let html = `<button class="page-btn" onclick="changePage(${AppState.queryPage - 1})" ${AppState.queryPage <= 1 ? 'disabled' : ''}><i class="fa-solid fa-angle-right"></i></button>`;
  for (let i = 1; i <= totalPages; i++) {
    html += `<button class="page-btn ${i === AppState.queryPage ? 'active' : ''}" onclick="changePage(${i})">${i}</button>`;
  }
  html += `<button class="page-btn" onclick="changePage(${AppState.queryPage + 1})" ${AppState.queryPage >= totalPages ? 'disabled' : ''}><i class="fa-solid fa-angle-left"></i></button>`;
  container.innerHTML = html;
}

function changePage(page) {
  const totalPages = Math.ceil(AppState.queryTotal / CONFIG.ITEMS_PER_PAGE);
  if (page < 1 || page > totalPages) return;
  AppState.queryPage = page;
  fetchAndRenderQuery();
}

function exportData() {
  freezeFeature("تصدير البيانات PDF/CSV قريباً");
}

/* ─────────────────────────────────────────────────────────────
   9. CHAT SCREEN (الوكيل الذكي المتقدم + البث المباشر)
   ───────────────────────────────────────────────────────────── */
async function loadChatScreen() {
  document.getElementById('chat-history-list').innerHTML = '<p style="text-align:center;color:var(--text-muted);font-size:12px;margin-top:10px;">السجل مجمّد حالياً</p>';
}

function startNewChat() {
  AppState.chatMessages = [];
  const container = document.getElementById('chat-messages');
  if(container) container.innerHTML = `
    <div class="chat-welcome" id="chat-welcome">
      <div class="welcome-icon"><i class="fa-solid fa-brain"></i></div>
      <h3>مرحباً بك في وكيل DKM الذكي</h3>
      <p>اسألني عن أي محتوى في مناهجك أو محاضراتك المرئية</p>
    </div>`;
  showToast('info', 'تم بدء محادثة جديدة');
}

function clearChat() { startNewChat(); }
function toggleChatSidebar() { document.getElementById('chat-sidebar')?.classList.toggle('collapsed'); }

function setMode(mode, btn) {
  AppState.chatMode = mode;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

function handleChatKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}
function autoResizeTextarea(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 150) + 'px';
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const text  = input.value.trim();
  if (!text) return;

  document.getElementById('chat-welcome')?.remove();
  appendUserMessage(text);
  input.value = '';
  input.style.height = 'auto';

  document.getElementById('send-btn').disabled = true;
  const thinkingId = showThinkingDots();

  try {
    const reader = await API.sendChatMessageStream(text, AppState.chatMode);
    removeThinkingDots(thinkingId);
    
    // إنشاء فقاعة ذكاء اصطناعي فارغة جاهزة لاستقبال البث
    const streamContainer = createEmptyAiBubble();
    const decoder = new TextDecoder('utf-8');
    let fullText = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) {
            // معالجة الأكواد البرمجية وأزرار الفيديو عند انتهاء البث
            processStreamFinished(streamContainer, fullText);
            break;
        }
        fullText += decoder.decode(value, { stream: true });
        streamContainer.innerHTML = fullText.replace(/\n/g, '<br>');
        scrollChatToBottom();
    }
  } catch (err) {
    removeThinkingDots(thinkingId);
    createEmptyAiBubble().innerHTML = "<span style='color:var(--clr-danger)'>عذراً، حدث خطأ في السيرفر أو انقطع الاتصال.</span>";
  } finally {
    document.getElementById('send-btn').disabled = false;
  }
}

function appendUserMessage(text) {
  const container = document.getElementById('chat-messages');
  const firstName = AppState.currentUser?.name?.split(' ')[0]?.[0] || 'أ';
  const div = document.createElement('div');
  div.className = 'chat-message user';
  div.innerHTML = `
    <div class="msg-avatar user-avatar-chat">${firstName}</div>
    <div class="msg-bubble-wrap">
      <div class="msg-bubble user-bubble">${escapeHtml(text).replace(/\n/g, '<br>')}</div>
    </div>`;
  container.appendChild(div);
  scrollChatToBottom();
}

function createEmptyAiBubble() {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'chat-message';
  div.innerHTML = `
    <div class="msg-avatar ai-avatar"><i class="fa-solid fa-brain"></i></div>
    <div class="msg-bubble-wrap">
      <div class="msg-bubble ai-bubble" style="min-width:100px;"></div>
    </div>`;
  container.appendChild(div);
  scrollChatToBottom();
  return div.querySelector('.ai-bubble');
}

function processStreamFinished(bubbleElement, text) {
  // تفعيل أي أزرار فيديو Mux قادمة من السيرفر
  const wrapper = bubbleElement.parentElement;
  
  // تحويل أزرار الفيديو القديمة (إن وجدت) للشكل الجديد
  const muxBtns = bubbleElement.querySelectorAll('.mux-jump-btn');
  muxBtns.forEach(btn => {
      btn.className = 'video-jump-btn';
      btn.style.display = 'inline-block';
      btn.style.marginTop = '10px';
      btn.innerHTML = `<i class="fa-solid fa-circle-play"></i> ${btn.innerText}`;
      btn.onclick = (e) => {
          e.preventDefault();
          showToast('info', 'سيتم تشغيل الفيديو...'); // اربطه بمشغل الفيديو إذا أردت لاحقاً
      };
  });

  // إضافة أزرار الإجراءات (نسخ النص)
  const actionsDiv = document.createElement('div');
  actionsDiv.className = 'msg-actions';
  actionsDiv.innerHTML = `
    <button class="msg-action-btn" onclick="copyMessage(this,'${encodeURIComponent(text)}')">
      <i class="fa-solid fa-copy"></i> نسخ
    </button>
  `;
  wrapper.appendChild(actionsDiv);
}

function showThinkingDots() {
  const id = 'thinking-' + Date.now();
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'thinking-bubble';
  div.id = id;
  div.innerHTML = `
    <div class="msg-avatar ai-avatar"><i class="fa-solid fa-brain"></i></div>
    <div class="thinking-dots"><span></span><span></span><span></span></div>`;
  container.appendChild(div);
  scrollChatToBottom();
  return id;
}

function removeThinkingDots(id) { document.getElementById(id)?.remove(); }
function scrollChatToBottom() {
  const c = document.getElementById('chat-messages');
  if(c) c.scrollTo({ top: c.scrollHeight, behavior: 'smooth' });
}

async function copyMessage(btn, encodedText) {
  const text = decodeURIComponent(encodedText);
  try {
    await navigator.clipboard.writeText(text);
    btn.innerHTML = '<i class="fa-solid fa-circle-check"></i> تم النسخ!';
    btn.style.color = 'var(--clr-success)';
    setTimeout(() => {
      btn.innerHTML = '<i class="fa-solid fa-copy"></i> نسخ';
      btn.style.color = '';
    }, 2000);
  } catch {
    showToast('error', 'تعذر النسخ');
  }
}

/* ─────────────────────────────────────────────────────────────
   10. INIT & FROZEN FEATURES
   ───────────────────────────────────────────────────────────── */
(function init() {
  applyTheme(AppState.theme);

  // تجميد التبويبات الغير مفعلة في الباك إند
  setTimeout(() => {
      const dashNav = document.getElementById('nav-dashboard');
      const histList = document.getElementById('chat-history-list');
      
      if(dashNav) {
          dashNav.style.opacity = '0.5';
          dashNav.title = 'قريباً';
      }
      if(histList) {
          histList.style.opacity = '0.5';
          histList.style.pointerEvents = 'none';
      }
  }, 500);
})();