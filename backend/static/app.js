const API = '';
let token = localStorage.getItem('oc_token') || '';
let history = [];
let busy = false;
let currentChatId = null;
let pendingFile = null; // { file_id, filename, mime_type, size }
let pushSub = null;
let nextAssistContext = null;
let mediaRecorder = null;
let recordingStream = null;
let audioChunks = [];
let speakAfterReply = false;
let activeSpeech = null;
let voicePressTimer = null;
let voiceHoldActive = false;
let voiceReleasePending = false;
let voiceCancelPending = false;
let voiceStartPoint = null;
let voiceStartRequest = 0;

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
  initVoiceControls();
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
let openChatMenuId = null;
let movingChatId = null;
let renamingChatId = null;
let collapsedSpaces = new Set(JSON.parse(localStorage.getItem('oc_collapsed_spaces') || '[]'));
let unreadReplyChatIds = new Set(JSON.parse(localStorage.getItem('oc_unread_replies') || '[]'));

function setUnreadReply(chatId, unread) {
  if (unread) unreadReplyChatIds.add(chatId); else unreadReplyChatIds.delete(chatId);
  localStorage.setItem('oc_unread_replies', JSON.stringify([...unreadReplyChatIds]));
}

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
    const editing = c.id === renamingChatId;
    const menuOpen = c.id === openChatMenuId;
    const unread = unreadReplyChatIds.has(c.id) && c.id !== currentChatId;
    const orderPeers = chatList.filter(item => item.workspace_id === c.workspace_id && item.project_id === c.project_id);
    const orderIndex = orderPeers.findIndex(item => item.id === c.id);
    return `<div class="chat-item ${active}" onclick="loadChat('${c.id}')">
      <div class="chat-item-top">
        ${editing
          ? `<input class="chat-item-title-input" id="chat-title-input-${c.id}" value="${esc(c.title)}" maxlength="120" onclick="event.stopPropagation()" onkeydown="onRenameKey(event, '${c.id}')" onblur="saveInlineRename('${c.id}')">`
          : `<span class="chat-item-title">${esc(c.title)}</span>${unread ? '<span class="chat-item-reply-dot" aria-label="Respuesta nueva" title="Respuesta nueva"></span>' : ''}`}
        <span class="chat-item-date">${date}</span>
      </div>
      ${c.preview ? `<div class="chat-item-preview">${esc(c.preview)}</div>` : ''}
      <button class="chat-item-more" onclick="toggleChatMenu(event, '${c.id}')" aria-label="Opciones de conversación" aria-expanded="${menuOpen}">⋯</button>
      ${menuOpen ? `<div class="chat-action-menu" onclick="event.stopPropagation()">${movingChatId === c.id
        ? `<div class="chat-action-menu-title">Mover a…</div>
           <button onclick="moveChat('${c.id}', 'general', null)">💬 General</button>
           <button onclick="moveChat('${c.id}', 'hornbills', null)">🏀 Hornbills</button>
           <button onclick="moveChat('${c.id}', 'english', null)">🇬🇧 English</button>
           <div class="chat-action-menu-title">Proyectos</div>
           ${projectList.map(p => `<button onclick="moveChat('${c.id}', 'projects', '${p.id}')">🚀 ${esc(p.name)}</button>`).join('')}
           <button class="chat-menu-back" onclick="showChatActions('${c.id}')">‹ Volver</button>`
        : `<div class="chat-action-menu-title">Orden</div>
           <button onclick="reorderChat('${c.id}', -1)" ${orderIndex === 0 ? 'disabled' : ''}>↑ Subir</button>
           <button onclick="reorderChat('${c.id}', 1)" ${orderIndex === orderPeers.length - 1 ? 'disabled' : ''}>↓ Bajar</button>
           <button onclick="showMoveChoices('${c.id}')">Mover a…</button>
           <button onclick="beginRenameChat('${c.id}')">Renombrar</button>
           <button class="danger" onclick="deleteChat(event,'${c.id}')">Eliminar</button>`}
      </div>` : ''}
    </div>`;
  };
  const inScope = (workspaceId, projectId = null) => chatList.filter(c =>
    c.workspace_id === workspaceId && (projectId ? c.project_id === projectId : !c.project_id)
  );
  const section = (label, items, workspaceId, projectId = null, depth = '', key = workspaceId + (projectId ? `:${projectId}` : '')) => {
    const collapsed = collapsedSpaces.has(key);
    return `<section class="space-section ${depth} ${collapsed ? 'collapsed' : ''}">
      <div class="space-label">
        <button class="space-collapse" onclick="toggleSpace(event, '${key}')" aria-expanded="${!collapsed}" title="Plegar o desplegar">${collapsed ? '›' : '⌄'}</button>
        <button class="space-name" onclick="toggleSpace(event, '${key}')">${label}</button>
        <button class="space-new" onclick="startNewChat('${workspaceId}', ${projectId ? `'${projectId}'` : 'null'})" title="Nueva conversación aquí">＋</button>
      </div>
      <div class="space-chats">${items.length ? items.map(chat).join('') : '<div class="space-empty">Sin conversaciones</div>'}</div>
    </section>`;
  };
  const spaces = workspaceList.map(w => {
    if (w.id !== 'projects') return section(`${w.icon} ${esc(w.name)}`, inScope(w.id), w.id);
    const projectSections = projectList.map(p => section(esc(p.name), inScope('projects', p.id), 'projects', p.id, 'project')).join('');
    const direct = inScope('projects');
    const collapsed = collapsedSpaces.has('projects');
    return `<section class="space-section projects ${collapsed ? 'collapsed' : ''}">
      <div class="space-label">
        <button class="space-collapse" onclick="toggleSpace(event, 'projects')" aria-expanded="${!collapsed}" title="Plegar o desplegar">${collapsed ? '›' : '⌄'}</button>
        <button class="space-name" onclick="toggleSpace(event, 'projects')">${w.icon} ${esc(w.name)}</button>
        <button class="space-new" onclick="startNewChat('projects', null)" title="Nueva conversación aquí">＋</button>
      </div>
      <div class="space-chats">${direct.length ? direct.map(chat).join('') : ''}${projectSections}</div>
    </section>`;
  }).join('');
  // A conversation belongs to exactly one workspace. Do not duplicate recent
  // conversations at the top of the sidebar: that made scoped chats look like
  // General chats and obscured where they were actually saved.
  el.innerHTML = spaces;
  if (renamingChatId) {
    const input = document.getElementById(`chat-title-input-${renamingChatId}`);
    if (input) { input.focus(); input.select(); }
  }
}

function toggleSpace(e, key) {
  e.stopPropagation();
  if (collapsedSpaces.has(key)) collapsedSpaces.delete(key); else collapsedSpaces.add(key);
  localStorage.setItem('oc_collapsed_spaces', JSON.stringify([...collapsedSpaces]));
  renderChatList();
}

