const API = '';
let token = localStorage.getItem('oc_token') || '';
let history = [];
let busy = false;
let currentChatId = null;
let pendingFile = null; // { file_id, filename, mime_type, size }
let pushSub = null;

// ─── Auth ────────────────────────────────────────────────────────────────────

async function tryToken(t) {
  try {
    const r = await fetch(`${API}/api/health`, { headers: { Authorization: `Bearer ${t}` } });
    return r.ok;
  } catch (_) { return false; }
}

async function login() {
  const username = document.getElementById('username-input').value.trim();
  const password = document.getElementById('password-input').value;
  if (!username || !password) return;
  setAuthErr('');
  document.getElementById('login-btn').disabled = true;
  try {
    const res = await fetch(`${API}/api/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (res.ok) {
      token = (await res.json()).token;
      localStorage.setItem('oc_token', token);
      showApp();
    } else {
      setAuthErr('Usuario o contraseña incorrectos.');
      document.getElementById('login-btn').disabled = false;
      document.getElementById('password-input').focus();
    }
  } catch (_) {
    setAuthErr('Error de conexión con el servidor.');
    document.getElementById('login-btn').disabled = false;
  }
}

function setAuthErr(msg) { document.getElementById('auth-error').textContent = msg; }

function logout() { localStorage.removeItem('oc_token'); location.reload(); }

// ─── Init ────────────────────────────────────────────────────────────────────

async function init() {
  if (token) {
    if (await tryToken(token)) { showApp(); return; }
    localStorage.removeItem('oc_token');
    token = '';
  }
  document.getElementById('username-input').focus();
}

async function showApp() {
  document.getElementById('auth-screen').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  await loadChatList();
  document.getElementById('msg-input').focus();
  initPush();
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────

let sidebarOpen = false;

function toggleSidebar() { sidebarOpen ? closeSidebar() : openSidebar(); }

function openSidebar() {
  sidebarOpen = true;
  document.getElementById('sidebar').classList.add('open');
  document.getElementById('sidebar-overlay').classList.add('open');
}

function closeSidebar() {
  sidebarOpen = false;
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('open');
}

// ─── Chat list ───────────────────────────────────────────────────────────────

let chatList = [];
let workspaceList = [];
let projectList = [];
let currentScope = { workspace_id: 'general', project_id: null, scope_source: 'auto' };
const recentLimit = 5;

async function loadChatList() {
  try {
    const r = await fetch('/api/chats', { headers: { Authorization: `Bearer ${token}` } });
    const data = await r.json();
    chatList = data.chats || [];
    workspaceList = data.workspaces || [];
    projectList = data.projects || [];
    renderChatList();
    if (chatList.length > 0) {
      await loadChat(chatList[0].id);
    } else {
      await startNewChat();
    }
  } catch (_) {
    await startNewChat();
  }
}

function renderChatList() {
  const el = document.getElementById('chat-list');
  const chat = c => {
    const active = c.id === currentChatId ? 'active' : '';
    const date = c.updated ? fmtDate(c.updated) : '';
    return `<div class="chat-item ${active}" onclick="loadChat('${c.id}')">
      <div class="chat-item-top">
        <span class="chat-item-title">${esc(c.title)}</span>
        <span class="chat-item-date">${date}</span>
      </div>
      ${c.preview ? `<div class="chat-item-preview">${esc(c.preview)}</div>` : ''}
      <button class="chat-item-del" onclick="deleteChat(event,'${c.id}')" title="Eliminar">✕</button>
    </div>`;
  };
  const inScope = (workspaceId, projectId = null) => chatList.filter(c =>
    c.workspace_id === workspaceId && (projectId ? c.project_id === projectId : !c.project_id)
  );
  const section = (label, items, workspaceId, projectId = null, depth = '') => `<section class="space-section ${depth}">
    <div class="space-label">${label}<button onclick="startNewChat('${workspaceId}', ${projectId ? `'${projectId}'` : 'null'})" title="Nueva conversación aquí">＋</button></div>
    <div class="space-chats">${items.length ? items.map(chat).join('') : '<div class="space-empty">Sin conversaciones</div>'}</div>
  </section>`;
  const recent = chatList.slice(0, recentLimit);
  const spaces = workspaceList.map(w => {
    if (w.id !== 'projects') return section(`${w.icon} ${esc(w.name)}`, inScope(w.id), w.id);
    const projectSections = projectList.map(p => section(esc(p.name), inScope('projects', p.id), 'projects', p.id, 'project')).join('');
    const direct = inScope('projects');
    return `<section class="space-section projects"><div class="space-label">${w.icon} ${esc(w.name)}</div>${direct.length ? `<div class="space-chats">${direct.map(chat).join('')}</div>` : ''}${projectSections}</section>`;
  }).join('');
  el.innerHTML = (recent.length ? section('Recientes', recent, 'general') : '') + spaces;
}

function fmtDate(iso) {
  const d = new Date(iso);
  const now = new Date();
  const diff = now - d;
  if (diff < 86400000 && d.getDate() === now.getDate()) {
    return d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleDateString('es', { day: 'numeric', month: 'short' });
}

async function startNewChat(workspaceId = 'general', projectId = null) {
  // Project buttons pass the project name; resolve it to its stable id.
  const project = projectList.find(p => p.id === projectId || p.name === projectId);
  if (project) { workspaceId = 'projects'; projectId = project.id; }
  try {
    const r = await fetch('/api/chats', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: workspaceId, project_id: projectId }),
    });
    const chat = await r.json();
    chatList.unshift(chat);
    currentChatId = chat.id;
    currentScope = { workspace_id: chat.workspace_id, project_id: chat.project_id, scope_source: chat.scope_source };
    history = [];
    renderChatList();
    showWelcome();
    renderChatScope(chat);
    closeSidebar();
    document.getElementById('msg-input').focus();
  } catch (_) {
    history = [];
    showWelcome();
  }
}

async function loadChat(id) {
  try {
    const r = await fetch(`/api/chats/${id}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!r.ok) return;
    const chat = await r.json();
    currentChatId = id;
    history = chat.messages || [];
    currentScope = { workspace_id: chat.workspace_id || 'general', project_id: chat.project_id || null, scope_source: chat.scope_source || 'auto' };
    renderMessages();
    renderChatScope(chat);
    renderChatList();
    closeSidebar();
    scrollBottom();
    document.getElementById('msg-input').focus();
  } catch (_) { /* ignore */ }
}

