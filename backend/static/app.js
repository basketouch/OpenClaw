const API = '';
let token = localStorage.getItem('oc_token') || '';
let history = [];
let busy = false;
let currentChatId = null;
let pendingFile = null; // { file_id, filename, mime_type, size }
let pushSub = null;
let nextAssistContext = null;

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
    const contextMessages = history.slice(-16);
    const body = { messages: contextMessages, ...currentScope };
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
      renderContextShortcuts(msgText, responseText);
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

function hornbillsIntent(userText, responseText) {
  const recent = history.slice(-10).filter(m => m.role === 'user').map(m => m.content).join(' ') + ' ' + userText;
  const text = recent.toLowerCase();
  const score = patterns => patterns.reduce((total, pattern) => total + (text.match(pattern) || []).length, 0);
  const intents = {
    video: score([/vídeo|video|clip|análisis|analysis|spacing|motion|low post|high post|pnr|pick and roll/g]),
    player: score([/jugador|player|rol|role|desarrollo|development|strength|fortaleza|minutes|minutos|lesi[oó]n/g]),
    scouting: score([/rival|opponent|scouting|game plan|contra |\bvs\b|ato|blob|slob|weakness/g]),
    practice: score([/entrenamiento|training|práctica|practice|sesión|session|preseason|pretemporada/g]),
    staff: score([/césar|cesar|staff|head coach|reuni[oó]n|meeting|decisi[oó]n|proposal|propuesta/g]),
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
      ['🇬🇧 Brief para staff', 'Ayúdame a explicar este scouting en inglés claro para el staff.', 'english'],
    ],
    practice: [
      ['🏋️ Crear sesión', 'Crea un borrador de Practice Session con objetivo principal, secundarios y estado Draft.'],
      ['🎯 Definir objetivos', 'Convierte esta conversación en objetivos principales y secundarios de práctica.'],
      ['👤 Vincular jugadores', 'Identifica los jugadores que deben vincularse a esta sesión y prepara la relación.'],
      ['🇬🇧 Explicar práctica', 'Ayúdame a explicar esta práctica en inglés claro para el staff o los jugadores.', 'english'],
    ],
    staff: [
      ['🇬🇧 Pregunta para César', 'Ayúdame a formular esta pregunta para César en inglés natural y directo.', 'english'],
      ['🤝 Propuesta de staff', 'Convierte esto en una propuesta para Staff Notes & Decisions con estado To Discuss.'],
      ['✅ Registrar decisión', 'Si esta conversación contiene una decisión confirmada, regístrala como Decision para el staff.'],
      ['🔒 Guardar privado', 'Guarda esta reflexión como nota privada, sin compartirla con el staff.'],
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
  if (currentScope.workspace_id !== 'hornbills') return;
  if (/sesión cerrada|sesion cerrada|guardad[oa] en notion/i.test(responseText)) return;
  const intent = hornbillsIntent(userText, responseText);
  const labels = { video: 'Vídeo y análisis', player: 'Jugador', scouting: 'Rival y scouting', practice: 'Entrenamiento', staff: 'Staff y César' };
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
