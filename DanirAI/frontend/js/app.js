/* ============================================================
   DanirAI — логика интерфейса
   ============================================================ */
(function () {
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const API = window.DanirAPI;
  const MD = window.DanirMarkdown;

  const state = {
    user: null,
    models: [],
    chats: [],
    currentChat: null,
    mode: 'chat',
    modelId: 'danirai-1v',
    busy: false,
    plans: null,
  };

  /* ---------------- утилиты ---------------- */
  function toast(msg, kind) {
    const el = $('#toast');
    el.textContent = msg;
    el.className = 'toast ' + (kind || '');
    el.classList.remove('hidden');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.add('hidden'), 4200);
  }
  function fmtTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  }
  function tierBadge(tier) {
    return { free: 'FREE', plus: 'PLUS', pro: 'PRO' }[tier] || tier;
  }
  function esc(s) { return MD.escapeHtml(s); }
  function modelById(id) { return state.models.find((m) => m.id === id); }
  function planAllows(modelId) {
    const plan = state.user && state.user.plan;
    return !plan || (plan.models || []).includes(modelId);
  }
  function avatarHtml(user, size) {
    if (user && user.avatar_url) return 'style="background-image:url(\'' + user.avatar_url + '\')"';
    return '';
  }

  /* ---------------- старт ---------------- */
  async function boot() {
    try {
      const status = await API.get('/api/status').catch(() => null);
      if (!status) throw new Error('offline');
    } catch (e) {
      $('#boot').innerHTML =
        '<div class="boot-logo"><div class="boot-text" style="max-width:420px;text-align:center;line-height:1.7">' +
        '⚠️ Не удалось связаться с сервером DanirAI.<br><br>Запустите бэкенд:<br><code style="font-family:monospace">cd backend && uvicorn app.main:app --port 8000</code>' +
        '</div></div>';
      return;
    }
    state.models = (await API.get('/api/models').catch(() => ({ models: [] }))).models || [];
    renderHeroModels();
    renderAuthPlans();

    if (API.store.token) {
      try {
        state.user = await API.get('/api/auth/me');
        return enterApp();
      } catch (e) { /* токен протух */ }
    }
    $('#boot').classList.add('hidden');
    $('#screen-auth').classList.remove('hidden');
  }

  window.addEventListener('danirai:unauthorized', () => {
    state.user = null;
    $('#app').classList.add('hidden');
    $('#screen-auth').classList.remove('hidden');
  });

  /* ---------------- экран входа ---------------- */
  function renderHeroModels() {
    const box = $('#hero-models');
    if (!box) return;
    box.innerHTML = state.models.map((m) =>
      '<div class="hero-model"><span>' + m.icon + '</span><div><b>' + esc(m.name) + '</b><br><span>' + esc(m.tagline) + '</span></div></div>'
    ).join('');
  }

  async function renderAuthPlans() {
    const plans = (await API.get('/api/plans').catch(() => null)) || {};
    const box = $('#auth-plans');
    if (!box || !plans.plans) return;
    box.innerHTML =
      '<h2>Тарифы для каждого</h2><div class="sub">Начните бесплатно — расширяйтесь, когда понадобится суперсила</div>' +
      '<div class="plans-grid">' + plans.plans.map(planCardHtml).join('') + '</div>';
  }

  function planCardHtml(p) {
    const current = state.user && state.user.tier === p.id;
    return (
      '<div class="plan-card' + (p.highlight ? ' hot' : '') + '">' +
      (p.highlight ? '<div class="flag">ПОПУЛЯРНЫЙ</div>' : '') +
      '<div class="plan-name">' + esc(p.name) + '</div>' +
      '<div class="plan-price">' + esc(p.price_label) + ' <small>/ ' + esc(p.period) + '</small></div>' +
      '<ul class="plan-feats">' + p.features.map((f) => '<li>' + esc(f) + '</li>').join('') + '</ul>' +
      (current
        ? '<div class="plan-current">✓ Ваш текущий тариф</div>'
        : state.user
          ? '<button class="btn ' + (p.price ? 'btn-primary' : 'btn-ghost') + '" data-plan="' + p.id + '">' + (p.price ? 'Перейти на ' + esc(p.name) : 'Вернуться на Free') + '</button>'
          : '<div class="plan-current" style="border-style:solid;border-color:var(--border);color:var(--muted)">Доступно после регистрации</div>') +
      '</div>'
    );
  }

  $$('.auth-tab').forEach((t) =>
    t.addEventListener('click', () => {
      $$('.auth-tab').forEach((x) => x.classList.remove('active'));
      t.classList.add('active');
      $('#form-login').classList.toggle('hidden', t.dataset.tab !== 'login');
      $('#form-register').classList.toggle('hidden', t.dataset.tab !== 'register');
    })
  );

  $('#form-login').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const r = await API.post('/api/auth/login', { email: fd.get('email'), password: fd.get('password') });
      API.store.token = r.access_token;
      state.user = r.user;
      state.user.plan = (await API.get('/api/auth/me')).plan || state.user.plan;
      enterApp();
    } catch (err) { $('#login-error').textContent = err.detail || err.message; }
  });

  $('#form-register').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const r = await API.post('/api/auth/register', {
        email: fd.get('email'), password: fd.get('password'), display_name: fd.get('display_name') || '',
      });
      API.store.token = r.access_token;
      state.user = r.user;
      state.user.plan = (await API.get('/api/auth/me')).plan || state.user.plan;
      toast('Добро пожаловать в DanirAI, ' + (state.user.display_name || 'друг') + '! 🎉', 'ok');
      enterApp();
    } catch (err) { $('#register-error').textContent = err.detail || err.message; }
  });

  /* ---------------- вход в приложение ---------------- */
  async function enterApp() {
    if (!state.user.plan) {
      try { const me = await API.get('/api/auth/me'); state.user.plan = me.plan; state.user.tier = me.tier; } catch (e) {}
    }
    $('#boot').classList.add('hidden');
    $('#screen-auth').classList.add('hidden');
    $('#app').classList.remove('hidden');
    if (state.user.is_admin) $('.admin-only').classList.remove('hidden');
    renderUserChip();
    await loadChats();
    renderModelMenu();
    switchView('chat');
  }

  function renderUserChip() {
    const u = state.user;
    const av = $('#user-avatar');
    av.textContent = (u.display_name || u.email || '?')[0].toUpperCase();
    if (u.avatar_url) av.style.backgroundImage = 'url(' + u.avatar_url + ')';
    $('#user-name').textContent = u.display_name || u.email;
    const badge = $('#user-tier');
    badge.textContent = tierBadge(u.tier);
    badge.className = 'tier-badge ' + u.tier;
  }

  /* ---------------- вкладки ---------------- */
  $$('.side-tab').forEach((t) => t.addEventListener('click', () => switchView(t.dataset.view)));
  function switchView(view) {
    $$('.side-tab').forEach((t) => t.classList.toggle('active', t.dataset.view === view));
    $$('.view').forEach((v) => v.classList.remove('active'));
    $('#view-' + view).classList.add('active');
    if (view === 'gallery') loadGallery();
    if (view === 'plans') loadPlans();
    if (view === 'admin') loadAdmin();
    $('#sidebar').classList.remove('open');
  }

  /* ---------------- чаты ---------------- */
  async function loadChats() {
    state.chats = await API.get('/api/chats').catch(() => []);
    renderChatList();
  }
  function renderChatList(filter) {
    const box = $('#chat-list');
    const q = (filter || '').toLowerCase();
    const list = state.chats.filter((c) => !q || (c.title || '').toLowerCase().includes(q));
    if (!list.length) {
      box.innerHTML = '<div style="padding:22px 10px;color:var(--faint);font-size:13px;text-align:center">Чатов пока нет.<br>Создайте первый! ✨</div>';
      return;
    }
    box.innerHTML = list.map((c) =>
      '<div class="chat-item' + (state.currentChat && state.currentChat.id === c.id ? ' active' : '') + '" data-id="' + c.id + '">' +
      (c.is_pinned ? '<span class="pin">📌</span>' : '') +
      '<span class="t">' + esc(c.title || 'Чат') + '</span>' +
      '<span class="del" data-del="' + c.id + '" title="Удалить">🗑</span>' +
      '</div>'
    ).join('');
  }
  $('#chat-search').addEventListener('input', (e) => renderChatList(e.target.value));
  $('#chat-list').addEventListener('click', async (e) => {
    const del = e.target.dataset.del;
    if (del) {
      e.stopPropagation();
      if (confirm('Удалить чат вместе с историей?')) {
        await API.del('/api/chats/' + del).catch(() => {});
        if (state.currentChat && state.currentChat.id === del) { state.currentChat = null; $('#messages').innerHTML = ''; showWelcome(); }
        await loadChats();
      }
      return;
    }
    const item = e.target.closest('.chat-item');
    if (item) openChat(item.dataset.id);
  });
  $('#btn-new-chat').addEventListener('click', () => newChat());
  $('#btn-clear-chat').addEventListener('click', async () => {
    if (!state.currentChat) return;
    if (confirm('Удалить этот чат?')) {
      await API.del('/api/chats/' + state.currentChat.id).catch(() => {});
      state.currentChat = null;
      $('#messages').innerHTML = '';
      showWelcome();
      loadChats();
    }
  });
  $('#btn-share').addEventListener('click', async () => {
    if (!state.currentChat) return toast('Сначала откройте чат');
    try {
      const r = await API.post('/api/chats/' + state.currentChat.id + '/share', {});
      const url = location.origin + r.url;
      await navigator.clipboard.writeText(url).catch(() => {});
      toast('Ссылка на чат скопирована: ' + url, 'ok');
    } catch (err) { toast(err.detail || 'Не удалось поделиться', 'err'); }
  });

  async function newChat() {
    state.currentChat = null;
    $('#messages').innerHTML = '';
    showWelcome();
    renderChatList($('#chat-search').value);
    $('#input').focus();
    switchView('chat');
  }

  async function openChat(id) {
    try {
      const full = await API.get('/api/chats/' + id);
      state.currentChat = full.chat;
      state.currentChat.messages = full.messages;
      state.modelId = full.chat.model_id || 'danirai-1v';
      updateModelButton();
      renderChatList($('#chat-search').value);
      renderMessages(full.messages);
      switchView('chat');
    } catch (err) { toast(err.detail || 'Чат недоступен', 'err'); }
  }

  function showWelcome() {
    const u = state.user || {};
    $('#messages').innerHTML =
      '<div class="welcome">' +
      '<div class="logo-big">🤖</div>' +
      '<h2>Привет, <span class="grad-text">' + esc(u.display_name || 'исследователь') + '</span>!</h2>' +
      '<p>Я DanirAI — задайте вопрос, попросите картинку, видео или глубокое исследование.</p>' +
      '<div class="suggests">' +
      [
        ['💡 Объясни простыми словами', 'как работает нейросеть и почему она «думает»'],
        [' Реши задачу', 'посчитай сложные проценты: 250 000 ₸ под 14% годовых на 3 года'],
        ['🎨 Нарисуй', 'футуристический город Астана ночью, неоновые огни, дождь'],
        ['🔎 Исследуй', 'рынок электромобилей в Центральной Азии: тренды и прогнозы'],
      ].map((s) => '<button class="suggest" data-q="' + esc(s[1]) + '"><b>' + s[0] + '</b><span>' + esc(s[1]) + '</span></button>').join('') +
      '</div></div>';
    $$('.suggest').forEach((b) => b.addEventListener('click', () => {
      const mode = b.dataset.q.startsWith('футурист') ? 'image' : b.dataset.q.startsWith('рынок') ? 'research' : 'chat';
      setMode(mode);
      $('#input').value = b.dataset.q;
      autosize();
      $('#input').focus();
    }));
  }

  /* ---------------- сообщения ---------------- */
  function renderMessages(messages) {
    const box = $('#messages');
    if (!messages || !messages.length) return showWelcome();
    box.innerHTML = messages.map(messageHtml).join('');
    bindMessageActions(box);
    scrollBottom();
  }

  function messageHtml(m) {
    const isUser = m.role === 'user';
    const model = modelById(m.model_id);
    const av = isUser
      ? '<div class="msg-avatar">' + esc((state.user.display_name || state.user.email || '?')[0].toUpperCase()) + '</div>'
      : '<div class="msg-avatar">D</div>';
    let media = '';
    if (m.attachments && m.attachments.length) {
      media = '<div class="msg-media">' + m.attachments.map((a) =>
        a.kind === 'video'
          ? '<video src="' + a.url + '" controls preload="metadata"></video>'
          : '<img src="' + a.url + '" alt="" loading="lazy" data-zoom="' + a.url + '">'
      ).join('') + '</div>';
    }
    let sources = '';
    if (m.sources && m.sources.length) {
      sources = '<div class="sources">' + m.sources.map((s, i) =>
        '<a class="source-chip" href="' + esc(s.url || '#') + '" target="_blank" rel="noopener">🔗 <span>' + (i + 1) + '. ' + esc(s.title || s.url || '') + '</span></a>'
      ).join('') + '</div>';
    }
    const reasoning = m.reasoning
      ? '<details class="reasoning"><summary>Мышление ' + esc(model ? model.name : 'DanirAI') + '</summary><div class="r-body">' + esc(m.reasoning) + '</div></details>'
      : '';
    return (
      '<div class="msg-row ' + (isUser ? 'user' : 'ai') + '" data-id="' + m.id + '">' + av +
      '<div class="msg-body">' +
      '<div class="msg-head"><b>' + (isUser ? esc(state.user.display_name || 'Вы') : 'DanirAI') + '</b>' +
      (m.model_id ? '<span class="m-model">' + esc((model && model.name) || m.model_id) + '</span>' : '') +
      '<time>' + fmtTime(m.created_at) + '</time></div>' +
      reasoning +
      '<div class="msg-content">' + (isUser ? esc(m.content) : MD.render(m.content)) + '</div>' +
      media + sources +
      (isUser ? '' :
        '<div class="msg-actions">' +
        '<button data-act="copy">📋 Копировать</button>' +
        '<button data-act="speak">🔊 Озвучить</button>' +
        '<button data-act="regen">🔄 Заново</button>' +
        '</div>') +
      '</div></div>'
    );
  }

  function bindMessageActions(scope) {
    $$('[data-act]', scope).forEach((btn) => {
      btn.onclick = async () => {
        const row = btn.closest('.msg-row');
        const contentEl = $('.msg-content', row);
        if (btn.dataset.act === 'copy') {
          await navigator.clipboard.writeText(contentEl.innerText).catch(() => {});
          toast('Скопировано', 'ok');
        }
        if (btn.dataset.act === 'speak') speak(contentEl.innerText);
        if (btn.dataset.act === 'regen' && state.currentChat) {
          try {
            const r = await API.post('/api/chats/' + state.currentChat.id + '/regenerate', {});
            openChat(state.currentChat.id);
          } catch (err) { toast(err.detail || 'Ошибка', 'err'); }
        }
      };
    });
    $$('img[data-zoom]', scope).forEach((img) => {
      img.onclick = () => {
        $('#image-modal-img').src = img.dataset.zoom;
        $('#image-modal-link').href = img.dataset.zoom;
        $('#image-modal-title').textContent = 'Изображение DanirAI';
        $('#modal-image').classList.remove('hidden');
      };
    });
  }

  function speak(text) {
    if (!('speechSynthesis' in window)) return toast('Озвучка не поддерживается браузером', 'err');
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text.slice(0, 4000));
    u.lang = 'ru-RU';
    u.rate = 1.02;
    speechSynthesis.speak(u);
    toast('🔊 Озвучиваю ответ…');
  }

  function scrollBottom() {
    const box = $('#messages');
    box.scrollTop = box.scrollHeight;
  }

  /* ---------------- выбор модели ---------------- */
  function renderModelMenu() {
    const menu = $('#model-menu');
    menu.innerHTML = state.models.map((m) => {
      const locked = !planAllows(m.id);
      return (
        '<button class="model-opt' + (m.id === state.modelId ? ' active' : '') + '" data-model="' + m.id + '">' +
        '<span class="mi">' + m.icon + '</span><div><div class="mn">' + esc(m.name) +
        (locked ? ' <span class="model-lock">🔒 ' + esc(m.tier.toUpperCase()) + '</span>' : '') +
        (m.id === state.modelId ? ' <span class="model-cur">✓</span>' : '') +
        '</div><div class="md">' + esc(m.tagline) + '</div></div></button>'
      );
    }).join('');
    $$('.model-opt', menu).forEach((b) => b.addEventListener('click', async () => {
      const id = b.dataset.model;
      if (!planAllows(id)) {
        toast('Модель доступна на тарифе выше — откройте «Тарифы» 💎');
        switchView('plans');
        return;
      }
      state.modelId = id;
      if (state.currentChat) await API.patch('/api/chats/' + state.currentChat.id, { model_id: id }).catch(() => {});
      updateModelButton();
      renderModelMenu();
      $('#model-menu').classList.add('hidden');
      const m = modelById(id);
      if (m && m.kind === 'image') setMode('image');
      else if (m && m.kind === 'video') setMode('video');
      else if (m && m.kind === 'research') setMode('research');
      else setMode('chat');
    }));
  }
  function updateModelButton() {
    const m = modelById(state.modelId) || { icon: '⚡', name: 'DanirAI-1v' };
    $('#model-icon').textContent = m.icon;
    $('#model-name').textContent = m.name;
  }
  $('#model-btn').addEventListener('click', (e) => { e.stopPropagation(); $('#model-menu').classList.toggle('hidden'); });
  document.addEventListener('click', () => $('#model-menu').classList.add('hidden'));

  /* ---------------- режимы композера ---------------- */
  function setMode(mode) {
    state.mode = mode;
    $$('#mode-chips .chip').forEach((c) => c.classList.toggle('active', c.dataset.mode === mode));
    const ph = {
      chat: 'Спросите DanirAI о чём угодно…',
      image: 'Опишите картинку: «закат в горах Алматы, масло, холст»…',
      video: 'Опишите сцену для видео: «дрон летит над ночным городом»…',
      research: 'Тема глубокого исследования…',
    }[mode];
    $('#input').placeholder = ph;
    if (mode === 'research') {
      const m = modelById('danirai-research');
      if (m && planAllows('danirai-research')) state.modelId = 'danirai-research';
      updateModelButton();
    }
    if (mode === 'image') { state.modelId = 'danirai-image'; updateModelButton(); }
    if (mode === 'video') { state.modelId = 'danirai-video'; updateModelButton(); }
    if (mode === 'chat' && ['danirai-image', 'danirai-video', 'danirai-research'].includes(state.modelId)) {
      state.modelId = planAllows('danirai-1-pro') ? 'danirai-1-pro' : 'danirai-1v';
      updateModelButton();
    }
    renderModelMenu();
  }
  $$('#mode-chips .chip').forEach((c) => c.addEventListener('click', () => {
    const mode = c.dataset.mode;
    const need = { chat: null, image: 'danirai-image', video: 'danirai-video', research: 'danirai-research' }[mode];
    if (need && !planAllows(need)) {
      toast('Этот режим доступен на тарифе выше — смотрите «Тарифы» 💎');
      return;
    }
    setMode(mode);
  }));

  /* ---------------- отправка ---------------- */
  const input = $('#input');
  function autosize() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 200) + 'px'; }
  input.addEventListener('input', autosize);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#composer').requestSubmit(); }
  });
  $('#composer').addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || state.busy) return;
    input.value = '';
    autosize();
    state.busy = true;
    $('#btn-send').disabled = true;
    try {
      if (state.mode === 'image') await sendImage(text);
      else if (state.mode === 'video') await sendVideo(text);
      else if (state.mode === 'research') await sendResearch(text);
      else await sendChat(text);
    } catch (err) {
      toast(err.detail || err.message || 'Ошибка', 'err');
      appendError(err.detail || err.message);
    } finally {
      state.busy = false;
      $('#btn-send').disabled = false;
    }
  });

  async function ensureChat() {
    if (state.currentChat) return state.currentChat;
    const chat = await API.post('/api/chats', { model_id: state.modelId });
    state.currentChat = Object.assign({ messages: [] }, chat);
    await loadChats();
    return state.currentChat;
  }

  function removeWelcome() { const w = $('.welcome'); if (w) w.remove(); }

  async function sendChat(text) {
    const chat = await ensureChat();
    removeWelcome();
    const userMsg = { id: 'tmp' + Date.now(), role: 'user', content: text, created_at: new Date().toISOString(), attachments: [], sources: [] };
    $('#messages').insertAdjacentHTML('beforeend', messageHtml(userMsg));
    bindMessageActions($('#messages'));
    const aiRow = document.createElement('div');
    aiRow.className = 'msg-row ai';
    aiRow.innerHTML =
      '<div class="msg-avatar">D</div><div class="msg-body"><div class="msg-head"><b>DanirAI</b>' +
      '<span class="m-model">' + esc((modelById(state.modelId) || {}).name || '') + '</span></div>' +
      '<div class="reasoning live" id="live-think"><summary>Думаю…</summary><div class="r-body"></div></div>' +
      '<div class="msg-content"><span class="typing"><i></i><i></i><i></i></span></div></div>';
    $('#messages').appendChild(aiRow);
    scrollBottom();

    const contentEl = $('.msg-content', aiRow);
    let acc = '';
    try {
      await API.stream('/api/chats/' + chat.id + '/messages/stream', { content: text, model_id: state.modelId }, (ev) => {
        if (ev.type === 'delta') {
          acc += ev.text;
          contentEl.innerHTML = MD.render(acc) + '<span class="typing"><i></i><i></i><i></i></span>';
          scrollBottom();
        }
        if (ev.type === 'done') {
          const think = $('#live-think', aiRow);
          if (think) think.remove();
          contentEl.innerHTML = MD.render(ev.message.content);
          aiRow.dataset.id = ev.message.id;
          if (ev.message.reasoning) {
            contentEl.insertAdjacentHTML('beforebegin',
              '<details class="reasoning"><summary>Мышление DanirAI-1 PRO</summary><div class="r-body">' + esc(ev.message.reasoning) + '</div></details>');
          }
          bindMessageActions(aiRow);
          loadChats();
          scrollBottom();
        }
        if (ev.type === 'error') {
          const think = $('#live-think', aiRow);
          if (think) think.remove();
          contentEl.innerHTML = '<span style="color:var(--err)">⚠️ ' + esc(ev.message) + '</span>';
        }
      });
    } catch (err) {
      contentEl.innerHTML = '<span style="color:var(--err)">⚠️ ' + esc(err.detail || err.message) + '</span>';
    }
  }

  async function sendImage(text) {
    const chat = await ensureChat();
    removeWelcome();
    $('#messages').insertAdjacentHTML('beforeend', messageHtml({ id: 't', role: 'user', content: '🎨 ' + text, created_at: new Date().toISOString() }));
    const row = document.createElement('div');
    row.className = 'msg-row ai';
    row.innerHTML = '<div class="msg-avatar">D</div><div class="msg-body"><div class="msg-head"><b>DanirAI Image</b></div><div class="msg-content"><span class="typing"><i></i><i></i><i></i></span> Рисую…</div></div>';
    $('#messages').appendChild(row);
    scrollBottom();
    const r = await API.post('/api/images', { prompt: text, chat_id: chat.id, width: 1024, height: 1024 });
    $('.msg-content', row).innerHTML =
      '<p>Готово! Картинка по запросу «' + esc(text) + '»</p>' +
      '<div class="msg-media"><img src="' + r.generation.url + '" data-zoom="' + r.generation.url + '" alt=""></div>';
    bindMessageActions(row);
    loadChats();
    scrollBottom();
  }

  async function sendVideo(text) {
    const chat = await ensureChat();
    removeWelcome();
    $('#messages').insertAdjacentHTML('beforeend', messageHtml({ id: 't', role: 'user', content: '🎬 ' + text, created_at: new Date().toISOString() }));
    const row = document.createElement('div');
    row.className = 'msg-row ai';
    row.innerHTML =
      '<div class="msg-avatar">D</div><div class="msg-body"><div class="msg-head"><b>DanirAI Video</b></div>' +
      '<div class="msg-content"><div class="reasoning live"><summary>Создаю видео…</summary><div class="r-body" id="vstage">Постановка в очередь</div></div>' +
      '<div style="height:6px;background:#1a1e33;border-radius:6px;overflow:hidden;margin-top:8px"><div id="vbar" style="height:100%;width:5%;background:var(--grad);transition:width .6s"></div></div></div></div>';
    $('#messages').appendChild(row);
    scrollBottom();
    const job = await API.post('/api/videos', { prompt: text, chat_id: chat.id, duration: 4 });
    while (true) {
      await new Promise((r2) => setTimeout(r2, 4000));
      const st = await API.get('/api/videos/jobs/' + job.job_id);
      $('#vbar') && ($('#vbar').style.width = (st.progress || 5) + '%');
      if ($('#vstage')) $('#vstage').textContent = st.stage || '';
      if (st.status === 'done') {
        $('.msg-content', row).innerHTML =
          '<p>🎬 Видео готово (' + esc(st.format || 'mp4') + ', движок: ' + esc(st.engine || '') + ')</p>' +
          '<div class="msg-media"><video src="' + st.url + '" controls autoplay muted loop></video></div>';
        loadChats();
        break;
      }
      if (st.status === 'failed') {
        $('.msg-content', row).innerHTML = '<span style="color:var(--err)">⚠️ ' + esc(st.stage || 'Ошибка генерации') + '</span>';
        break;
      }
      scrollBottom();
    }
  }

  async function sendResearch(text) {
    const chat = await ensureChat();
    removeWelcome();
    $('#messages').insertAdjacentHTML('beforeend', messageHtml({ id: 't', role: 'user', content: '🔎 ' + text, created_at: new Date().toISOString() }));
    const row = document.createElement('div');
    row.className = 'msg-row ai';
    row.innerHTML =
      '<div class="msg-avatar">D</div><div class="msg-body"><div class="msg-head"><b>DanirAI Deep Research</b></div>' +
      '<div class="msg-content"><span class="typing"><i></i><i></i><i></i></span> Исследую интернет: ищу источники, читаю страницы, пишу отчёт… (это может занять 1–2 минуты)</div></div>';
    $('#messages').appendChild(row);
    scrollBottom();
    const r = await API.post('/api/research', { query: text, chat_id: chat.id, depth: 2, model_id: 'danirai-research' });
    $('.msg-content', row).innerHTML = MD.render(r.report);
    if (r.sources && r.sources.length) {
      $('.msg-content', row).insertAdjacentHTML('afterend',
        '<div class="sources">' + r.sources.map((s, i) => '<a class="source-chip" href="' + esc(s.url) + '" target="_blank" rel="noopener">🔗 <span>' + (i + 1) + '. ' + esc(s.title || s.url) + '</span></a>').join('') + '</div>');
    }
    loadChats();
    scrollBottom();
  }

  function appendError(detail) {
    removeWelcome();
    $('#messages').insertAdjacentHTML('beforeend',
      '<div class="msg-row ai"><div class="msg-avatar">!</div><div class="msg-body"><div class="msg-content" style="color:var(--err)">⚠️ ' + esc(detail || 'Ошибка') + '</div></div></div>');
    scrollBottom();
  }

  /* ---------------- галерея ---------------- */
  async function loadGallery() {
    const grid = $('#gallery-grid');
    grid.innerHTML = '<div class="g-empty"><div class="big"></div>Загружаю галерею…</div>';
    const [images, videos] = await Promise.all([
      API.get('/api/images').catch(() => []),
      API.get('/api/videos').catch(() => []),
    ]);
    const items = []
      .concat(videos.map((v) => Object.assign({ kind: 'video' }, v)))
      .concat(images.map((v) => Object.assign({ kind: 'image' }, v)))
      .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
    if (!items.length) {
      grid.innerHTML = '<div class="g-empty"><div class="big"></div>Здесь появятся ваши картинки и видео.<br>Переключитесь в режим «Картинка» или «Видео» и опишите сцену.</div>';
      return;
    }
    grid.innerHTML = items.map((it) =>
      '<div class="g-card"><div class="g-media">' +
      (it.kind === 'video' ? '<video src="' + it.url + '" controls preload="metadata"></video>' : '<img src="' + it.url + '" loading="lazy" data-zoom="' + it.url + '" alt="">') +
      '</div><div class="g-info"><p>' + esc(it.prompt || '') + '</p><time>' + fmtTime(it.created_at) + ' • ' + it.kind + '</time></div></div>'
    ).join('');
    bindMessageActions(grid);
  }
  $('#btn-refresh-gallery').addEventListener('click', loadGallery);

  /* ---------------- research-вкладка ---------------- */
  $('#btn-research').addEventListener('click', async () => {
    const q = $('#research-input').value.trim();
    if (!q) return toast('Опишите тему исследования');
    const box = $('#research-result');
    box.innerHTML = '<div class="r-steps"><div class="r-step"><span class="dot"></span><div><b>Исследование запущено…</b><div class="det">Ищу источники и читаю страницы, подождите 1–2 минуты</div></div></div></div>';
    $('#btn-research').disabled = true;
    try {
      const r = await API.post('/api/research', { query: q, depth: +$('#research-depth').value, model_id: 'danirai-research' });
      box.innerHTML =
        '<div class="r-steps">' + r.steps.map((s) =>
          '<div class="r-step"><span class="dot"></span><div><b>' + esc(s.title) + '</b>' + (s.detail ? '<div class="det">' + esc(s.detail) + '</div>' : '') + '</div></div>'
        ).join('') + '</div>' +
        '<div class="r-report msg-content">' + MD.render(r.report) + '</div>' +
        '<div class="sources" style="margin-top:16px">' + r.sources.map((s, i) =>
          '<a class="source-chip" href="' + esc(s.url) + '" target="_blank" rel="noopener">🔗 <span>' + (i + 1) + '. ' + esc(s.title || s.url) + '</span></a>').join('') + '</div>';
      toast('Исследование готово ✅', 'ok');
    } catch (err) {
      box.innerHTML = '<div class="r-report" style="color:var(--err)">⚠️ ' + esc(err.detail || err.message) + '</div>';
    } finally { $('#btn-research').disabled = false; }
  });

  /* ---------------- тарифы ---------------- */
  async function loadPlans() {
    let data;
    try { data = await API.get('/api/billing/plans'); } catch (e) { data = { plans: state.plans || [] }; }
    state.plans = data.plans;
    $('#plans-grid').innerHTML = data.plans.map(planCardHtml).join('');
    $$('#plans-grid [data-plan]').forEach((b) => b.addEventListener('click', () => openPayment(b.dataset.plan)));
    const pays = await API.get('/api/billing/payments').catch(() => []);
    $('#payments-list').innerHTML = pays.length
      ? pays.map((p) =>
          '<div class="pay-row"><span>' + esc(p.plan_id.toUpperCase()) + ' • ' + p.amount.toLocaleString('ru-RU') + ' ' + esc(p.currency) + '</span>' +
          '<span style="color:var(--faint)">' + fmtTime(p.created_at) + '</span>' +
          '<span class="pay-status ' + p.status + '">' + p.status.toUpperCase() + '</span></div>'
        ).join('')
      : '<div style="color:var(--faint);font-size:13px">Платежей пока не было.</div>';
  }

  async function openPayment(planId) {
    const plan = (state.plans || []).find((p) => p.id === planId);
    if (!plan) return;
    if (plan.price === 0) {
      // возврат на Free — просто информируем
      toast('Вернуться на Free можно после окончания подписки');
      return;
    }
    $('#payment-body').innerHTML =
      '<div class="pay-summary">' +
      '<div class="row"><span>Тариф</span><b>' + esc(plan.name) + '</b></div>' +
      '<div class="row"><span>Период</span><span>30 дней</span></div>' +
      '<div class="row"><span>Модели</span><span>' + plan.models.length + ' шт.</span></div>' +
      '<div class="row total"><span>Итого</span><span>' + esc(plan.price_label) + '</span></div>' +
      '</div>' +
      '<div class="pay-methods">' +
      ['💳 Банковская карта (Kaspi / Visa / MC)', '📱 Kaspi QR', '🏦 Безнал для бизнеса'].map((m, i) =>
        '<div class="pay-method' + (i === 0 ? ' sel' : '') + '" data-m="' + i + '">' + m + '</div>').join('') +
      '</div>' +
      '<button class="btn btn-primary btn-big" id="btn-pay-confirm">Оплатить ' + esc(plan.price_label) + '</button>' +
      '<div class="pay-note">Демо-режим оплаты: платёж подтверждается мгновенно. Для приёма настоящих денег подключите провайдер в .env: PAYMENT_PROVIDER=kassa и PAYMENT_SECRET=… (вебхук: /api/billing/webhook).</div>';
    $('#modal-payment').classList.remove('hidden');
    $$('.pay-method').forEach((m) => m.addEventListener('click', () => {
      $$('.pay-method').forEach((x) => x.classList.remove('sel'));
      m.classList.add('sel');
    }));
    $('#btn-pay-confirm').onclick = async () => {
      $('#btn-pay-confirm').disabled = true;
      $('#btn-pay-confirm').textContent = 'Проводим оплату…';
      try {
        const ch = await API.post('/api/billing/checkout', { plan_id: planId, payment_method: 'card' });
        await new Promise((r) => setTimeout(r, 900));
        const res = await API.get(ch.confirm_url);
        $('#modal-payment').classList.add('hidden');
        state.user = await API.get('/api/auth/me');
        renderUserChip();
        renderModelMenu();
        loadPlans();
        toast(res.message || 'Тариф активирован!', 'ok');
      } catch (err) {
        toast(err.detail || 'Ошибка оплаты', 'err');
        $('#btn-pay-confirm').disabled = false;
        $('#btn-pay-confirm').textContent = 'Повторить оплату';
      }
    };
  }

  /* ---------------- профиль ---------------- */
  $('#btn-profile').addEventListener('click', openProfile);
  async function openProfile() {
    const u = state.user;
    const av = $('#profile-avatar');
    av.textContent = (u.display_name || u.email)[0].toUpperCase();
    av.style.backgroundImage = u.avatar_url ? 'url(' + u.avatar_url + ')' : '';
    $('#profile-name').value = u.display_name || '';
    $('#profile-bio').value = u.bio || '';
    $('#profile-pass').value = '';
    $('#modal-profile').classList.remove('hidden');
    try {
      const plans = await API.get('/api/billing/plans');
      const usage = plans.usage_today || {};
      const limit = plans.current.plan.messages_per_day;
      $('#profile-stats').innerHTML =
        '<div><b>' + (usage.messages || 0) + '</b><span>сообщений сегодня' + (limit > 0 ? ' / ' + limit : '') + '</span></div>' +
        '<div><b>' + (usage.images || 0) + '</b><span>картинок</span></div>' +
        '<div><b>' + (usage.videos || 0) + '</b><span>видео</span></div>' +
        '<div><b>' + (state.chats.length || 0) + '</b><span>чатов</span></div>';
    } catch (e) {}
    loadKeys();
  }
  $('#btn-save-profile').addEventListener('click', async () => {
    const body = { display_name: $('#profile-name').value, bio: $('#profile-bio').value };
    if ($('#profile-pass').value) body.password = $('#profile-pass').value;
    try {
      state.user = Object.assign(state.user, await API.patch('/api/auth/me', body));
      renderUserChip();
      toast('Профиль сохранён ✅', 'ok');
      $('#modal-profile').classList.add('hidden');
    } catch (err) { toast(err.detail || 'Ошибка', 'err'); }
  });
  $('#avatar-file').addEventListener('change', async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    const form = new FormData();
    form.append('file', f);
    try {
      const r = await API.upload('/api/auth/me/avatar', form);
      state.user.avatar_url = r.avatar_url;
      renderUserChip();
      openProfile();
      toast('Аватар обновлён 📸', 'ok');
    } catch (err) { toast(err.detail || 'Ошибка загрузки', 'err'); }
  });
  $('#btn-avatar-gen').addEventListener('click', async (e) => {
    e.target.disabled = true;
    e.target.textContent = 'Генерирую…';
    try {
      const r = await API.post('/api/auth/me/avatar/generate', {});
      state.user.avatar_url = r.avatar_url;
      renderUserChip();
      openProfile();
      toast('Аватар сгенерирован нейросетью ✨', 'ok');
    } catch (err) { toast(err.detail || 'Ошибка генерации', 'err'); }
    e.target.disabled = false;
    e.target.textContent = '✨ Сгенерировать аватар';
  });
  $('#btn-logout').addEventListener('click', async () => {
    await API.post('/api/auth/logout', {}).catch(() => {});
    API.store.token = '';
    location.reload();
  });

  async function loadKeys() {
    const keys = await API.get('/api/keys').catch(() => []);
    $('#keys-list').innerHTML = keys.length
      ? keys.map((k) => '<div class="key-row"><span>' + esc(k.name) + ' <code>' + esc(k.prefix) + '…</code></span><button class="icon-btn" data-key-del="' + k.id + '" title="Удалить">🗑</button></div>').join('')
      : '<div style="color:var(--faint);font-size:12.5px;margin-bottom:6px">Ключей нет. Создайте, чтобы обращаться к DanirAI из своих программ.</div>';
    $$('[data-key-del]').forEach((b) => (b.onclick = async () => {
      await API.del('/api/keys/' + b.dataset.keyDel).catch(() => {});
      loadKeys();
    }));
  }
  $('#btn-key-create').addEventListener('click', async () => {
    try {
      const r = await API.post('/api/keys', { name: $('#key-name').value || 'default' });
      $('#key-secret').classList.remove('hidden');
      $('#key-secret').textContent = r.api_key + '\n\n' + r.warning;
      $('#key-name').value = '';
      loadKeys();
    } catch (err) { toast(err.detail || 'Ошибка', 'err'); }
  });

  /* ---------------- админ ---------------- */
  async function loadAdmin() {
    const wrap = $('#admin-wrap');
    try {
      const s = await API.get('/api/admin/stats');
      const users = await API.get('/api/admin/users');
      const pays = await API.get('/api/admin/payments');
      wrap.innerHTML =
        '<div class="stat-grid">' +
        '<div class="stat-card"><b>' + s.users.total + '</b><span>пользователей</span></div>' +
        '<div class="stat-card"><b>' + s.users.active_7d + '</b><span>активных за 7 дней</span></div>' +
        '<div class="stat-card"><b>' + s.messages + '</b><span>сообщений всего</span></div>' +
        '<div class="stat-card"><b>' + s.assets + '</b><span>картинок и видео</span></div>' +
        '<div class="stat-card"><b>' + (s.revenue_kzt || 0).toLocaleString('ru-RU') + ' ₸</b><span>выручка</span></div>' +
        '</div>' +
        '<div class="admin-table"><table><thead><tr><th>Пользователь</th><th>Тариф</th><th>Чатов</th><th>Сообщ. сегодня</th><th>Регистрация</th><th>Управление</th></tr></thead><tbody>' +
        users.map((u) =>
          '<tr><td><b>' + esc(u.display_name || u.email) + '</b><br><span style="color:var(--faint);font-size:12px">' + esc(u.email) + (u.is_admin ? ' 🛡' : '') + '</span></td>' +
          '<td><span class="tier-badge ' + u.tier + '">' + tierBadge(u.tier) + '</span></td>' +
          '<td>' + u.chats + '</td><td>' + u.messages_today + '</td><td style="color:var(--faint)">' + fmtTime(u.created_at) + '</td>' +
          '<td><select data-tier-for="' + u.id + '"><option value="free"' + (u.tier === 'free' ? ' selected' : '') + '>Free</option><option value="plus"' + (u.tier === 'plus' ? ' selected' : '') + '>Plus</option><option value="pro"' + (u.tier === 'pro' ? ' selected' : '') + '>Pro</option></select></td></tr>'
        ).join('') +
        '</tbody></table></div>' +
        '<div class="payments-block"><h3>Платежи платформы</h3><div class="payments-list">' +
        (pays.length ? pays.map((p) => '<div class="pay-row"><span>' + esc(p.user) + ' → ' + esc(p.plan_id.toUpperCase()) + '</span><span>' + p.amount.toLocaleString('ru-RU') + ' ₸</span><span class="pay-status ' + p.status + '">' + p.status + '</span></div>').join('') : '<div style="color:var(--faint);font-size:13px">Платежей нет.</div>') +
        '</div></div>';
      $$('select[data-tier-for]', wrap).forEach((sel) => (sel.onchange = async () => {
        await API.patch('/api/admin/users/' + sel.dataset.tierFor, { tier: sel.value }).catch((e) => toast(e.detail, 'err'));
        toast('Тариф пользователя изменён', 'ok');
      }));
    } catch (err) {
      wrap.innerHTML = '<div style="color:var(--err);padding:30px">⚠️ ' + esc(err.detail || 'Нет доступа') + '</div>';
    }
  }
  $('#btn-admin-refresh').addEventListener('click', loadAdmin);

  /* ---------------- модалки: закрытие ---------------- */
  $$('.modal-backdrop').forEach((m) => {
    m.addEventListener('click', (e) => { if (e.target === m) m.classList.add('hidden'); });
    $('.modal-close', m).addEventListener('click', () => m.classList.add('hidden'));
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') $$('.modal-backdrop').forEach((m) => m.classList.add('hidden'));
  });

  boot();
})();
