# 🤖 DanirAI

**DanirAI** — полноценная AI-платформа «как ChatGPT и Gemini», но со своим характером:
собственные модели, профили пользователей, личные чаты, тарифы с оплатой, генерация
картинок и видео, глубокое исследование интернета и автономный агент.

> Сделано с нуля: бэкенд (Python + FastAPI), фронтенд (vanilla JS, без сборщиков),
> база данных, провайдеры моделей, агент с инструментами и платёжная система.

---

## ✨ Что умеет

| Возможность | Описание |
|---|---|
| 💬 Чаты | У каждого пользователя **своя история чатов** (полная изоляция), стриминг ответов, закрепление, поиск, переименование, публичные ссылки |
| 🧠 Мышление | Модель **DanirAI-1 PRO** показывает цепочку рассуждений («мысли») перед ответом |
| 🔎 Deep Research | Агент сам составляет план, ищет в интернете (DuckDuckGo/SearXNG/Brave), читает страницы и пишет отчёт с источниками |
| 🤖 Agent | Автономный агент с инструментами: поиск, чтение страниц, калькулятор, рисование, время (function calling + ReAct) |
| 🎨 Картинки | Генерация изображений по промпту (FLUX / DALL·E), галерея работ |
| 🎬 Видео | Настоящее видео: раскадровка → нейрокадры → Ken Burns-анимация → кодирование в **MP4 (ffmpeg)** |
| 👤 Профили | Аватар (загрузка или генерация нейросетью), имя, био, бейдж тарифа, статистика |
| 💎 Тарифы | Free / **Plus 9 990 ₸** / **Pro 50 000 ₸** с лимитами, оплата (демо-режим + вебхуки для боевых провайдеров) |
| 🛡 Админка | Статистика платформы, выручка, управление тарифами пользователей |
| 🔑 API-ключи | Личные ключи `dnr_...` + **OpenAI-совместимый API** `/v1/chat/completions` |
| 🔊 Озвучка | Кнопка «Озвучить» (Web Speech API) |

## 🧬 Модели DanirAI

| Модель | Тип | Тариф | Характер |
|---|---|---|---|
| ⚡ **DanirAI-1v** | чат | Free | Первая модель: отвечает быстро и по делу |
| 🧠 **DanirAI-1 PRO** | чат + reasoning | Plus | Глубоко думает: цепочка рассуждений, затем ответ |
| 🔎 **DanirAI Deep Research** | исследование | Pro | Ищет в интернете, читает источники, пишет отчёт |
| 🤖 **DanirAI Agent** | агент | Pro | Сам выбирает инструменты и решает задачу пошагово |
| 🎨 **DanirAI Image** | изображения | Plus | Рисует по описанию |
| 🎬 **DanirAI Video** | видео | Pro | Создаёт видеоролики |

Модели — это «лица» платформы: под капотом подключается любой провайдер
(OpenAI-совместимый API, бесплатный Pollinations или офлайн Local Brain),
а пользователь видит единый бренд DanirAI.

## 💎 Тарифы

| | Free | Plus — 9 990 ₸/мес | Pro — 50 000 ₸/мес |
|---|---|---|---|
| Сообщений в день | 50 | 1 000 | ∞ |
| DanirAI-1v | ✅ | ✅ | ✅ |
| DanirAI-1 PRO | — | ✅ | ✅ |
| Картинки | 3/день | 200/день | ∞ |
| Deep Research + Agent | — | — | 30/день |
| Видео | — | — | 20/день |

Цены задаются в `backend/app/config.py` (секция `PLANS`) — поменяйте под себя.
Оплата сейчас в демо-режиме (`PAYMENT_PROVIDER=mock`): платёж создаётся и
подтверждается подписанным вебхуком. Для боевых денег подключите свой провайдер
(Kaspi/CloudPayments/Stripe): реализуйте ссылку в `/api/billing/checkout`
и принимайте уведомления на `/api/billing/webhook` (подпись HMAC уже проверяется).

---

## 🚀 Быстрый старт

Требования: Python 3.10+, интернет (для нейросети и поиска).