function toggleChatMenu(e, id) {
  e.stopPropagation();
  openChatMenuId = openChatMenuId === id ? null : id;
  movingChatId = null;
  renderChatList();
}

function showMoveChoices(id) {
  movingChatId = id;
  renderChatList();
}

function showChatActions(id) {
  movingChatId = null;
  openChatMenuId = id;
  renderChatList();
}

async function moveChat(id, workspaceId, projectId) {
  try {
    const r = await fetch(`/api/chats/${id}`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: workspaceId, project_id: projectId, scope_source: 'manual' }),
    });
    if (!r.ok) throw new Error('No se pudo mover');
    chatList = chatList.map(c => c.id === id ? { ...c, workspace_id: workspaceId, project_id: projectId, scope_source: 'manual', updated: new Date().toISOString() } : c);
    if (currentChatId === id) {
      currentScope = { workspace_id: workspaceId, project_id: projectId, scope_source: 'manual' };
      renderChatScope(currentScope);
    }
    openChatMenuId = null;
    movingChatId = null;
    renderChatList();
  } catch (_) { alert('No se pudo mover la conversación.'); }
}

async function reorderChat(id, direction) {
  const chat = chatList.find(item => item.id === id);
  if (!chat) return;
  const peers = chatList.filter(item =>
    item.workspace_id === chat.workspace_id && item.project_id === chat.project_id
  );
  const index = peers.findIndex(item => item.id === id);
  const target = index + direction;
  if (target < 0 || target >= peers.length) return;

  [peers[index], peers[target]] = [peers[target], peers[index]];
  try {
    const r = await fetch('/api/chats/order', {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ ordered_ids: peers.map(item => item.id) }),
    });
    if (!r.ok) throw new Error('No se pudo guardar el orden');

    const listResponse = await fetch('/api/chats', { headers: { Authorization: `Bearer ${token}` } });
    const data = await listResponse.json();
    chatList = data.chats || [];
    openChatMenuId = null;
    renderChatList();
  } catch (_) {
    alert('No se pudo guardar el orden de las conversaciones.');
  }
}

function openNewChatPicker() {
  const el = document.getElementById('new-chat-picker');
  if (!el.classList.contains('hidden')) { el.classList.add('hidden'); return; }
  const spaces = workspaceList.filter(w => w.id !== 'projects').map(w =>
    `<button onclick="startNewChat('${w.id}')"><span>${w.icon}</span>${esc(w.name)}</button>`
  ).join('');
  const projects = projectList.map(p =>
    `<button onclick="startNewChat('projects','${p.id}')"><span>🚀</span>${esc(p.name)}</button>`
  ).join('');
  el.innerHTML = `<div class="new-chat-picker-title">Nueva conversación en…</div>${spaces}<div class="new-chat-picker-divider">Projects</div>${projects}`;
  el.classList.remove('hidden');
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
  document.getElementById('new-chat-picker').classList.add('hidden');
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
    renderChatScope(currentScope);
    renderChatHeader(chat);
    showWelcome();
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
    setUnreadReply(id, false);
    history = chat.messages || [];
    currentScope = { workspace_id: chat.workspace_id || 'general', project_id: chat.project_id || null, scope_source: chat.scope_source || 'auto' };
    renderMessages();
    renderChatList();
    renderChatScope(currentScope);
    renderChatHeader(chat);
    closeSidebar();
    scrollBottom();
    document.getElementById('msg-input').focus();
  } catch (_) { /* ignore */ }
}

async function deleteChat(e, id) {
  e.stopPropagation();
  const chat = chatList.find(c => c.id === id);
  if (!window.confirm(`¿Eliminar “${chat ? chat.title : 'esta conversación'}”? Esta acción no se puede deshacer.`)) return;
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

function beginRenameChat(id) {
  openChatMenuId = null;
  renamingChatId = id;
  renderChatList();
}

function onRenameKey(e, id) {
  if (e.key === 'Enter') { e.preventDefault(); e.target.blur(); }
  if (e.key === 'Escape') { renamingChatId = null; renderChatList(); }
}

async function saveInlineRename(id) {
  if (renamingChatId !== id) return;
  const input = document.getElementById(`chat-title-input-${id}`);
  const title = input ? input.value.trim() : '';
  renamingChatId = null;
  if (!title) { renderChatList(); return; }
  const chat = chatList.find(c => c.id === id);
  try {
    const r = await fetch(`/api/chats/${id}/title`, {
      method: 'PATCH',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    if (!r.ok) throw new Error('No se pudo cambiar el nombre');
    chatList = chatList.map(c => c.id === id ? { ...c, title, updated: new Date().toISOString() } : c);
    renderChatList();
    if (currentChatId === id) renderChatHeader();
  } catch (_) {
    alert('No se pudo cambiar el nombre de la conversación.');
  }
}

async function saveCurrentChat() {
  return saveChatSnapshot(currentChatId, history, currentScope);
}

async function saveChatSnapshot(chatId, messages, scope) {
  if (!chatId) return;
  try {
    await fetch(`/api/chats/${chatId}`, {
      method: 'PUT',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages, ...scope }),
    });
    const r = await fetch('/api/chats', { headers: { Authorization: `Bearer ${token}` } });
    chatList = (await r.json()).chats || [];
    renderChatList();
    if (currentChatId === chatId) renderChatHeader();
  } catch (_) { /* ignore */ }
}

function scopeName(scope) {
  const workspace = workspaceList.find(w => w.id === scope.workspace_id);
  const project = projectList.find(p => p.id === scope.project_id);
  return project ? `Projects · ${project.name}` : (workspace ? workspace.name : 'General');
}

function renderChatScope(scope = currentScope) {
  const el = document.getElementById('chat-title-hdr');
  if (el) el.textContent = scopeName(scope);
  renderChatHeader();
}

function renderChatHeader(chat = null) {
  const el = document.getElementById('app-title');
  const activeChat = chat || chatList.find(c => c.id === currentChatId);
  const title = activeChat?.title || 'Nueva conversación';
  if (el) {
    el.textContent = `Alex - ${title}`;
    el.title = title;
  }
  document.title = `Alex - ${title}`;
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

function prefill(text, assistContext = null) {
  const input = document.getElementById('msg-input');
  input.value = text;
  nextAssistContext = assistContext;
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
  e.preventDefault();
  sendMessage();
}

// ─── Voice dictation ────────────────────────────────────────────────────────

function setVoiceStatus(message = '', error = false) {
  const status = document.getElementById('voice-status');
  status.textContent = message;
  status.classList.toggle('hidden', !message);
  status.classList.toggle('error', error);
}

function setVoiceButton(recording = false, working = false) {
  const button = document.getElementById('voice-btn');
  button.classList.toggle('recording', recording);
  button.classList.toggle('working', working);
  button.disabled = working;
  button.title = recording ? 'Grabando…' : (working ? 'Transcribiendo…' : 'Toca para dictar · Mantén para hablar con Alex');
  button.setAttribute('aria-label', button.title);
}

function initVoiceControls() {
  const button = document.getElementById('voice-btn');
  if (!button || button.dataset.voiceBound) return;
  button.dataset.voiceBound = 'true';
  button.addEventListener('pointerdown', onVoicePointerDown);
  button.addEventListener('pointermove', onVoicePointerMove);
  button.addEventListener('pointerup', onVoicePointerUp);
  button.addEventListener('pointercancel', onVoicePointerCancel);
}

function isRecordingVoice() {
  return mediaRecorder && mediaRecorder.state === 'recording';
}

function onVoicePointerDown(event) {
  if (event.button !== undefined && event.button !== 0) return;
  const button = event.currentTarget;
  if (button.disabled) return;
  event.preventDefault();
  button.setPointerCapture?.(event.pointerId);
  voiceStartPoint = { x: event.clientX, y: event.clientY };
  voiceCancelPending = false;
  voiceReleasePending = false;

  if (isRecordingVoice()) {
    voiceHoldActive = true;
    return;
  }

  voiceHoldActive = false;
  voicePressTimer = window.setTimeout(() => {
    voicePressTimer = null;
    voiceHoldActive = true;
    startVoiceRecording(true);
  }, 350);
}

function onVoicePointerMove(event) {
  if (!voiceHoldActive || !voiceStartPoint) return;
  const distance = Math.hypot(event.clientX - voiceStartPoint.x, event.clientY - voiceStartPoint.y);
  if (distance > 64 && !voiceCancelPending) {
    voiceCancelPending = true;
    setVoiceStatus('Suelta para cancelar el mensaje de voz.');
  }
}

function resetVoicePress() {
  if (voicePressTimer) window.clearTimeout(voicePressTimer);
  voicePressTimer = null;
  voiceHoldActive = false;
  voiceStartPoint = null;
}

function onVoicePointerUp(event) {
  event.preventDefault();
  const wasHold = voiceHoldActive;
  resetVoicePress();
  if (!wasHold) {
    toggleVoiceRecording();
    return;
  }
  voiceReleasePending = true;
  if (voiceCancelPending) {
    cancelVoiceRecording();
  } else if (isRecordingVoice()) {
    mediaRecorder.stop();
  }
}

function onVoicePointerCancel(event) {
  event.preventDefault();
  const wasHold = voiceHoldActive;
  resetVoicePress();
  if (wasHold) {
    voiceCancelPending = true;
    cancelVoiceRecording();
  }
}

async function toggleVoiceRecording() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
    return;
  }
  await startVoiceRecording(false);
}

