// OpenClaw v2 mode switch — loaded after app.js
let ocMode = 'auto';

function modeLabel(mode) {
  return mode === 'english' ? 'English' : 'Alex';
}

function renderModeSwitch() {
  let host = document.getElementById('oc-mode-switch');
  if (!host) {
    host = document.createElement('div');
    host.id = 'oc-mode-switch';
    host.innerHTML = `
      <button data-mode="auto" onclick="setOpenClawMode('auto')">⚡ Alex</button>
      <button data-mode="english" onclick="setOpenClawMode('english')">🇬🇧 English</button>`;
    const hdrRight = document.querySelector('.hdr-right');
    if (hdrRight) hdrRight.prepend(host);

    const style = document.createElement('style');
    style.textContent = `
      #oc-mode-switch{display:flex;gap:3px;background:rgba(255,255,255,.06);padding:3px;border-radius:10px;margin-right:8px}
      #oc-mode-switch button{border:0;background:transparent;color:var(--muted);font:inherit;font-size:12px;padding:6px 8px;border-radius:8px;cursor:pointer;white-space:nowrap}
      #oc-mode-switch button.on{background:rgba(255,255,255,.11);color:var(--text)}
      body.oc-english .hdr-icon{filter:none}
      @media(max-width:520px){#oc-mode-switch button{font-size:0;padding:7px 9px}#oc-mode-switch button::first-letter{font-size:14px}}
    `;
    document.head.appendChild(style);
  }

  host.querySelectorAll('button').forEach(btn => {
    btn.classList.toggle('on', btn.dataset.mode === ocMode);
  });

  document.body.classList.toggle('oc-english', ocMode === 'english');
  const title = document.querySelector('.hdr-title');
  const icon = document.querySelector('.hdr-icon');
  if (title) title.textContent = modeLabel(ocMode);
  if (icon) icon.textContent = ocMode === 'english' ? '🇬🇧' : '⚡';
  const input = document.getElementById('msg-input');
  if (input) input.placeholder = ocMode === 'english' ? 'English Coach…' : 'Escribe un mensaje…';
}

async function setOpenClawMode(mode, persist = true) {
  ocMode = mode === 'english' ? 'english' : 'auto';
  renderModeSwitch();

  if (persist && typeof currentChatId !== 'undefined' && currentChatId) {
    try {
      await fetch(`/api/chats/${currentChatId}`, {
        method: 'PUT',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: history || [], mode: ocMode }),
      });
    } catch (_) {}
  }
}

function syncModeFromCurrentChat() {
  if (typeof currentChatId === 'undefined' || !currentChatId || typeof chatList === 'undefined') return;
  const chat = chatList.find(c => c.id === currentChatId);
  setOpenClawMode(chat?.mode === 'english' ? 'english' : 'auto', false);
}

// Inject mode into chat API requests and chat persistence without duplicating app.js.
const _ocFetch = window.fetch.bind(window);
window.fetch = async function(input, init = {}) {
  const url = typeof input === 'string' ? input : (input?.url || '');
  const method = (init.method || 'GET').toUpperCase();

  if (init.body && typeof init.body === 'string') {
    try {
      const body = JSON.parse(init.body);
      if (url.endsWith('/api/chat') && method === 'POST') {
        body.mode = ocMode;
        init = { ...init, body: JSON.stringify(body) };
      } else if (/\/api\/chats\/[a-zA-Z0-9-]+$/.test(url) && method === 'PUT') {
        body.mode = ocMode;
        init = { ...init, body: JSON.stringify(body) };
      }
    } catch (_) {}
  }

  return _ocFetch(input, init);
};

// Wrap existing navigation functions so each conversation restores its mode.
if (typeof loadChat === 'function') {
  const _loadChat = loadChat;
  loadChat = async function(id) {
    await _loadChat(id);
    syncModeFromCurrentChat();
  };
}

if (typeof startNewChat === 'function') {
  const _startNewChat = startNewChat;
  startNewChat = async function(...args) {
    await _startNewChat(...args);
    setOpenClawMode('auto', true);
  };
}

// Add mode marker to sidebar conversations.
if (typeof renderChatList === 'function') {
  const _renderChatList = renderChatList;
  renderChatList = function() {
    _renderChatList();
    document.querySelectorAll('.chat-item').forEach((el, i) => {
      const chat = chatList[i];
      if (!chat || chat.mode !== 'english') return;
      const title = el.querySelector('.chat-item-title');
      if (title && !title.textContent.startsWith('🇬🇧')) title.textContent = `🇬🇧 ${title.textContent}`;
    });
  };
}

renderModeSwitch();
setTimeout(syncModeFromCurrentChat, 0);
