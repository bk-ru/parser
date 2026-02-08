# OPERATIONS

Краткий runbook для эксплуатации `site-parser`.

## 1. Локальный запуск (CLI)

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
# .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
site-parser https://www.iana.org/contact --pretty
```

## 2. Локальный запуск (API + UI)

Терминал 1:

```bash
site-parser-api
```

Терминал 2:

```bash
cd frontend
npm install
npm run dev
```

Проверка:
- UI: `http://127.0.0.1:5173`
- Swagger: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/api/health`

## 3. Продакшен (Docker Compose)

1. Создайте файл `.env.production` на основе `.env.production.example`.

Windows (PowerShell):

```powershell
Copy-Item .env.production.example .env.production
```

Linux/macOS (bash):

```bash
cp .env.production.example .env.production
```

2. Запустите сервис:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
```

3. Проверьте API:

```bash
curl http://127.0.0.1:8000/api/health
```

4. Просмотр логов и остановка:

```bash
docker logs -f site-parser-prod
docker compose -f docker-compose.prod.yml down
```

## 4. Продакшен без Docker

1. Соберите UI:

```bash
cd frontend
npm ci
npm run build
```

2. Запустите API:

```bash
site-parser-api
```

3. Рекомендуемые параметры окружения:

- `SITE_PARSER_API_HOST=0.0.0.0`
- `SITE_PARSER_API_RELOAD=false`
- `SITE_PARSER_API_WORKERS=2` (или выше по CPU)

## 5. Переменные API-сервера

| Переменная | По умолчанию | Назначение |
| --- | ---: | --- |
| `SITE_PARSER_API_HOST` | `127.0.0.1` | Хост API-сервера |
| `SITE_PARSER_API_PORT` | `8000` | Порт API-сервера |
| `SITE_PARSER_API_WORKERS` | `1` | Число worker-процессов Uvicorn |
| `SITE_PARSER_API_RELOAD` | `false` | Автоперезапуск в dev (`1/true/yes/on`) |
| `SITE_PARSER_TRUSTED_HOSTS` | `127.0.0.1,localhost` | Разрешённые `Host` заголовки |
| `SITE_PARSER_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | Разрешённые CORS origin |

## 6. Диагностика

### API не отвечает
- Проверьте контейнер: `docker ps`.
- Проверьте логи: `docker logs site-parser-prod`.
- Проверьте, что порт `8000` не занят другим процессом.

### Веб-интерфейс показывает ошибки прокси
- Убедитесь, что API запущен (`site-parser-api` или Docker-сервис).
- Для dev-режима убедитесь, что frontend работает на `5173`.

### Пустой результат парсинга
- Увеличьте `PARSER_MAX_DEPTH` и `PARSER_MAX_PAGES`.
- Увеличьте `PARSER_MAX_SECONDS` для больших сайтов.
- Проверьте доступность сайта и таймаут `PARSER_REQUEST_TIMEOUT`.