async function startVoiceRecording(sendAutomatically) {
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    setVoiceStatus('La grabación no está disponible en este navegador.', true);
    return;
  }
  try {
    const requestId = ++voiceStartRequest;
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (requestId !== voiceStartRequest) {
      stream.getTracks().forEach(track => track.stop());
      return;
    }
    recordingStream = stream;
    audioChunks = [];
    const preferredType = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm']
      .find(type => MediaRecorder.isTypeSupported(type));
    const recorder = preferredType ? new MediaRecorder(recordingStream, { mimeType: preferredType }) : new MediaRecorder(recordingStream);
    recorder.ondataavailable = event => { if (event.data.size) audioChunks.push(event.data); };
    recorder.onstop = () => transcribeRecording(sendAutomatically);
    mediaRecorder = recorder;
    recorder.start();
    setVoiceButton(true);
    setVoiceStatus(sendAutomatically
      ? '● Escuchando… Suelta para enviar · desliza para cancelar.'
      : '● Escuchando… Toca otra vez al terminar.');
    if (sendAutomatically && voiceReleasePending) {
      if (voiceCancelPending) cancelVoiceRecording();
      else recorder.stop();
    }
  } catch (error) {
    const denied = error && error.name === 'NotAllowedError';
    setVoiceStatus(denied ? 'Necesitas permitir el micrófono para dictar.' : 'No se ha podido iniciar el micrófono.', true);
    stopRecordingTracks();
  }
}

function cancelVoiceRecording() {
  voiceStartRequest += 1;
  voiceReleasePending = false;
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    const recorder = mediaRecorder;
    recorder.onstop = () => {
      if (mediaRecorder === recorder) mediaRecorder = null;
      audioChunks = [];
      stopRecordingTracks();
      setVoiceButton();
      setVoiceStatus('Mensaje de voz cancelado.');
    };
    recorder.stop();
    return;
  }
  audioChunks = [];
  stopRecordingTracks();
  setVoiceButton();
  setVoiceStatus('Mensaje de voz cancelado.');
}

function stopRecordingTracks() {
  if (recordingStream) recordingStream.getTracks().forEach(track => track.stop());
  recordingStream = null;
}

async function transcribeRecording(sendAutomatically = false) {
  const type = mediaRecorder && mediaRecorder.mimeType ? mediaRecorder.mimeType : 'audio/webm';
  const extension = type.includes('mp4') ? 'm4a' : 'webm';
  const audio = new Blob(audioChunks, { type });
  mediaRecorder = null;
  audioChunks = [];
  stopRecordingTracks();
  if (!audio.size) { setVoiceButton(); setVoiceStatus('No se ha grabado audio.', true); return; }

  setVoiceButton(false, true);
  setVoiceStatus('Transcribiendo…');
  try {
    const data = new FormData();
    data.append('file', audio, `nota-de-voz.${extension}`);
    const response = await fetch('/api/transcribe', {
      method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: data,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'No se pudo transcribir');
    const input = document.getElementById('msg-input');
    input.value = [input.value.trim(), result.text].filter(Boolean).join(input.value.trim() ? ' ' : '');
    resize(input);
    input.focus();
    if (sendAutomatically) {
      speakAfterReply = true;
      setVoiceStatus('Enviando a Alex…');
      await sendMessage();
    } else {
      setVoiceStatus('Texto listo para revisar y enviar.');
    }
  } catch (error) {
    setVoiceStatus(error.message || 'No se pudo transcribir el audio.', true);
  } finally {
    setVoiceButton();
  }
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

  // A reply may finish after the user has opened another conversation. Keep it
  // attached to the conversation that started it, then mark it as unread.
  const responseChatId = currentChatId;
  const responseHistory = history;
  let responseScope = { ...currentScope };

  const msgText = text || ('[Archivo: ' + (pendingFile ? pendingFile.filename : '') + ']');
  input.value = '';
  resize(input);
  var welcome = document.querySelector('.welcome');
  if (welcome) welcome.remove();

  responseHistory.push({ role: 'user', content: msgText });
  document.querySelectorAll('.context-shortcuts').forEach(el => el.remove());
  appendUserMsg(msgText, true, pendingFile);

  const filePayload = pendingFile ? Object.assign({}, pendingFile) : null;
  clearAttachment();

  busy = true;
  setDisabled(true);
  setStatus('loading');

  const bubble = appendAssistantBubble();
  let responseText = '';

  try {
    const contextMessages = responseHistory.slice(-16);
    const body = { messages: contextMessages, ...responseScope };
    if (nextAssistContext) body.assist_context = nextAssistContext;
    nextAssistContext = null;
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
            responseScope = { workspace_id: ev.workspace_id, project_id: ev.project_id || null, scope_source: responseScope.scope_source };
            if (currentChatId === responseChatId) currentScope = responseScope;
          }
        } else if (ev.type === 'error') {
          bubble.classList.remove('cursor');
          bubble.innerHTML = '<span class="err">Error: ' + esc(ev.message) + '</span>';
        }
      }
    }

    bubble.classList.remove('cursor');
    if (responseText) {
      responseHistory.push({ role: 'assistant', content: responseText });
      await saveChatSnapshot(responseChatId, responseHistory, responseScope);
      if (currentChatId === responseChatId) {
        renderContextShortcuts(msgText, responseText);
      } else {
        setUnreadReply(responseChatId, true);
        renderChatList();
      }
      const shouldSpeak = speakAfterReply;
      speakAfterReply = false;
      if (shouldSpeak && currentChatId === responseChatId) {
        const listenButton = bubble.parentElement.querySelector('.listen-btn');
        if (listenButton) speakBubble(listenButton);
      }
    }

  } catch (err) {
    speakAfterReply = false;
    bubble.classList.remove('cursor');
    bubble.innerHTML = '<span class="err">' + esc(err.message) + '</span>';
  } finally {
    busy = false;
    setDisabled(false);
    setStatus('ready');
  }
}

