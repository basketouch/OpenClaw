const API = '';
let token = localStorage.getItem('oc_token') || '';
let history = [];
let busy = false;

// ─── Auth ───────────────────────────────────────────────────────────────────

async function tryToken(t) {
  try {
    const r = await fetch(`${API}/api/health`, { headers: { Authorization: `Bearer ${t}` } });
    return r.ok;
  } catch {
    return false;
  }
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
      const data = await res.json();
      token = data.token;
      localStorage.setItem('oc_token', token);
      showApp();
    } else {
      setAuthErr('Usuario o contraseña incorrectos.');
      document.getElementById('login-btn').disabled = false;
      document.getElementById('password-input').focus();
    }
  } catch {
    setAuthErr('Error de conexión con el servidor.');
    document.getElementById('login-btn').disabled = false;
  }
}

function setAuthErr(msg) {
  document.getElementById('auth-error').textContent = msg;
}

function logout() {
  localStorage.removeItem('oc_token');
  location.reload();
}

// ─── Init ────────────────────────────────────────────────────────────────────

async function init() {
  if (token) {
    if (await tryToken(token)) { showApp(); return; }
    localStorage.removeItem('oc_token');
    token = '';
  }
  document.getElementById('username-input').focus();
}

function showApp() {
  document.getElementById('auth-screen').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  showWelcome();
  document.getElementById('msg-input').focus();
}

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

function newChat() {
  history = [];
  showWelcome();
}

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
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

// ─── Chat ────────────────────────────────────────────────────────────────────