```bash
git clone https://github.com/ВАШ_НИК/DanirAI.git
cd DanirAI

# 1. зависимости
pip install -r backend/requirements.txt
pip install imageio-ffmpeg pillow      # ffmpeg для видео + обработка картинок

# 2. настройки (необязательно — всё работает и без ключей)
cp .env.example .env
#    OPENAI_API_KEY=sk-...   ← включит полноценную нейросеть уровня ChatGPT

# 3. запуск
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Откройте **http://localhost:8000** → зарегистрируйтесь → пользуйтесь.
Первый зарегистрированный пользователь становится **администратором**.

Интерактивная документация API: **http://localhost:8000/docs**

### Docker

```bash
docker compose up --build
# → http://localhost:8000
```

### Как работает «мозг» без ключей

DanirAI пробует провайдеров по цепочке и всегда отвечает:

```
OpenAI-совместимый API (если OPENAI_API_KEY)
        ↓ ошибка
Pollinations.ai (бесплатная нейросеть + FLUX-картинки)
        ↓ нет интернета
Local Brain (офлайн: математика, код, диалог)
```

---

## 🔌 API за 30 секунд

```bash
# зарегистрироваться
curl -X POST http://localhost:8000/api/auth/register \
     -H 'Content-Type: application/json' \
     -d '{"email":"me@mail.com","password":"secret123","display_name":"Danir"}'

# создать чат и спросить (токен из ответа выше)
curl -X POST http://localhost:8000/api/chats \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"model_id":"danirai-1v"}'

curl -X POST http://localhost:8000/api/chats/$CHAT_ID/messages \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"content":"Привет, DanirAI!","model_id":"danirai-1v"}'

# картинка / видео / исследование
curl -X POST http://localhost:8000/api/images   -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"prompt":"закат в горах Алматы"}'
curl -X POST http://localhost:8000/api/videos   -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"prompt":"дрон над ночным городом","duration":4}'
curl -X POST http://localhost:8000/api/research -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"query":"рынок электромобилей 2026","depth":2}'
```

### OpenAI-совместимый доступ

Создайте ключ в профиле («🔑 API-ключи») и используйте DanirAI из любых клиентов:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer dnr_ВАШ_КЛЮЧ" -H 'Content-Type: application/json' \
  -d '{"model":"danirai-1-pro","messages":[{"role":"user","content":"Привет!"}]}'
```

---

## 🏗 Архитектура

```
DanirAI/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI-приложение, OpenAI-совместимый шлюз, SPA
│   │   ├── config.py          # модели, тарифы, провайдеры, .env
│   │   ├── database.py        # SQLAlchemy (SQLite по умолчанию, любой SQL)
│   │   ├── models.py          # User, Chat, Message, UsageLog, Payment, Asset, ApiKey
│   │   ├── schemas.py         # Pydantic-схемы
│   │   ├── security.py        # bcrypt/pbkdf2 пароли, подписанные токены
│   │   ├── deps.py            # auth, тарифы, дневные лимиты
│   │   ├── providers/         # openai / pollinations / local_brain / search / video
│   │   ├── agent/             # tools.py (инструменты), research.py, runner.py
│   │   ├── services/          # image_service (хранение медиа)
│   │   └── routers/           # auth, chat, generation, research, billing, keys, admin
│   └── requirements.txt
├── frontend/                  # SPA без сборщиков: index.html + css + js
│   ├── index.html
│   ├── css/style.css          # тёмная «неоновая» тема
│   └── js/                    # api.js, markdown.js, app.js
├── data/                      # SQLite + media/ (аватары, картинки, видео)
├── scripts/                   # run.sh, setup.sh, ui_smoke_test.js
├── .github/workflows/ci.yml   # авто-тесты при пуше
├── Dockerfile, docker-compose.yml
└── README.md
```

**Изоляция данных:** каждый чат и каждое сообщение привязаны к `user_id`;
API отдаёт 404 на чужие чаты. Лимиты считаются по `usage_logs` за день (UTC).

## 🧪 Тесты

```bash
cd backend && python -m pytest -q          # unit-тесты API
node scripts/ui_smoke_test.js              # E2E фронтенда в jsdom (нужен запущенный сервер)
```

## 🗺 Дорожная карта

- [x] Чаты, стриминг, профили, аватары, тарифы, картинки, видео, research, агент, админка
- [ ] Боевые платёжные провайдеры (Kaspi Pay, CloudPayments, Stripe)
- [ ] Голосовой ввод и TTS на сервере
- [ ] Мобильные приложения (обёртка поверх API)
- [ ] Обучение собственной модели DanirAI-2 (fine-tune)
- [ ] Командные пространства и общие чаты

## 📄 Лицензия

MIT — используйте свободно, коммерчески и с любовью. © DanirAI