function hornbillsIntent(userText, responseText) {
  const recent = history.slice(-10).filter(m => m.role === 'user').map(m => m.content).join(' ') + ' ' + userText;
  const text = recent.toLowerCase();
  const score = patterns => patterns.reduce((total, pattern) => total + (text.match(pattern) || []).length, 0);
  const intents = {
    video: score([/vídeo|video|clip|análisis|analysis|spacing|motion|low post|high post|pnr|pick and roll/g]),
    player: score([/jugador|player|rol|role|desarrollo|development|strength|fortaleza|minutes|minutos|lesi[oó]n/g]),
    scouting: score([/rival|opponent|scouting|game plan|contra |\bvs\b|ato|blob|slob|weakness/g]),
    practice: score([/entrenamiento|training|práctica|practice|sesión|session|preseason|pretemporada/g]),
    decision: score([/césar|cesar|staff|head coach|reuni[oó]n|meeting|decisi[oó]n|proposal|propuesta/g]),
  };
  return Object.entries(intents).sort((a, b) => b[1] - a[1])[0][1] ? Object.entries(intents).sort((a, b) => b[1] - a[1])[0][0] : 'video';
}

function hornbillsActions(intent) {
  const actions = {
    video: [
      ['📊 Guardar análisis', 'Cierra esta revisión y guárdala como un análisis en Analysis Library. Separa hipótesis, preguntas y próximos pasos.'],
      ['🎯 Vincular a rival', 'Convierte estas observaciones en scouting del rival o del partido correspondiente.'],
      ['🇬🇧 Preparar para César', 'Ayúdame a formular para César, en inglés natural y oral, las preguntas que salen de esta revisión.', 'english'],
      ['🏋️ Llevar a práctica', 'Propón una práctica concreta a partir de estos hallazgos, sin crearla hasta que tenga fecha y objetivo claros.'],
    ],
    player: [
      ['🔒 Nota de jugador', 'Guarda esta evaluación como nota privada de jugador, con estado Needs Review.'],
      ['👤 Actualizar desarrollo', 'Si esta información está confirmada, actualiza el foco de desarrollo o perfil del jugador correspondiente.'],
      ['📊 Vincular análisis', 'Guarda esto como análisis de jugador y vincúlalo al jugador correspondiente.'],
      ['🇬🇧 Preparar feedback', 'Ayúdame a formular en inglés un feedback breve y constructivo para este jugador.', 'english'],
    ],
    scouting: [
      ['🎯 Guardar scouting', 'Crea o actualiza el registro de Games & Scouting correspondiente con estos patrones y prioridades.'],
      ['🛡️ Prioridades defensivas', 'Convierte esto en prioridades defensivas concretas para el game plan.'],
      ['🏀 Atacar debilidades', 'Extrae las debilidades a atacar y añádelas al scouting del rival.'],
      ['🇬🇧 Brief en inglés', 'Ayúdame a explicar este scouting en inglés claro y directo.', 'english'],
    ],
    practice: [
      ['🏋️ Crear sesión', 'Crea un borrador de Practice Session con objetivo principal, secundarios y estado Draft.'],
      ['🎯 Definir objetivos', 'Convierte esta conversación en objetivos principales y secundarios de práctica.'],
      ['👤 Vincular jugadores', 'Identifica los jugadores que deben vincularse a esta sesión y prepara la relación.'],
      ['🇬🇧 Explicar práctica', 'Ayúdame a explicar esta práctica en inglés claro y natural.', 'english'],
    ],
    decision: [
      ['🇬🇧 Preparar reunión', 'Ayúdame a preparar esto en inglés natural y directo.', 'english'],
      ['🧭 Preparar seguimiento', 'Convierte esto en una nota personal para Decisions & Meetings.'],
      ['✅ Registrar decisión', 'Si esta conversación contiene una decisión confirmada, regístrala en Decisions & Meetings.'],
      ['🔒 Guardar reflexión', 'Guarda esta reflexión como nota privada.'],
    ],
  };
  return actions[intent] || actions.video;
}

function renderContextShortcuts(userText, responseText) {
  if (currentScope.workspace_id === 'english') {
    renderEnglishShortcuts(userText, responseText);
    return;
  }
  if (currentScope.workspace_id === 'projects' && currentScope.project_id === 'cutsports') {
    renderCutSportsShortcuts(userText, responseText);
    return;
  }
  if (currentScope.workspace_id === 'projects' && currentScope.project_id === 'drawsports') {
    renderDrawSportsShortcuts(userText, responseText);
    return;
  }
  if (currentScope.workspace_id === 'projects' && currentScope.project_id === 'the-analyst') {
    renderTheAnalystShortcuts(userText, responseText);
    return;
  }
  if (currentScope.workspace_id === 'projects' && currentScope.project_id === 'comunidad') {
    renderComunidadShortcuts(userText, responseText);
    return;
  }
  if (currentScope.workspace_id === 'projects' && currentScope.project_id === 'basketouch-hub') {
    renderBasketouchHubShortcuts(userText, responseText);
    return;
  }
  if (currentScope.workspace_id !== 'hornbills') return;
  if (/sesión cerrada|sesion cerrada|guardad[oa] en notion/i.test(responseText)) return;
  const intent = hornbillsIntent(userText, responseText);
  const labels = { video: 'Vídeo y análisis', player: 'Jugador', scouting: 'Rival y scouting', practice: 'Entrenamiento', decision: 'Decisiones y reuniones' };
  const actions = hornbillsActions(intent);
  const el = document.createElement('div');
  el.className = 'context-shortcuts';
  el.innerHTML = `<span class="context-shortcuts-label">${labels[intent]} · ¿Qué hacemos con esto?</span>` + actions.map(([label, prompt, assist]) =>
    `<button class="context-shortcut" data-prompt="${esc(prompt)}" data-assist="${assist || ''}">${label}</button>`
  ).join('');
  el.addEventListener('click', e => {
    const prompt = e.target.dataset.prompt;
    if (prompt) prefill(prompt, e.target.dataset.assist || null);
  });
  document.getElementById('messages').appendChild(el);
  scrollBottom();
}

