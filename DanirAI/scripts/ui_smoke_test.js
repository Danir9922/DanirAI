/* Смоук-тест фронтенда DanirAI в jsdom против живого сервера.
   Запуск: node scripts/ui_smoke_test.js  (нужен запущенный бэкенд на :8000
   и установленный jsdom: npm i --prefix /tmp/domtest jsdom) */
const { JSDOM } = require('/tmp/domtest/node_modules/jsdom');

const BASE = process.env.DANIRAI_TEST_URL || 'http://127.0.0.1:8000';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const html = await (await fetch(BASE + '/')).text();
  const dom = new JSDOM(html, {
    url: BASE + '/',
    runScripts: 'dangerously',
    resources: "usable",
    pretendToBeVisual: true,
  });
  const { window } = dom;
  const { document } = window;

  // проксируем fetch окна на реальный сервер (относительные пути)
  window.fetch = async (path, opts) => {
    const url = typeof path === 'string' && path.startsWith('http') ? path : BASE + path;
    return fetch(url, opts);
  };
  window.HTMLMediaElement.prototype.play = () => Promise.resolve();
  window.scrollTo = () => {};
  window.confirm = () => true;

  const errors = [];
  window.addEventListener('error', (e) => errors.push('window error: ' + e.message));

  await new Promise((res) => {
    if (document.readyState === 'complete') return res();
    window.addEventListener('load', res);
  });
  await sleep(1500);

  const visible = (sel) => !document.querySelector(sel).classList.contains('hidden');
  console.log('BOOT hidden:', visible('#boot') ? 'no(!)' : 'yes');
  console.log('AUTH screen visible:', visible('#screen-auth'));

  // --- регистрация через форму ---
  const email = 'ui_' + Date.now() + '@test.kz';
  document.querySelector('#form-register [name=display_name]').value = 'UI Тест';
  document.querySelector('#form-register [name=email]').value = email;
  document.querySelector('#form-register [name=password]').value = 'secret123';
  document.querySelector('#form-register').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await sleep(2500);

  console.log('APP visible after register:', visible('#app'));
  console.log('USER chip name:', document.querySelector('#user-name').textContent);
  console.log('TIER badge:', document.querySelector('#user-tier').textContent);

  // --- отправка сообщения в чат ---
  document.querySelector('#input').value = 'Привет, DanirAI! Расскажи, что ты умеешь?';
  document.querySelector('#composer').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }));
  await sleep(20000);

  const rows = document.querySelectorAll('.msg-row');
  console.log('MESSAGE ROWS:', rows.length);
  const last = rows[rows.length - 1];
  console.log('AI ANSWER PREVIEW:', (last ? last.querySelector('.msg-content').textContent.slice(0, 140) : 'none').replace(/\s+/g, ' '));
  console.log('AI row html len:', last ? last.innerHTML.length : 0, '| reasoning?', last ? !!last.querySelector('.reasoning') : false);

  // --- чат появился в сайдбаре ---
  console.log('CHAT LIST items:', document.querySelectorAll('.chat-item').length);

  // --- открытие профиля ---
  document.querySelector('#btn-profile').click();
  await sleep(1200);
  console.log('PROFILE modal open:', visible('#modal-profile') ? 'yes' : 'no');
  console.log('PROFILE stats html len:', document.querySelector('#profile-stats').innerHTML.length);
  document.querySelector('#modal-profile').classList.add('hidden');

  // --- тарифы ---
  document.querySelector('.side-tab[data-view=plans]').click();
  await sleep(1500);
  console.log('PLAN CARDS:', document.querySelectorAll('#plans-grid .plan-card').length);

  // --- оплата Plus через UI ---
  const plusBtn = document.querySelector('#plans-grid [data-plan=plus]');
  if (plusBtn) {
    plusBtn.click();
    await sleep(600);
    console.log('PAYMENT modal:', visible('#modal-payment') ? 'yes' : 'no');
    document.querySelector('#btn-pay-confirm').click();
    await sleep(3500);
    console.log('TIER after pay:', document.querySelector('#user-tier').textContent);
  }

  // --- модель PRO теперь доступна ---
  document.querySelector('#model-btn').click();
  await sleep(300);
  const locked = document.querySelectorAll('#model-menu .model-lock').length;
  console.log('LOCKED models now:', locked);

  console.log('JS ERRORS:', errors.length ? errors : 'none');
  window.close();
  process.exit(0);
}

main().catch((e) => { console.error('TEST FAILED', e); process.exit(1); });
