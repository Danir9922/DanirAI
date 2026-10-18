/* Клиент API DanirAI. */
(function (global) {
  const store = {
    get token() { return localStorage.getItem('danirai_token') || ''; },
    set token(v) { v ? localStorage.setItem('danirai_token', v) : localStorage.removeItem('danirai_token'); },
  };

  class ApiError extends Error {
    constructor(status, detail) { super(detail); this.status = status; this.detail = detail; }
  }

  async function request(path, opts = {}) {
    const headers = Object.assign({}, opts.headers || {});
    if (store.token) headers['Authorization'] = 'Bearer ' + store.token;
    if (opts.body !== undefined && !(opts.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    let res;
    try {
      res = await fetch(path, Object.assign({ headers }, opts));
    } catch (e) {
      throw new ApiError(0, 'Сервер DanirAI недоступен. Убедитесь, что бэкенд запущен (uvicorn app.main:app).');
    }
    if (res.status === 401 && !path.includes('/auth/login') && !path.includes('/auth/register')) {
      store.token = '';
      global.dispatchEvent(new CustomEvent('danirai:unauthorized'));
    }
    let data = null;
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('json')) data = await res.json().catch(() => null);
    else data = { text: await res.text() };
    if (!res.ok) {
      const detail = (data && (data.detail || data.message)) || ('Ошибка ' + res.status);
      throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    return data;
  }

  // SSE-поток для стриминга ответов
  async function stream(path, body, handlers) {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + store.token },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      const data = await res.json().catch(() => ({}));
      throw new ApiError(res.status, (data && data.detail) || 'Ошибка потока');
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const line = chunk.replace(/^data:\s?/, '');
        if (!line) continue;
        try { handlers(JSON.parse(line)); } catch (e) { /* skip */ }
      }
    }
  }

  global.DanirAPI = {
    store,
    ApiError,
    get: (p) => request(p),
    post: (p, body) => request(p, { method: 'POST', body }),
    patch: (p, body) => request(p, { method: 'PATCH', body }),
    del: (p) => request(p, { method: 'DELETE' }),
    upload: (p, form) => request(p, { method: 'POST', body: form }),
    stream,
  };
})(window);