function renderCutSportsShortcuts(userText, responseText) {
  const text = (history.slice(-8).map(m => m.content).join(' ') + ' ' + userText).toLowerCase();
  const crm = /lead|cliente|club|entrenador|coach|contacto|email|demo|piloto|licencia/.test(text);
  const marketing = /marketing|campaña|campana|beta|copy|landing|contenido|reel|newsletter/.test(text);
  const release = /release|publicar|publicación|publicacion|build|appcast|web|dmg/.test(text);
  const actions = crm ? [
    ['👤 Registrar en CRM', 'Confirma que este contacto es un lead real y crea o actualiza el registro correspondiente en CRM — CutSports.'],
    ['📆 Definir próximo paso', 'Define el próximo paso y fecha de seguimiento para este lead, sin inventar información de contacto.'],
    ['✉️ Preparar mensaje', 'Redacta un mensaje breve y personalizado para este contacto.'],
    ['🔍 Revisar historial', 'Busca si ya existe este contacto o una oportunidad relacionada antes de crear nada.'],
  ] : marketing ? [
    ['📣 Convertir en propuesta', 'Estructura esta idea como propuesta de marketing de CutSports: objetivo, audiencia, mensaje y siguiente decisión.'],
    ['🧪 Llevar a BETA', 'Define cómo validar esta idea con los usuarios BETA antes de ejecutarla.'],
    ['✍️ Preparar copy', 'Escribe una primera versión de copy para esta idea con tono CutSports.'],
    ['📌 Guardar decisión', 'Si esta propuesta ya está aprobada, resume la decisión y el siguiente paso de ejecución.'],
  ] : release ? [
    ['📦 Preparar publicación', 'Convierte esto en una propuesta de nota para Pendiente de publicar, sin registrar una publicación como hecha.'],
    ['✅ Checklist de release', 'Prepara un checklist de verificación antes de publicar web o build Mac.'],
    ['🧭 Contrastar estado', 'Contrasta esta afirmación con Estado del Proyecto antes de darla por válida.'],
    ['📝 Crear backlog', 'Si hay trabajo pendiente para este release, crea o actualiza el ítem correspondiente en Backlog — CutSports.'],
  ] : [
    ['🛠️ Añadir al backlog', 'Comprueba duplicados y crea o actualiza este ítem en Backlog — CutSports con área, prioridad y notas concisas.'],
    ['🎯 Definir prioridad', 'Ayúdame a decidir el área y prioridad de este trabajo antes de guardarlo.'],
    ['🧭 Contrastar estado', 'Contrasta esta conversación con Estado del Proyecto y señala qué está verificado y qué es propuesta.'],
    ['📣 Convertir en propuesta', 'Estructura esto como una propuesta breve de producto o marketing, sin registrarla como hecho todavía.'],
  ];
  const el = document.createElement('div');
  el.className = 'context-shortcuts cutsports-shortcuts';
  el.innerHTML = '<span class="context-shortcuts-label">CutSports · siguiente paso</span>' + actions.map(([label, prompt]) =>
    `<button class="context-shortcut" data-prompt="${esc(prompt)}">${label}</button>`
  ).join('');
  el.addEventListener('click', e => {
    const prompt = e.target.dataset.prompt;
    if (prompt) prefill(prompt);
  });
  document.getElementById('messages').appendChild(el);
  scrollBottom();
}

function renderDrawSportsShortcuts(userText, responseText) {
  const text = (history.slice(-8).map(m => m.content).join(' ') + ' ' + userText).toLowerCase();
  const marketing = /marketing|campaña|campana|copy|landing|contenido|reel|newsletter|instagram|tiktok|youtube|linkedin|kpi/.test(text);
  const release = /release|publicar|publicación|publicacion|app store|appstore|build|archive|submit for review|versión|version|tienda/.test(text);
  const actions = release ? [
    ['📦 Añadir al lote', 'Comprueba si este cambio ya está en Pendiente de publicar y, si no, prepara una propuesta de ítem para el siguiente lote de DrawSports.'],
    ['✅ Checklist de publicación', 'Prepara el checklist mínimo para publicar este lote, sin afirmar que ya se ha publicado.'],
    ['🧭 Contrastar estado', 'Contrasta este cambio con Estado del Proyecto y distingue entre listo en repo, pendiente y publicado.'],
    ['📝 Preparar notas', 'Redacta un borrador de notas de versión claro para usuarios, en español e inglés si aplica.'],
  ] : marketing ? [
    ['📣 Convertir en propuesta', 'Estructura esta idea como propuesta de marketing de DrawSports: objetivo, audiencia, mensaje, canal y siguiente decisión.'],
    ['✍️ Preparar copy', 'Escribe una primera versión de copy para DrawSports, centrada en el problema real del entrenador.'],
    ['📊 Definir medición', 'Propón los KPIs y la forma de medir esta acción sin inventar resultados.'],
    ['📌 Guardar decisión', 'Si esta propuesta ya está aprobada, resume la decisión, el responsable y el siguiente paso.'],
  ] : [
    ['🛠️ Añadir al backlog', 'Comprueba duplicados y crea o actualiza este ítem en Backlog — DrawSports con área, prioridad, estado y notas concisas.'],
    ['🎯 Definir prioridad', 'Ayúdame a decidir el área y prioridad de este trabajo antes de guardarlo.'],
    ['🧭 Contrastar estado', 'Contrasta esta conversación con Estado del Proyecto y señala qué está verificado, qué falta y qué es propuesta.'],
    ['📦 Llevar a publicación', 'Si este cambio ya está listo en repo pero aún no está publicado, prepara una propuesta para Pendiente de publicar.'],
  ];
  const el = document.createElement('div');
  el.className = 'context-shortcuts drawsports-shortcuts';
  el.innerHTML = '<span class="context-shortcuts-label">DrawSports · siguiente paso</span>' + actions.map(([label, prompt]) =>
    `<button class="context-shortcut" data-prompt="${esc(prompt)}">${label}</button>`
  ).join('');
  el.addEventListener('click', e => {
    const prompt = e.target.dataset.prompt;
    if (prompt) prefill(prompt);
  });
  document.getElementById('messages').appendChild(el);
  scrollBottom();
}

