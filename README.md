
# site-parser

`site-parser` обходит страницы сайта **в пределах одного домена** и извлекает контактные данные: **адреса электронной почты** и **телефонные номера**.

Требуется Python 3.12+.

![Скриншот 1](imgs/hero.png)

## Установка (виртуальное окружение + pip)

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
```

Linux/macOS (bash):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Запуск

```powershell
site-parser https://sotohit.ru/
```

```powershell
site-parser https://www.iana.org/contact --pretty
```

```powershell
site-parser https://www.iana.org/contact --config parser.example.toml --pretty
```

Пример формата вывода:

```json
{
  "url": "https://example.com",
  "emails": ["info@example.com", "..."],
  "phones": ["+14155552671", "..."]
}
```

## Использование

### Интерфейс командной строки

```powershell
site-parser https://www.iana.org/contact
site-parser https://sotohit.ru/
site-parser https://xn--c1akpdiz.xn--80adxhks/yuristy-moskvy/371-advokaty-yuristy-butovo.html
```

Опции:

```powershell
site-parser https://www.iana.org/contact --pretty
site-parser https://www.iana.org/contact --log-level DEBUG
site-parser https://www.iana.org/contact --config parser.example.toml
```

- `--pretty` — печатает JSON с отступами (удобно для чтения).
- `--config` — путь к файлу конфигурации (TOML/JSON), пример: `parser.example.toml`.
- `--log-level` — уровень логирования (DEBUG/INFO/WARNING/ERROR).

Только текущая страница (без обхода ссылок):

```powershell
$env:PARSER_MAX_DEPTH = '0'
$env:PARSER_MAX_PAGES = '1'
site-parser https://www.iana.org/contact
```

### Python API

```python
from site_parser import parse_site

result = parse_site("https://www.iana.org/contact")
print(result["url"], len(result["emails"]), len(result["phones"]))
```

## Конфигурация

Настройки можно задавать:

* через файл конфигурации (**parser.example.toml**)
* через переменные окружения.

### Переменные окружения

| Переменная                             |        По умолчанию | Описание                                                               |
| -------------------------------------- | ------------------: | ---------------------------------------------------------------------- |
| `PARSER_MAX_SECONDS`                   |              `30.0` | Лимит времени обхода, сек.                                             |
| `PARSER_MAX_DEPTH`                     |                 `0` | Максимальная глубина обхода (0 — только стартовая страница)            |
| `PARSER_MAX_PAGES`                     |               `200` | Максимальное количество страниц в обходе                               |
| `PARSER_MAX_LINKS_PER_PAGE`            |               `200` | Максимальное количество ссылок, обрабатываемых с одной страницы        |
| `PARSER_MAX_BODY_BYTES`                |           `2000000` | Максимальный размер тела ответа, байт                                  |
| `PARSER_MAX_CONCURRENCY`               |                 `4` | Уровень параллелизма: число одновременных HTTP-запросов                |
| `PARSER_PHONE_REGIONS`                 |       *(не задано)* | Регионы для разборa локальных телефонов (через запятую), напр. `RU,BY` |
| `PARSER_EMAIL_DOMAIN_ALLOWLIST`        |       *(не задано)* | Белый список доменов e-mail (через запятую), напр. `gmail.com,mail.ru` |
| `PARSER_FOCUSED_CRAWLING`              |              `true` | Фокусированный обход: приоритизация «контактных» страниц               |
| `PARSER_REQUEST_TIMEOUT`               |              `10.0` | Таймаут HTTP-запроса, сек.                                             |
| `PARSER_RETRY_TOTAL`                   |                 `2` | Количество повторных попыток HTTP-запроса                              |
| `PARSER_RETRY_BACKOFF_FACTOR`          |               `0.5` | Коэффициент задержки между повторами (backoff)                         |
| `PARSER_USER_AGENT`                    | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36` | Значение заголовка `User-Agent`                                        |
| `PARSER_INCLUDE_QUERY`                 |             `false` | Учитывать параметры строки запроса (`?a=b`) при нормализации URL       |
| `PARSER_LOG_LEVEL`                     |              `INFO` | Уровень логирования                                                    |
| `PARSER_CONFIG_FILE` / `PARSER_CONFIG` |       *(не задано)* | Путь к файлу конфигурации (если не используете `--config`)             |

## Как это работает

1. Нормализуется `start_url`, вычисляется базовый домен; обход ограничивается этим доменом.
2. При включённом фокусированном обходе URL ранжируются по эвристикам: «контактные» разделы выше, документация/архивы ниже.
3. Страницы загружаются параллельно пулом потоков с таймаутом, повторными попытками и увеличивающейся задержкой между повторами, а также с ограничением размера ответа.
4. HTML разбирается через BeautifulSoup; контакты извлекаются из текста и ссылок.
5. Ссылки приводятся к абсолютному виду, нормализуются и добавляются в очередь до достижения лимитов.
6. Контакты дедуплицируются и сортируются перед выдачей результата.

## Ограничения

* Некоторые сайты блокируют ботов, требуют выполнения JavaScript или отдают контент только после рендеринга — такой контент парсер может не увидеть.

## Тесты

```powershell
pytest
```

Тесты проверяют базовые сценарии: ограничение домена, извлечение e-mail/телефонов, фокусированный обход, чтение конфигурации (файл/env), фильтрацию e-mail по белому списку.

## License

Проект распространяется под лицензией MIT. См. файл [LICENSE](LICENSE) для подробностей.