async function deleteChat(e, id) {
  e.stopPropagation();
  await fetch(`/api/chats/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  chatList = chatList.filter(c => c.id !== id);
  if (currentChatId === id) {
    if (chatList.length > 0) await loadChat(chatList[0].id);
    else await startNewChat();
  } else {
    renderChatList();
  }
}

async function saveCurrentChat() {
  if (!currentChatId) return;
  try {
    await fetch(`/api/chats/${currentChatId}`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: history, ...currentScope }),
    });
    const r = await fetch('/api/chats', { headers: { Authorization: `Bearer ${token}` } });
    chatList = (await r.json()).chats || [];
    renderChatList();
  } catch (_) { /* ignore */ }
}

function scopeName(scope) {
  const workspace = workspaceList.find(w => w.id === scope.workspace_id);
  const project = projectList.find(p => p.id === scope.project_id);
  return project ? `Projects · ${project.name}` : (workspace ? workspace.name : 'General');
}

function renderChatScope(chat) {
  document.getElementById('chat-title-hdr').textContent = scopeName(chat.workspace_id ? chat : currentScope);
}

function toggleScopePicker() {
  if (!currentChatId) return;
  const el = document.getElementById('scope-picker');
  if (!el.classList.contains('hidden')) { el.classList.add('hidden'); return; }
  const choices = workspaceList.filter(w => w.id !== 'projects').map(w =>
    `<button onclick="moveCurrentChat('${w.id}', null)">${w.icon} ${esc(w.name)}</button>`
  ).join('') + projectList.map(p => `<button onclick="moveCurrentChat('projects', '${p.id}')">🚀 ${esc(p.name)}</button>`).join('');
  el.innerHTML = `<div class="scope-picker-title">Mover conversación a…</div>${choices}`;
  el.classList.remove('hidden');
}

async function moveCurrentChat(workspaceId, projectId) {
  if (!currentChatId) return;
  currentScope = { workspace_id: workspaceId, project_id: projectId, scope_source: 'manual' };
  await saveCurrentChat();
  renderChatScope(currentScope);
  document.getElementById('scope-picker').classList.add('hidden');
}

function renderMessages() {
  const msgs = document.getElementById('messages');
  if (!history.length) { showWelcome(); return; }
  msgs.innerHTML = '';
  for (const msg of history) {
    if (msg.role === 'user') appendUserMsg(msg.content, false);
    else if (msg.role === 'assistant') {
      const bubble = appendAssistantBubble();
      bubble._rawText = msg.content;
      bubble.innerHTML = renderMd(msg.content);
      bubble.classList.remove('cursor');
    }
  }
}

// ─── Welcome ─────────────────────────────────────────────────────────────────

function showWelcome() {
  document.getElementById('messages').innerHTML = `
    <div class="welcome">
      <div class="welcome-icon">⚡</div>
      <h2>Hola, soy Alex</h2>
      <p>Tu asistente operativo. ¿En qué trabajamos hoy?</p>
      <div class="chips">
        <button class="chip" onclick="prefill('¿Qué puedes hacer?')">¿Qué puedes hacer?</button>
        <button class="chip" onclick="prefill('¿Qué día es hoy?')">Fecha de hoy</button>
        <button class="chip" onclick="prefill('Lista los archivos del workspace')">Ver workspace</button>
        <button class="chip" onclick="prefill('Crea una nota con mis tareas pendientes de esta semana')">Crear nota</button>
      </div>
    </div>`;
}

function newChat() { startNewChat(); }

function prefill(text) {
  const input = document.getElementById('msg-input');
  input.value = text;
  resize(input);
  sendMessage();
}

// ─── Input ───────────────────────────────────────────────────────────────────

function resize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 200) + 'px';
}

function onKey(e) {
  if (e.key !== 'Enter' || e.shiftKey) return;
  var ta = e.target;
  var pos = ta.selectionStart;
  var text = ta.value;
  var lineStart = text.lastIndexOf('\n', pos - 1) + 1;
  var line = text.substring(lineStart, pos);
  var m = line.match(/^(\d+)\.\s/);
  if (!m) return;
  if (line.trim() === m[0].trim()) {
    e.preventDefault();
    ta.value = text.substring(0, lineStart) + text.substring(pos);
    ta.selectionStart = ta.selectionEnd = lineStart;
    resize(ta);
    return;
  }
  e.preventDefault();
  var next = '\n' + (parseInt(m[1]) + 1) + '. ';
  ta.value = text.substring(0, pos) + next + text.substring(pos);
  ta.selectionStart = ta.selectionEnd = pos + next.length;
  resize(ta);
}

// ─── File upload ─────────────────────────────────────────────────────────────

async function pickFile() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/*,.pdf,.txt,.md,.csv';
  input.onchange = async function() {
    const file = input.files[0];
    if (!file) return;
    const preview = document.getElementById('attach-preview');
    preview.innerHTML = `<span class="attach-name">📎 ${esc(file.name)}</span><span class="attach-loading">Subiendo…</span>`;
    preview.classList.remove('hidden');
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await fetch('/api/upload', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: fd,
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      pendingFile = await r.json();
      preview.innerHTML = `<span class="attach-name">📎 ${esc(pendingFile.filename)}</span><button class="attach-del" onclick="clearAttachment()">✕</button>`;
    } catch (e) {
      preview.innerHTML = `<span class="attach-err">Error al subir: ${esc(e.message)}</span><button class="attach-del" onclick="clearAttachment()">✕</button>`;
      pendingFile = null;
    }
  };
  input.click();
}

function clearAttachment() {
  pendingFile = null;
  const preview = document.getElementById('attach-preview');
  preview.classList.add('hidden');
  preview.innerHTML = '';
}

// ─── Chat ────────────────────────────────────────────────────────────────────

async function sendMessage() {
  if (busy) return;
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text && !pendingFile) return;

  const msgText = text || ('[Archivo: ' + (pendingFile ? pendingFile.filename : '') + ']');
  input.value = '';
  resize(input);
  var welcome = document.querySelector('.welcome');
  if (welcome) welcome.remove();

  history.push({ role: 'user', content: msgText });
  appendUserMsg(msgText, true, pendingFile);

  const filePayload = pendingFile ? Object.assign({}, pendingFile) : null;
  clearAttachment();

  busy = true;
  setDisabled(true);
  setStatus('loading');

  const bubble = appendAssistantBubble();
  let responseText = '';

  try {
    const contextMessages = history.slice(-16);
    const body = { messages: contextMessages, ...currentScope };
    if (filePayload) {
      body.file_id = filePayload.file_id;
      body.filename = filePayload.filename;
      body.mime_type = filePayload.mime_type;
    }
    const res = await fetch(API + '/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + token },
      body: JSON.stringify(body),
    });

    if (res.status === 401) { logout(); return; }
    if (!res.ok) throw new Error('HTTP ' + res.status);

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';

    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buf += dec.decode(chunk.value, { stream: true });
      const parts = buf.split('\n\n');
      buf = parts.pop();

      for (let i = 0; i < parts.length; i++) {
        const line = parts[i].trim();
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;
        let ev;
        try { ev = JSON.parse(raw); } catch (_) { continue; }

        if (ev.type === 'text') {
          responseText += ev.content;
          bubble._rawText = responseText;
          bubble.classList.remove('cursor');
          bubble.innerHTML = renderMd(responseText);
          bubble.classList.add('cursor');
          scrollBottom();
        } else if (ev.type === 'tool_start') {
          addTool(bubble.parentElement.querySelector('.tools'), ev.name, 'running');
        } else if (ev.type === 'tool_done') {
          doneTool(bubble.parentElement.querySelector('.tools'), ev.name);
        } else if (ev.type === 'done') {
          bubble.classList.remove('cursor');
          if (ev.workspace_id) {
            currentScope = { workspace_id: ev.workspace_id, project_id: ev.project_id || null, scope_source: currentScope.scope_source };
            renderChatScope(currentScope);
          }
        } else if (ev.type === 'error') {
          bubble.classList.remove('cursor');
          bubble.innerHTML = '<span class="err">Error: ' + esc(ev.message) + '</span>';
        }
      }
    }

    bubble.classList.remove('cursor');
    if (responseText) {
      history.push({ role: 'assistant', content: responseText });
      await saveCurrentChat();
    }

  } catch (err) {
    bubble.classList.remove('cursor');
    bubble.innerHTML = '<span class="err">' + esc(err.message) + '</span>';
  } finally {
    busy = false;
    setDisabled(false);
    setStatus('ready');
  }
}

// ─── UI helpers ──────────────────────────────────────────────────────────────

function appendUserMsg(text, scroll, file) {
  if (scroll === undefined) scroll = true;
  if (file === undefined) file = null;
  const msgs = document.getElementById('messages');
  const el = document.createElement('div');
  el.className = 'msg user';
  const fileBadge = file ? '<div class="file-badge">📎 ' + esc(file.filename) + '</div>' : '';
  el.innerHTML = '<div class="avatar user-av">J</div><div class="bubble user-bubble">' + fileBadge + esc(text) + '</div>';
  msgs.appendChild(el);
  if (scroll) scrollBottom();
}

function appendAssistantBubble() {
  const msgs = document.getElementById('messages');
  const el = document.createElement('div');
  el.className = 'msg assistant';
  el.innerHTML =
    '<div class="avatar alex-av">⚡</div>' +
    '<div class="msg-body">' +
      '<div class="bubble alex-bubble cursor"></div>' +
      '<div class="tools"></div>' +
      '<div class="msg-actions">' +
        '<button class="copy-btn" onclick="copyBubble(this)" title="Copiar mensaje">' +
          '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>' +
          ' Copiar' +
        '</button>' +
      '</div>' +
    '</div>';
  msgs.appendChild(el);
  scrollBottom();
  return el.querySelector('.bubble');
}

function copyBubble(btn) {
  const bubble = btn.closest('.msg-body').querySelector('.bubble');
  const text = bubble._rawText || bubble.innerText;
  navigator.clipboard.writeText(text).then(function() {
    btn.textContent = '✓ Copiado';
    setTimeout(function() {
      btn.innerHTML =
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg> Copiar';
    }, 1500);
  });
}

function addTool(container, name, state) {
  const el = document.createElement('div');
  el.className = 'tool ' + state;
  el.dataset.tool = name;
  el.innerHTML = '<span class="tool-icon">' + (state === 'running' ? '⚙' : '✓') + '</span> ' + esc(name);
  container.appendChild(el);
  scrollBottom();
}

function doneTool(container, name) {
  if (!container) return;
  const el = container.querySelector('[data-tool="' + name + '"]');
  if (el) { el.className = 'tool done'; el.innerHTML = '<span class="tool-icon">✓</span> ' + esc(name); }
}

function setDisabled(v) { document.getElementById('send-btn').disabled = v; }

function setStatus(state) {
  document.getElementById('status-dot').className = state === 'loading' ? 'dot loading' : 'dot';
}

function scrollBottom() { var c = document.getElementById('chat'); c.scrollTop = c.scrollHeight; }

function esc(t) {
  return String(t)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderMd(text) {
  const parts = text.split(/(```[\w]*\n[\s\S]*?```)/g);
  return parts.map(function(part, i) {
    if (i % 2 === 1) {
      const code = part.replace(/^```[\w]*\n/, '').replace(/\n?```$/, '');
      return '<pre><code>' + esc(code) + '</code></pre>';
    }
    let h = esc(part);
    h = h.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    h = h.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
    h = h.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
    h = h.replace(/\n/g, '<br>');
    return h;
  }).join('');
}

// ─── Bootstrap ───────────────────────────────────────────────────────────────

document.getElementById('username-input').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') document.getElementById('password-input').focus();
});
document.getElementById('password-input').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') login();
});

init();

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(function() {});
}

function toggleSection(title) {
  title.closest('.admin-section').classList.toggle('collapsed');
}

// ─── Admin panel ─────────────────────────────────────────────────────────────

function openAdmin() {
  document.getElementById('admin-overlay').classList.remove('hidden');
  document.getElementById('admin-panel').classList.remove('hidden');
  requestAnimationFrame(function() { document.getElementById('admin-panel').classList.add('open'); });
  loadAdminData();
  updatePushUI();
}

function closeAdmin() {
  const panel = document.getElementById('admin-panel');
  panel.classList.remove('open');
  setTimeout(function() {
    panel.classList.add('hidden');
    document.getElementById('admin-overlay').classList.add('hidden');
  }, 250);
}

async function adminFetch(path) {
  const r = await fetch(path, { headers: { Authorization: 'Bearer ' + token } });
  return r.json();
}

async function loadAdminData() { loadStats(); loadContainers(); loadTasks(); loadWA(); loadTelegramStatus(); }

async function loadStats() {
  try {
    const d = await adminFetch('/api/admin/stats');
    document.getElementById('s-disk').textContent = d.disk || '—';
    document.getElementById('s-mem').textContent = d.memory || '—';
    document.getElementById('s-load').textContent = d.load || '—';
    document.getElementById('s-uptime').textContent = d.uptime || '—';
  } catch (_) { document.getElementById('s-disk').textContent = 'error'; }
}

async function loadContainers() {
  const el = document.getElementById('admin-containers');
  try {
    const d = await adminFetch('/api/admin/containers');
    if (d.error) { el.innerHTML = '<p class="no-items" style="color:var(--err)">' + esc(d.error) + '</p>'; return; }
    if (!d.containers.length) { el.innerHTML = '<p class="no-items">Sin contenedores</p>'; return; }
    el.innerHTML = d.containers.map(function(c) {
      return '<div class="container-row">' +
        '<span class="container-name">' + esc(c.name) + '</span>' +
        '<span class="container-status ' + (c.up ? 'status-up' : 'status-down') + '">' + (c.up ? '● Activo' : '● Parado') + '</span>' +
        '</div>';
    }).join('');
  } catch (_) { el.innerHTML = '<p class="no-items">Error al cargar</p>'; }
}

async function loadTasks() {
  const el = document.getElementById('admin-tasks');
  try {
    const d = await adminFetch('/api/admin/tasks');
    if (!d.tasks.length) { el.innerHTML = '<p class="no-items">No hay tareas programadas</p>'; return; }
    el.innerHTML = d.tasks.map(function(t) {
      const sched = t.schedule_type === 'cron'
        ? 'Cron: ' + JSON.stringify(t.schedule_params)
        : 'Cada: ' + JSON.stringify(t.schedule_params);
      return '<div class="task-row">' +
        '<div class="task-info">' +
          '<div class="task-name">' + esc(t.name) + '</div>' +
          '<div class="task-schedule">' + esc(sched) + '</div>' +
        '</div>' +
        '<div class="task-actions">' +
          '<button class="task-btn" onclick="toggleTask(\'' + t.id + '\',' + (!t.enabled) + ')">' + (t.enabled ? 'Pausar' : 'Activar') + '</button>' +
          '<button class="task-btn danger" onclick="deleteTask(\'' + t.id + '\')">✕</button>' +
        '</div>' +
        '</div>';
    }).join('');
  } catch (_) { el.innerHTML = '<p class="no-items">Error al cargar</p>'; }
}

async function toggleTask(id, enabled) {
  await fetch('/api/admin/tasks/' + id, {
    method: 'PATCH',
    headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: enabled }),
  });
  loadTasks();
}

async function deleteTask(id) {
  if (!confirm('¿Eliminar esta tarea?')) return;
  await fetch('/api/admin/tasks/' + id, { method: 'DELETE', headers: { Authorization: 'Bearer ' + token } });
  loadTasks();
}

// ─── Telegram ────────────────────────────────────────────────────────────────

async function loadTelegramStatus() {
  var el = document.getElementById('tg-status');
  var testWrap = document.getElementById('tg-test-wrap');
  if (!el) return;
  try {
    var d = await adminFetch('/api/telegram/status');
    if (d.error) {
      el.innerHTML = '<span style="color:var(--err)">' + esc(d.error) + '</span>';
      return;
    }
    if (!d.token_set) {
      el.innerHTML = '<span style="color:var(--err)">● TELEGRAM_BOT_TOKEN no configurado en .env</span>';
      if (testWrap) testWrap.style.display = 'none';
    } else if (!d.chat_id) {
      el.innerHTML = '<span style="color:var(--muted)">● Token OK — falta TELEGRAM_CHAT_ID</span><br><small style="font-size:11px">Envía un mensaje a @JLclaw13_bot y pulsa "Detectar Chat ID"</small>';
      if (testWrap) testWrap.style.display = 'none';
    } else {
      el.innerHTML = '<span style="color:var(--green)">● Conectado — chat_id: ' + esc(d.chat_id) + '</span>';
      if (testWrap) testWrap.style.display = '';
    }
  } catch (_) {
    el.textContent = 'Error al cargar estado de Telegram';
  }
}

async function detectTelegramChat() {
  var el = document.getElementById('tg-status');
  if (el) el.textContent = 'Detectando…';
  try {
    var d = await adminFetch('/api/telegram/detect-chat');
    if (d.error) {
      if (el) el.innerHTML = '<span style="color:var(--err)">' + esc(d.error) + '</span>';
    } else {
      if (el) el.innerHTML = '<span style="color:var(--green)">● chat_id detectado: ' + esc(d.chat_id) + (d.name ? ' (' + esc(d.name) + ')' : '') + '</span><br><small style="font-size:11px;color:var(--muted)">Añade TELEGRAM_CHAT_ID=' + esc(d.chat_id) + ' al .env y reinicia</small>';
    }
  } catch (_) {
    if (el) el.textContent = 'Error al detectar';
  }
}

async function testTelegram() {
  try {
    var d = await fetch('/api/telegram/test', { method: 'POST', headers: { Authorization: 'Bearer ' + token } }).then(function(r) { return r.json(); });
    if (d.ok) alert('Mensaje enviado por Telegram.');
    else alert('Error: ' + (d.error || JSON.stringify(d)));
  } catch (e) {
    alert('Error: ' + e.message);
  }
}

// ─── Push notifications ───────────────────────────────────────────────────────

async function initPush() {
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
  try {
    const reg = await navigator.serviceWorker.ready;
    pushSub = await reg.pushManager.getSubscription();
  } catch (_) { /* ignore */ }
}

function updatePushUI() {
  const status = document.getElementById('push-status');
  const btn = document.getElementById('push-btn');
  const testWrap = document.getElementById('push-test-wrap');
  if (!status) return;
  if (!('PushManager' in window)) {
    status.textContent = 'No soportado en este navegador';
    if (btn) btn.style.display = 'none';
    return;
  }
  if (pushSub) {
    status.innerHTML = '<span style="color:var(--green)">● Notificaciones activadas</span>';
    if (btn) btn.textContent = 'Desactivar notificaciones';
    if (testWrap) testWrap.style.display = '';
  } else {
    status.innerHTML = '<span style="color:var(--muted)">○ Notificaciones desactivadas</span>';
    if (btn) btn.textContent = 'Activar notificaciones';
    if (testWrap) testWrap.style.display = 'none';
  }
}

function _urlBase64ToUint8Array(b64) {
  const pad = '='.repeat((4 - b64.length % 4) % 4);
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

async function togglePush() {
  if (pushSub) {
    await pushSub.unsubscribe();
    pushSub = null;
    updatePushUI();
    return;
  }
  try {
    const data = await adminFetch('/api/push/vapid-key');
    const reg = await navigator.serviceWorker.ready;
    pushSub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: _urlBase64ToUint8Array(data.public_key),
    });
    await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify(pushSub.toJSON()),
    });
    updatePushUI();
  } catch (e) {
    alert('Error al activar notificaciones: ' + e.message);
  }
}

async function testPush() {
  await fetch('/api/push/test', { method: 'POST', headers: { Authorization: 'Bearer ' + token } });
}

async function doDeploy() {
  const btn = document.querySelector('.deploy-btn');
  const msg = document.getElementById('deploy-msg');
  btn.disabled = true;
  btn.textContent = 'Iniciando…';
  try {
    const d = await fetch('/api/admin/deploy', {
      method: 'POST', headers: { Authorization: 'Bearer ' + token },
    }).then(function(r) { return r.json(); });
    msg.textContent = d.message;
    btn.textContent = '✓ Deploy iniciado';
  } catch (_) {
    btn.disabled = false;
    btn.textContent = '↑ Actualizar a la última versión';
    msg.textContent = 'Error al iniciar deploy';
  }
}