function renderTheAnalystShortcuts(userText, responseText) {
  const text = (history.slice(-8).map(m => m.content).join(' ') + ' ' + userText).toLowerCase();
  const people = /lead|cliente|entrenador|coach|contacto|email|demo|embajador|embajadora|testimonio|caso de éxito|caso de exito/.test(text);
  const marketing = /marketing|campaña|campana|copy|landing|contenido|reel|newsletter|instagram|youtube|linkedin|lanzamiento|rrss/.test(text);
  const actions = people ? [
    ['👤 Revisar contacto', 'Busca si este entrenador o contacto ya existe antes de crear un registro.'],
    ['🤝 Registrar prospecto', 'Confirma que esta persona es un cliente potencial real y crea o actualiza el registro correspondiente.'],
    ['🌟 Valorar embajador', 'Evalúa si este contacto encaja como embajador: segmento, audiencia, valor mutuo y próximo paso.'],
    ['🗣️ Preparar mensaje', 'Redacta un mensaje breve, personalizado y útil para este contacto; no inventes datos.'],
  ] : marketing ? [
    ['📣 Convertir en propuesta', 'Estructura esta idea como propuesta de marketing de The Analyst: objetivo, audiencia, mensaje, canal y siguiente decisión.'],
    ['✍️ Preparar copy', 'Escribe una primera versión de copy centrada en el problema que resuelve The Analyst para un entrenador.'],
    ['🗓️ Planificar pieza', 'Si esta pieza ya está aprobada, prepara los datos necesarios para Calendario RRSS: canal, idioma, segmento, fecha y notas.'],
    ['📊 Definir medición', 'Propón los KPIs de esta acción y cómo medirlos, sin inventar resultados.'],
  ] : [
    ['🛠️ Añadir al backlog', 'Comprueba duplicados y crea o actualiza esta incoherencia o tarea en el Backlog de The Analyst.'],
    ['🗺️ Llevar al roadmap', 'Convierte esta idea en una propuesta priorizable para Roadmap — Próximos Pasos, sin tratarla como decisión cerrada.'],
    ['🧭 Contrastar estado', 'Contrasta esta conversación con Estado del Proyecto y separa lo verificado, lo pendiente y lo propuesto.'],
    ['✅ Registrar decisión', 'Si esta decisión ya está confirmada, resume el alcance, el motivo y el siguiente paso para actualizar el estado del proyecto.'],
  ];
  const el = document.createElement('div');
  el.className = 'context-shortcuts analyst-shortcuts';
  el.innerHTML = '<span class="context-shortcuts-label">The Analyst · siguiente paso</span>' + actions.map(([label, prompt]) =>
    `<button class="context-shortcut" data-prompt="${esc(prompt)}">${label}</button>`
  ).join('');
  el.addEventListener('click', e => {
    const prompt = e.target.dataset.prompt;
    if (prompt) prefill(prompt);
  });
  document.getElementById('messages').appendChild(el);
  scrollBottom();
}

function renderComunidadShortcuts(userText, responseText) {
  const text = (history.slice(-8).map(m => m.content).join(' ') + ' ' + userText).toLowerCase();
  const publishing = /publicar|publicación|publicacion|reel|youtube|instagram|newsletter|pieza lista|ya está preparado|ya esta preparado/.test(text);
  const strategy = /marketing|funnel|campaña|campana|copy|contenido|laboratorio|vip|skool|precio|oferta|entregable|público|publico/.test(text);
  const actions = publishing ? [
    ['📦 Revisar si está lista', 'Comprueba si esta pieza ya tiene contenido, canal, formato y siguiente acción de publicación definidos.'],
    ['📝 Preparar publicación', 'Si ya está preparada, conviértela en una propuesta para Pendiente de publicar sin marcarla como publicada.'],
    ['✍️ Ajustar copy', 'Revisa el copy para que deje claro el valor para el entrenador y la siguiente acción.'],
    ['📊 Definir medición', 'Define qué métrica y enlace o UTM permitirían evaluar esta publicación.'],
  ] : strategy ? [
    ['📣 Convertir en propuesta', 'Estructura esta idea para Marketing Comunidad: objetivo, audiencia, nivel de la escalera de valor, canal y siguiente decisión.'],
    ['🧭 Definir frontera', 'Aclara qué parte corresponde a contenido público, Comunidad, Laboratorio o VIP y por qué.'],
    ['✍️ Preparar copy', 'Escribe una primera versión de copy clara para entrenadores, sin prometer entregables no confirmados.'],
    ['🎯 Llevar al backlog', 'Si falta trabajo para ejecutar esta idea, crea o actualiza un ítem en Backlog — Comunidad con área y prioridad.'],
  ] : [
    ['🛠️ Añadir al backlog', 'Comprueba duplicados y crea o actualiza este ítem en Backlog — Comunidad con área, prioridad, estado y notas concisas.'],
    ['🎯 Definir prioridad', 'Ayúdame a decidir el área y prioridad de este trabajo antes de guardarlo.'],
    ['🧭 Contrastar estado', 'Contrasta esta conversación con Estado del Proyecto y distingue lo verificado de lo propuesto.'],
    ['📣 Convertir en propuesta', 'Estructura esto como una propuesta de producto, contenido o marketing sin registrarla como decisión cerrada.'],
  ];
  const el = document.createElement('div');
  el.className = 'context-shortcuts comunidad-shortcuts';
  el.innerHTML = '<span class="context-shortcuts-label">Comunidad · siguiente paso</span>' + actions.map(([label, prompt]) =>
    `<button class="context-shortcut" data-prompt="${esc(prompt)}">${label}</button>`
  ).join('');
  el.addEventListener('click', e => {
    const prompt = e.target.dataset.prompt;
    if (prompt) prefill(prompt);
  });
  document.getElementById('messages').appendChild(el);
  scrollBottom();
}

