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
  document.getElementById('token-input').focus();
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