async function sendMessage() {
  if (busy) return;
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  resize(input);
  document.querySelector('.welcome')?.remove();

  history.push({ role: 'user', content: text });
  appendUserMsg(text);

  busy = true;
  setDisabled(true);
  setStatus('loading');

  const bubble = appendAssistantBubble();
  const toolsEl = bubble.parentElement.querySelector('.tools');
  let responseText = '';

  try {
    const res = await fetch(`${API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ messages: history }),
    });

    if (res.status === 401) { logout(); return; }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });

      const parts = buf.split('\n\n');
      buf = parts.pop(); // keep incomplete chunk

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith('data: ')) continue;
        const raw = line.slice(6).trim();
        if (!raw) continue;

        let ev;
        try { ev = JSON.parse(raw); } catch { continue; }

        if (ev.type === 'text') {
          responseText += ev.content;
          bubble.classList.remove('cursor');
          bubble.innerHTML = renderMd(responseText);
          bubble.classList.add('cursor');
          scrollBottom();
        } else if (ev.type === 'tool_start') {
          addTool(toolsEl, ev.name, 'running');
        } else if (ev.type === 'tool_done') {
          doneTool(toolsEl, ev.name);
        } else if (ev.type === 'done') {
          bubble.classList.remove('cursor');
        } else if (ev.type === 'error') {
          bubble.classList.remove('cursor');
          bubble.innerHTML = `<span class="err">Error: ${esc(ev.message)}</span>`;
        }
      }
    }

    bubble.classList.remove('cursor');
    if (responseText) history.push({ role: 'assistant', content: responseText });

  } catch (err) {
    bubble.classList.remove('cursor');
    bubble.innerHTML = `<span class="err">${esc(err.message)}</span>`;
  } finally {
    busy = false;
    setDisabled(false);
    setStatus('ready');
  }
}

// ─── UI helpers ──────────────────────────────────────────────────────────────

function appendUserMsg(text) {
  const msgs = document.getElementById('messages');
  const el = document.createElement('div');
  el.className = 'msg user';
  el.innerHTML = `<div class="avatar user-av">J</div><div class="bubble user-bubble">${esc(text)}</div>`;
  msgs.appendChild(el);
  scrollBottom();
}

function appendAssistantBubble() {
  const msgs = document.getElementById('messages');
  const el = document.createElement('div');
  el.className = 'msg assistant';
  el.innerHTML = `
    <div class="avatar alex-av">⚡</div>
    <div class="msg-body">
      <div class="bubble alex-bubble cursor"></div>
      <div class="tools"></div>
    </div>`;
  msgs.appendChild(el);
  scrollBottom();
  return el.querySelector('.bubble');
}

function addTool(container, name, state) {
  const el = document.createElement('div');
  el.className = `tool ${state}`;
  el.dataset.tool = name;
  el.innerHTML = `<span class="tool-icon">${state === 'running' ? '⚙' : '✓'}</span> ${esc(name)}`;
  container.appendChild(el);
  scrollBottom();
}

function doneTool(container, name) {
  const el = container.querySelector(`[data-tool="${name}"]`);
  if (el) { el.className = 'tool done'; el.innerHTML = `<span class="tool-icon">✓</span> ${esc(name)}`; }
}

function setDisabled(v) { document.getElementById('send-btn').disabled = v; }

function setStatus(state) {
  document.getElementById('status-dot').className = state === 'loading' ? 'dot loading' : 'dot';
}

function scrollBottom() {
  const c = document.getElementById('chat');
  c.scrollTop = c.scrollHeight;
}

function esc(t) {
  return String(t)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function renderMd(text) {
  // Split on fenced code blocks to handle them separately
  const parts = text.split(/(```[\w]*\n[\s\S]*?```)/g);
  return parts.map((part, i) => {
    if (i % 2 === 1) {
      const code = part.replace(/^```[\w]*\n/, '').replace(/\n?```$/, '');
      return `<pre><code>${esc(code)}</code></pre>`;
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

document.getElementById('username-input')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('password-input').focus();
});
document.getElementById('password-input')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') login();
});

init();

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// ─── WhatsApp modal ──────────────────────────────────────────────────────────

async function openWA() {
  document.getElementById('wa-modal').classList.remove('hidden');
  await loadWA();
}

function closeWA(e) {
  if (!e || e.target === document.getElementById('wa-modal')) {
    document.getElementById('wa-modal').classList.add('hidden');
  }
}

async function loadWA() {
  const statusBar = document.getElementById('wa-status-bar');
  const qrArea = document.getElementById('wa-qr-area');

  statusBar.innerHTML = '<div class="wa-status mid">Comprobando conexión…</div>';
  qrArea.innerHTML = '<p style="color:var(--muted);font-size:14px">Cargando QR…</p>';

  try {
    const r = await fetch('/api/whatsapp/status', { headers: { Authorization: `Bearer ${token}` } });
    const data = await r.json();
    const connected = data.conectado || data.status === 'WORKING';
    const estado = data.estado || data.status || 'UNKNOWN';
    if (connected) {
      statusBar.innerHTML = `<div class="wa-status ok">● Conectado — ${esc(estado)}</div>`;
      qrArea.innerHTML = '<p style="color:var(--muted);font-size:14px;padding:16px 0">WhatsApp ya está vinculado y funcionando.</p>';
      return;
    }
    statusBar.innerHTML = `<div class="wa-status err">● Desconectado — ${esc(estado)}</div>`;
  } catch {
    statusBar.innerHTML = '<div class="wa-status err">● No se pudo conectar con WAHA</div>';
  }

  try {
    const r = await fetch('/api/whatsapp/qr', { headers: { Authorization: `Bearer ${token}` } });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const blob = await r.blob();
    qrArea.innerHTML = `<img src="${URL.createObjectURL(blob)}" alt="QR WhatsApp">`;
  } catch (e) {
    qrArea.innerHTML = `<p style="color:var(--err);font-size:13px">No se pudo cargar el QR: ${esc(e.message)}</p>`;
  }
}

// ─── Admin panel ─────────────────────────────────────────────────────────────

function openAdmin() {
  document.getElementById('admin-overlay').classList.remove('hidden');
  document.getElementById('admin-panel').classList.remove('hidden');
  requestAnimationFrame(() => document.getElementById('admin-panel').classList.add('open'));
  loadAdminData();
}

function closeAdmin() {
  const panel = document.getElementById('admin-panel');
  panel.classList.remove('open');
  setTimeout(() => {
    panel.classList.add('hidden');
    document.getElementById('admin-overlay').classList.add('hidden');
  }, 250);
}

async function adminFetch(path) {
  const r = await fetch(path, { headers: { Authorization: `Bearer ${token}` } });
  return r.json();
}

async function loadAdminData() {
  loadStats();
  loadContainers();
  loadTasks();
}

async function loadStats() {
  try {
    const d = await adminFetch('/api/admin/stats');
    document.getElementById('s-disk').textContent = d.disk || '—';
    document.getElementById('s-mem').textContent = d.memory || '—';
    document.getElementById('s-load').textContent = d.load || '—';
    document.getElementById('s-uptime').textContent = d.uptime || '—';
  } catch {
    document.getElementById('s-disk').textContent = 'error';
  }
}

async function loadContainers() {
  const el = document.getElementById('admin-containers');
  try {
    const d = await adminFetch('/api/admin/containers');
    if (d.error) { el.innerHTML = `<p class="no-items" style="color:var(--err)">${esc(d.error)}</p>`; return; }
    if (!d.containers.length) { el.innerHTML = '<p class="no-items">Sin contenedores</p>'; return; }
    el.innerHTML = d.containers.map(c => `
      <div class="container-row">
        <span class="container-name">${esc(c.name)}</span>
        <span class="container-status ${c.up ? 'status-up' : 'status-down'}">${c.up ? '● Activo' : '● Parado'}</span>
      </div>`).join('');
  } catch { el.innerHTML = '<p class="no-items">Error al cargar</p>'; }
}

async function loadTasks() {
  const el = document.getElementById('admin-tasks');
  try {
    const d = await adminFetch('/api/admin/tasks');
    if (!d.tasks.length) { el.innerHTML = '<p class="no-items">No hay tareas programadas</p>'; return; }
    el.innerHTML = d.tasks.map(t => {
      const sched = t.schedule_type === 'cron'
        ? 'Cron: ' + JSON.stringify(t.schedule_params)
        : 'Cada: ' + JSON.stringify(t.schedule_params);
      const label = t.enabled ? 'Pausar' : 'Activar';
      return `<div class="task-row">
        <div class="task-info">
          <div class="task-name">${esc(t.name)}</div>
          <div class="task-schedule">${esc(sched)}</div>
        </div>
        <div class="task-actions">
          <button class="task-btn" onclick="toggleTask('${t.id}',${!t.enabled})">${label}</button>
          <button class="task-btn danger" onclick="deleteTask('${t.id}')">✕</button>
        </div>
      </div>`;
    }).join('');
  } catch { el.innerHTML = '<p class="no-items">Error al cargar</p>'; }
}

async function toggleTask(id, enabled) {
  await fetch(`/api/admin/tasks/${id}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  loadTasks();
}

async function deleteTask(id) {
  if (!confirm('¿Eliminar esta tarea?')) return;
  await fetch(`/api/admin/tasks/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  loadTasks();
}

async function doDeploy() {
  const btn = document.querySelector('.deploy-btn');
  const msg = document.getElementById('deploy-msg');
  btn.disabled = true;
  btn.textContent = 'Iniciando…';
  try {
    const d = await fetch('/api/admin/deploy', {
      method: 'POST', headers: { Authorization: `Bearer ${token}` },
    }).then(r => r.json());
    msg.textContent = d.message;
    btn.textContent = '✓ Deploy iniciado';
  } catch {
    btn.disabled = false;
    btn.textContent = '↑ Actualizar a la última versión';
    msg.textContent = 'Error al iniciar deploy';
  }
}