function renderBasketouchHubShortcuts(userText, responseText) {
  const text = (history.slice(-8).map(m => m.content).join(' ') + ' ' + userText).toLowerCase();
  const metrics = /métrica|metrica|kpi|dashboard|funnel|mrr|ingresos|usuarios|retención|retencion|datos|supabase|instrumentación|instrumentacion/.test(text);
  const planning = /prioridad|semana|acción|accion|tarea|hacer|bloqueado|siguiente paso|roadmap|coordinar/.test(text);
  const actions = metrics ? [
    ['📊 Contrastar fuente', 'Indica qué fuente real debe confirmar cada métrica y qué dato no está disponible todavía.'],
    ['🧩 Revisar módulo', 'Contrasta esta necesidad con Módulos por producto y separa lo implementado, pendiente y propuesto.'],
    ['🧭 Diseñar instrumentación', 'Convierte esto en una propuesta de instrumentación: evento o fuente, propietario, frecuencia y decisión que permitirá tomar.'],
    ['🎯 Crear acción transversal', 'Si requiere coordinación entre productos o infraestructura, crea o actualiza una Acción central tras comprobar duplicados.'],
  ] : planning ? [
    ['✅ Llevar a Acciones', 'Comprueba duplicados y crea o actualiza esta acción central en Inbox, con resultado esperado, próximo paso y bloqueo si existe.'],
    ['📅 Priorizar semana', 'Revisa Revisión semanal y propone si esta acción debe entrar en Esta semana, respetando el límite de cinco.'],
    ['🧭 Contrastar estado', 'Contrasta esta conversación con Estado del Hub y separa lo verificado, lo pendiente y la decisión necesaria.'],
    ['🗺️ Llevar al roadmap', 'Convierte esto en una propuesta de roadmap con alcance, dependencia y criterio de prioridad.'],
  ] : [
    ['✅ Crear acción transversal', 'Si esto necesita trabajo operativo entre productos, comprueba duplicados y crea o actualiza una Acción central en Inbox.'],
    ['📅 Revisar semana', 'Resume las acciones activas y los compromisos de esta semana, sin crear una lista paralela.'],
    ['🧭 Contrastar estado', 'Contrasta esta conversación con Estado del Hub antes de afirmar que una capacidad está disponible o terminada.'],
    ['📊 Separar dato y propuesta', 'Distingue los datos verificados, los datos que faltan y la propuesta de siguiente paso.'],
  ];
  const el = document.createElement('div');
  el.className = 'context-shortcuts basketouch-hub-shortcuts';
  el.innerHTML = '<span class="context-shortcuts-label">Basketouch Hub · siguiente paso</span>' + actions.map(([label, prompt]) =>
    `<button class="context-shortcut" data-prompt="${esc(prompt)}">${label}</button>`
  ).join('');
  el.addEventListener('click', e => {
    const prompt = e.target.dataset.prompt;
    if (prompt) prefill(prompt);
  });
  document.getElementById('messages').appendChild(el);
  scrollBottom();
}

function renderEnglishShortcuts(userText, responseText) {
  if (/guardad[oa]|saved|frase guardada/i.test(responseText)) return;
  const text = (userText + ' ' + responseText).toLowerCase();
  const isPractice = /practic|role play|conversation|conversaci[oó]n|ensay/.test(text);
  const actions = isPractice ? [
    ['🎭 Seguir practicando', 'Sigamos el role play con una situación un poco más exigente.'],
    ['📝 Corregir lo importante', 'Corrige solo mis errores de mayor impacto y dame la versión natural para decir en voz alta.'],
    ['💾 Guardar frase útil', 'Guarda la frase más reutilizable de este ejercicio en mi English Coach.'],
    ['🔁 Repasar', 'Ponme un repaso breve con frases que tenga pendientes.'],
  ] : [
    ['💾 Guardar frase útil', 'Guarda la frase más reutilizable que acabamos de trabajar en mi English Coach.'],
    ['🗣️ Practicarla', 'Hazme practicar esta frase en un role play corto y realista.'],
    ['📝 Explicar matiz', 'Explícame brevemente el matiz entre la traducción literal y la versión natural.'],
    ['🔁 Repasar', 'Ponme un repaso breve con frases que tenga pendientes.'],
  ];
  const el = document.createElement('div');
  el.className = 'context-shortcuts english-shortcuts';
  el.innerHTML = '<span class="context-shortcuts-label">English Coach · siguiente paso</span>' + actions.map(([label, prompt]) =>
    `<button class="context-shortcut" data-prompt="${esc(prompt)}">${label}</button>`
  ).join('');
  el.addEventListener('click', e => {
    const prompt = e.target.dataset.prompt;
    if (prompt) prefill(prompt);
  });
  document.getElementById('messages').appendChild(el);
  scrollBottom();
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
        '<button class="listen-btn" onclick="speakBubble(this)" title="Escuchar respuesta generada por IA">' +
          '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 010 7"/><path d="M19 5a10 10 0 010 14"/></svg>' +
          ' Escuchar <span>· Voz IA</span>' +
        '</button>' +
      '</div>' +
    '</div>';
  msgs.appendChild(el);
  scrollBottom();
  return el.querySelector('.bubble');
}

function cleanSpeechText(text) {
  return String(text)
    .replace(/```[\s\S]*?```/g, ' He omitido un bloque de código. ')
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1')
    .replace(/[*_#>`]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

async function speakBubble(button) {
  const bubble = button.closest('.msg-body').querySelector('.bubble');
  const text = cleanSpeechText(bubble._rawText || bubble.innerText);
  if (!text) return;
  if (activeSpeech && !activeSpeech.paused) {
    activeSpeech.pause();
    activeSpeech.currentTime = 0;
  }
  button.disabled = true;
  button.classList.add('speaking');
  setListenLabel(button, 'Preparando…');
  try {
    let url = button.dataset.speechUrl;
    if (!url) {
      const response = await fetch('/api/speech', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || 'No se pudo generar la voz');
      }
      url = URL.createObjectURL(await response.blob());
      button.dataset.speechUrl = url;
    }
    const audio = new Audio(url);
    activeSpeech = audio;
    audio.onended = () => resetListenButton(button);
    audio.onerror = () => resetListenButton(button);
    await audio.play();
    setListenLabel(button, 'Detener');
    button.onclick = () => { audio.pause(); audio.currentTime = 0; resetListenButton(button); };
  } catch (error) {
    button.title = error.message || 'No se pudo reproducir la voz';
    resetListenButton(button);
  }
}

function setListenLabel(button, label) {
  button.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 010 7"/><path d="M19 5a10 10 0 010 14"/></svg> ' + esc(label) + (label === 'Escuchar' ? ' <span>· Voz IA</span>' : '');
}

function resetListenButton(button) {
  if (!button) return;
  button.disabled = false;
  button.classList.remove('speaking');
  button.onclick = () => speakBubble(button);
  setListenLabel(button, 'Escuchar');
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

function setDisabled(v) {
  document.getElementById('send-btn').disabled = v;
  const voiceButton = document.getElementById('voice-btn');
  if (voiceButton && !(mediaRecorder && mediaRecorder.state === 'recording')) voiceButton.disabled = v;
}

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
  navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' })
    .then(function(registration) { return registration.update(); })
    .catch(function() {});
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
  resetTaskForm();
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

async function loadAdminData() { loadStats(); loadContainers(); loadTasks(); loadTelegramStatus(); }

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
    adminTasks = d.tasks || [];
    if (!d.tasks.length) { el.innerHTML = '<p class="no-items">No hay recordatorios programados</p>'; return; }
    el.innerHTML = d.tasks.map(function(t) {
      const sched = formatTaskSchedule(t);
      return '<div class="task-row">' +
        '<div class="task-info">' +
          '<div class="task-name">' + esc(t.name) + '</div>' +
          '<div class="task-schedule">' + esc(sched) + '</div>' +
        '</div>' +
        '<div class="task-actions">' +
          '<button class="task-btn" onclick="editTask(\'' + t.id + '\')">Editar</button>' +
          '<button class="task-btn" onclick="toggleTask(\'' + t.id + '\',' + (!t.enabled) + ')">' + (t.enabled ? 'Pausar' : 'Activar') + '</button>' +
          '<button class="task-btn danger" onclick="deleteTask(\'' + t.id + '\')">✕</button>' +
        '</div>' +
        '</div>';
    }).join('');
  } catch (_) { el.innerHTML = '<p class="no-items">Error al cargar</p>'; }
}

function formatTaskSchedule(task) {
  const p = task.schedule_params || {};
  const time = String(p.hour ?? 0).padStart(2, '0') + ':' + String(p.minute ?? 0).padStart(2, '0');
  if (task.schedule_type === 'date') {
    const when = new Date(p.run_date);
    return Number.isNaN(when.valueOf()) ? 'Una vez' : 'Una vez · ' + when.toLocaleString('es', { dateStyle: 'medium', timeStyle: 'short' });
  }
  if (task.schedule_type === 'interval') {
    if (p.hours) return 'Cada ' + p.hours + ' h';
    if (p.minutes) return 'Cada ' + p.minutes + ' min';
  }
  const days = { mon: 'lunes', tue: 'martes', wed: 'miércoles', thu: 'jueves', fri: 'viernes', sat: 'sábado', sun: 'domingo' };
  return p.day_of_week ? 'Cada ' + (days[p.day_of_week] || p.day_of_week) + ' · ' + time : 'Cada día · ' + time;
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

let editingTaskId = null;
let adminTasks = [];

function localDateTimeValue(date = new Date(Date.now() + 5 * 60000)) {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function renderTaskScheduleFields(task = null) {
  const type = document.getElementById('task-frequency').value;
  const el = document.getElementById('task-schedule-fields');
  const params = task ? task.schedule_params || {} : {};
  if (type === 'date') {
    const value = params.run_date ? localDateTimeValue(new Date(params.run_date)) : localDateTimeValue();
    el.innerHTML = '<label class="task-field-label" for="task-date">Fecha y hora (hora local)</label><input id="task-date" type="datetime-local" value="' + value + '" required>';
  } else if (type === 'daily') {
    const value = String(params.hour ?? 9).padStart(2, '0') + ':' + String(params.minute ?? 0).padStart(2, '0');
    el.innerHTML = '<label class="task-field-label" for="task-time">Hora (hora local)</label><input id="task-time" type="time" value="' + value + '" required>';
  } else if (type === 'weekly') {
    const value = String(params.hour ?? 9).padStart(2, '0') + ':' + String(params.minute ?? 0).padStart(2, '0');
    const day = params.day_of_week || 'mon';
    el.innerHTML = '<label class="task-field-label">Día y hora (hora local)</label><select id="task-day"><option value="mon">Lunes</option><option value="tue">Martes</option><option value="wed">Miércoles</option><option value="thu">Jueves</option><option value="fri">Viernes</option><option value="sat">Sábado</option><option value="sun">Domingo</option></select><input id="task-time" type="time" value="' + value + '" required>';
    document.getElementById('task-day').value = day;
  } else {
    const amount = params.hours || params.minutes || 1;
    const unit = params.hours ? 'hours' : 'minutes';
    el.innerHTML = '<label class="task-field-label">Repetir cada</label><input id="task-interval" type="number" min="1" max="999" value="' + amount + '" required><select id="task-interval-unit"><option value="hours">horas</option><option value="minutes">minutos</option></select>';
    document.getElementById('task-interval-unit').value = unit;
  }
}

function taskScheduleFromForm() {
  const type = document.getElementById('task-frequency').value;
  if (type === 'date') {
    const value = document.getElementById('task-date').value;
    if (!value) throw new Error('Elige la fecha y la hora.');
    const date = new Date(value);
    if (date <= new Date()) throw new Error('La fecha debe ser futura.');
    return { schedule_type: 'date', schedule_params: { run_date: date.toISOString() } };
  }
  if (type === 'interval') {
    const amount = Number(document.getElementById('task-interval').value);
    if (!Number.isInteger(amount) || amount < 1) throw new Error('Indica un intervalo válido.');
    return { schedule_type: 'interval', schedule_params: { [document.getElementById('task-interval-unit').value]: amount } };
  }
  const [hour, minute] = document.getElementById('task-time').value.split(':').map(Number);
  if (!Number.isInteger(hour) || !Number.isInteger(minute)) throw new Error('Elige una hora válida.');
  const params = { hour, minute };
  if (type === 'weekly') params.day_of_week = document.getElementById('task-day').value;
  return { schedule_type: 'cron', schedule_params: params };
}

function setTaskFormStatus(message = '', error = false) {
  const el = document.getElementById('task-form-status');
  el.textContent = message;
  el.classList.toggle('error', error);
}

function resetTaskForm() {
  editingTaskId = null;
  document.getElementById('task-form').reset();
  document.getElementById('task-frequency').value = 'date';
  renderTaskScheduleFields();
  document.getElementById('task-save-btn').textContent = 'Crear recordatorio';
  document.getElementById('task-cancel-btn').classList.add('hidden');
  setTaskFormStatus('');
}

function cancelTaskEdit() { resetTaskForm(); }

function editTask(id) {
  const task = adminTasks.find(t => t.id === id);
  if (!task) return;
  editingTaskId = id;
  document.getElementById('task-name').value = task.name || '';
  document.getElementById('task-prompt').value = task.prompt || '';
  const frequency = task.schedule_type === 'date' ? 'date'
    : task.schedule_type === 'interval' ? 'interval'
      : task.schedule_params?.day_of_week ? 'weekly' : 'daily';
  document.getElementById('task-frequency').value = frequency;
  renderTaskScheduleFields(task);
  document.getElementById('task-save-btn').textContent = 'Guardar cambios';
  document.getElementById('task-cancel-btn').classList.remove('hidden');
  setTaskFormStatus('Editando recordatorio.');
  document.getElementById('task-name').focus();
}

async function saveTask(event) {
  event.preventDefault();
  try {
    const schedule = taskScheduleFromForm();
    const body = {
      name: document.getElementById('task-name').value.trim(),
      prompt: document.getElementById('task-prompt').value.trim(),
      ...schedule,
    };
    if (!body.name || !body.prompt) throw new Error('Escribe un título y el mensaje.');
    const wasEditing = Boolean(editingTaskId);
    const path = wasEditing ? '/api/admin/tasks/' + editingTaskId : '/api/admin/tasks';
    const response = await fetch(path, {
      method: wasEditing ? 'PUT' : 'POST',
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'No se pudo guardar el recordatorio.');
    resetTaskForm();
    setTaskFormStatus(wasEditing ? 'Recordatorio actualizado.' : 'Recordatorio creado.');
    await loadTasks();
  } catch (error) { setTaskFormStatus(error.message || 'No se pudo guardar.', true); }
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
