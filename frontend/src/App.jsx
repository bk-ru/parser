import { useMemo, useState } from "react";

const EXAMPLES = [
  "https://www.iana.org/contact",
  "https://www.icann.org/contact",
  "https://xn--c1akpdiz.xn--80adxhks/yuristy-moskvy/371-advokaty-yuristy-butovo.html"
];

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

const DEFAULT_ADVANCED = {
  maxDepth: "",
  maxPages: "",
  maxSeconds: "",
  maxConcurrency: "",
  requestTimeout: "",
  maxLinksPerPage: "",
  maxBodyBytes: "",
  retryTotal: "",
  phoneRegions: "",
  emailDomainAllowlist: "",
  userAgent: "",
  focusedCrawling: "",
  includeQuery: ""
};

function buildApiUrl(path) {
  return API_BASE ? `${API_BASE}${path}` : path;
}

function toErrorMessage(error) {
  if (error instanceof TypeError) {
    return "API недоступно. Проверьте, что запущен `site-parser-api` на 127.0.0.1:8000.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Не удалось выполнить запрос.";
}

async function readJsonSafe(response) {
  const bodyText = await response.text();
  if (!bodyText.trim()) {
    return null;
  }
  try {
    return JSON.parse(bodyText);
  } catch {
    return { detail: bodyText };
  }
}

function parseNumber(rawValue, label, mode) {
  const value = rawValue.trim();
  if (!value) {
    return null;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    throw new Error(`Поле "${label}" содержит некорректное число.`);
  }
  if (mode === "int" && !Number.isInteger(parsed)) {
    throw new Error(`Поле "${label}" должно быть целым числом.`);
  }
  return parsed;
}

function buildOverrides(values) {
  const overrides = {};

  const maxDepth = parseNumber(values.maxDepth, "max_depth", "int");
  if (maxDepth !== null) overrides.max_depth = maxDepth;

  const maxPages = parseNumber(values.maxPages, "max_pages", "int");
  if (maxPages !== null) overrides.max_pages = maxPages;

  const maxSeconds = parseNumber(values.maxSeconds, "max_seconds", "float");
  if (maxSeconds !== null) overrides.max_seconds = maxSeconds;

  const maxConcurrency = parseNumber(values.maxConcurrency, "max_concurrency", "int");
  if (maxConcurrency !== null) overrides.max_concurrency = maxConcurrency;

  const requestTimeout = parseNumber(values.requestTimeout, "request_timeout", "float");
  if (requestTimeout !== null) overrides.request_timeout = requestTimeout;

  const maxLinksPerPage = parseNumber(values.maxLinksPerPage, "max_links_per_page", "int");
  if (maxLinksPerPage !== null) overrides.max_links_per_page = maxLinksPerPage;

  const maxBodyBytes = parseNumber(values.maxBodyBytes, "max_body_bytes", "int");
  if (maxBodyBytes !== null) overrides.max_body_bytes = maxBodyBytes;

  const retryTotal = parseNumber(values.retryTotal, "retry_total", "int");
  if (retryTotal !== null) overrides.retry_total = retryTotal;

  const phoneRegions = values.phoneRegions.trim();
  if (phoneRegions) overrides.phone_regions = phoneRegions;

  const emailDomainAllowlist = values.emailDomainAllowlist.trim();
  if (emailDomainAllowlist) overrides.email_domain_allowlist = emailDomainAllowlist;

  const userAgent = values.userAgent.trim();
  if (userAgent) overrides.user_agent = userAgent;

  if (values.focusedCrawling === "true") overrides.focused_crawling = true;
  if (values.focusedCrawling === "false") overrides.focused_crawling = false;

  if (values.includeQuery === "true") overrides.include_query = true;
  if (values.includeQuery === "false") overrides.include_query = false;

  return Object.keys(overrides).length > 0 ? overrides : null;
}

export default function App() {
  const [url, setUrl] = useState(EXAMPLES[0]);
  const [configPath, setConfigPath] = useState("parser.example.toml");
  const [advanced, setAdvanced] = useState(DEFAULT_ADVANCED);
  const [result, setResult] = useState(null);
  const [rawJson, setRawJson] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState("");
  const [elapsedMs, setElapsedMs] = useState(null);

  const summary = useMemo(() => {
    if (!result) {
      return { emails: 0, phones: 0 };
    }
    return {
      emails: result.emails?.length || 0,
      phones: result.phones?.length || 0
    };
  }, [result]);

  function updateAdvanced(key, value) {
    setAdvanced((previous) => ({ ...previous, [key]: value }));
  }

  function resetAdvanced() {
    setAdvanced(DEFAULT_ADVANCED);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      setErrorText("Укажите URL для парсинга.");
      return;
    }

    setLoading(true);
    setErrorText("");
    const startedAt = performance.now();

    try {
      const overrides = buildOverrides(advanced);
      const response = await fetch(buildApiUrl("/api/parse"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          url: trimmedUrl,
          config: configPath.trim() || null,
          overrides
        })
      });

      const payload = await readJsonSafe(response);
      if (!response.ok) {
        const detail =
          payload && typeof payload === "object" && "detail" in payload
            ? String(payload.detail)
            : `HTTP ${response.status}`;
        throw new Error(detail);
      }

      if (!payload || typeof payload !== "object") {
        throw new Error("API вернул пустой ответ.");
      }

      setResult(payload);
      setRawJson(JSON.stringify(payload, null, 2));
    } catch (error) {
      setResult(null);
      setRawJson("");
      setErrorText(toErrorMessage(error));
    } finally {
      setElapsedMs(Math.round(performance.now() - startedAt));
      setLoading(false);
    }
  }

  async function copyResult() {
    if (!rawJson) {
      return;
    }
    try {
      await navigator.clipboard.writeText(rawJson);
    } catch {
      setErrorText("Не удалось скопировать JSON в буфер обмена.");
    }
  }

  return (
    <div className="app-shell">
      <div className="app-background" />
      <main className="app-content">
        <section className="hero-card">
          <p className="badge">Site Parser</p>
          <h1>Парсер контактов</h1>
          <p className="subtitle">
            Запустите парсинг одного домена, получите e-mail и телефоны в структурированном JSON.
          </p>
          <form className="search-form" onSubmit={handleSubmit}>
            <label>
              URL сайта
              <input
                type="url"
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://example.com/contact"
                required
              />
            </label>
            <label>
              Путь к конфигу (опционально)
              <input
                type="text"
                value={configPath}
                onChange={(event) => setConfigPath(event.target.value)}
                placeholder="parser.example.toml"
              />
            </label>
            <details className="advanced-panel">
              <summary>Переопределение параметров парсинга</summary>
              <p className="advanced-note">
                Меняют поведение только для текущего запуска из UI и не перезаписывают файл конфигурации.
              </p>
              <div className="advanced-grid">
                <label>
                  max_depth
                  <input
                    type="number"
                    value={advanced.maxDepth}
                    onChange={(event) => updateAdvanced("maxDepth", event.target.value)}
                    placeholder="0..50"
                  />
                  <span className="field-hint">0 - только текущая страница; больше - глубже обход и дольше выполнение.</span>
                </label>
                <label>
                  max_pages
                  <input
                    type="number"
                    value={advanced.maxPages}
                    onChange={(event) => updateAdvanced("maxPages", event.target.value)}
                    placeholder="1..5000"
                  />
                  <span className="field-hint">Лимит страниц за запуск: больше полнота, но выше время и нагрузка.</span>
                </label>
                <label>
                  max_seconds
                  <input
                    type="number"
                    step="0.1"
                    value={advanced.maxSeconds}
                    onChange={(event) => updateAdvanced("maxSeconds", event.target.value)}
                    placeholder="1..3600"
                  />
                  <span className="field-hint">Общий лимит времени. При достижении возвращается частичный результат.</span>
                </label>
                <label>
                  max_concurrency
                  <input
                    type="number"
                    value={advanced.maxConcurrency}
                    onChange={(event) => updateAdvanced("maxConcurrency", event.target.value)}
                    placeholder="1..64"
                  />
                  <span className="field-hint">Число одновременных запросов: выше быстрее, но больше риск 429.</span>
                </label>
                <label>
                  request_timeout
                  <input
                    type="number"
                    step="0.1"
                    value={advanced.requestTimeout}
                    onChange={(event) => updateAdvanced("requestTimeout", event.target.value)}
                    placeholder="0.5..120"
                  />
                  <span className="field-hint">Таймаут одного запроса: меньше быстрее отбой, больше выше шанс дождаться.</span>
                </label>
                <label>
                  max_links_per_page
                  <input
                    type="number"
                    value={advanced.maxLinksPerPage}
                    onChange={(event) => updateAdvanced("maxLinksPerPage", event.target.value)}
                    placeholder="1..5000"
                  />
                  <span className="field-hint">Сколько ссылок брать с одной страницы в очередь обхода.</span>
                </label>
                <label>
                  max_body_bytes
                  <input
                    type="number"
                    value={advanced.maxBodyBytes}
                    onChange={(event) => updateAdvanced("maxBodyBytes", event.target.value)}
                    placeholder="1024..50000000"
                  />
                  <span className="field-hint">Ограничение размера ответа страницы для защиты памяти и скорости.</span>
                </label>
                <label>
                  retry_total
                  <input
                    type="number"
                    value={advanced.retryTotal}
                    onChange={(event) => updateAdvanced("retryTotal", event.target.value)}
                    placeholder="0..10"
                  />
                  <span className="field-hint">Повторы при временных ошибках сети/сервера.</span>
                </label>
                <label>
                  phone_regions
                  <input
                    type="text"
                    value={advanced.phoneRegions}
                    onChange={(event) => updateAdvanced("phoneRegions", event.target.value)}
                    placeholder="RU,BY"
                  />
                  <span className="field-hint">Регионы для локальных телефонов без “+”, например RU,BY.</span>
                </label>
                <label>
                  email_domain_allowlist
                  <input
                    type="text"
                    value={advanced.emailDomainAllowlist}
                    onChange={(event) => updateAdvanced("emailDomainAllowlist", event.target.value)}
                    placeholder="gmail.com,mail.ru"
                  />
                  <span className="field-hint">Оставляет только e-mail из этих доменов и поддоменов.</span>
                </label>
                <label>
                  user_agent
                  <input
                    type="text"
                    value={advanced.userAgent}
                    onChange={(event) => updateAdvanced("userAgent", event.target.value)}
                    placeholder="Mozilla/5.0 ..."
                  />
                  <span className="field-hint">Заголовок User-Agent в HTTP-запросах парсера.</span>
                </label>
                <label>
                  focused_crawling
                  <select
                    value={advanced.focusedCrawling}
                    onChange={(event) => updateAdvanced("focusedCrawling", event.target.value)}
                  >
                    <option value="">по умолчанию</option>
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                  <span className="field-hint">true - в приоритете контактные страницы; false - обычный обход.</span>
                </label>
                <label>
                  include_query
                  <select value={advanced.includeQuery} onChange={(event) => updateAdvanced("includeQuery", event.target.value)}>
                    <option value="">по умолчанию</option>
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                  <span className="field-hint">
                    true - `/catalog?page=1` и `/catalog?page=2` считаются разными страницами; false - одной.
                  </span>
                </label>
              </div>
              <div className="advanced-actions">
                <button type="button" className="secondary-button" onClick={resetAdvanced}>
                  Сбросить переопределения
                </button>
              </div>
            </details>
            <div className="examples">
              {EXAMPLES.map((item) => (
                <button key={item} type="button" className="ghost-button" onClick={() => setUrl(item)}>
                  {item}
                </button>
              ))}
            </div>
            <div className="actions">
              <button type="submit" className="primary-button" disabled={loading}>
                {loading ? "Идёт парсинг..." : "Запустить парсинг"}
              </button>
              <button type="button" className="secondary-button" onClick={copyResult} disabled={!rawJson}>
                Копировать JSON
              </button>
            </div>
          </form>
          {errorText ? <div className="error-box">{errorText}</div> : null}
        </section>

        <section className="result-grid">
          <article className="result-card">
            <h2>Сводка</h2>
            <div className="metrics">
              <div>
                <p className="metric-label">E-mail</p>
                <p className="metric-value">{summary.emails}</p>
              </div>
              <div>
                <p className="metric-label">Телефоны</p>
                <p className="metric-value">{summary.phones}</p>
              </div>
              <div>
                <p className="metric-label">Время</p>
                <p className="metric-value">{elapsedMs !== null ? `${elapsedMs} мс` : "-"}</p>
              </div>
            </div>
            <div className="list-block">
              <h3>E-mail</h3>
              <ul>
                {(result?.emails || []).map((email) => (
                  <li key={email}>{email}</li>
                ))}
              </ul>
            </div>
            <div className="list-block">
              <h3>Телефоны</h3>
              <ul>
                {(result?.phones || []).map((phone) => (
                  <li key={phone}>{phone}</li>
                ))}
              </ul>
            </div>
          </article>

          <article className="result-card">
            <h2>JSON</h2>
            <pre>{rawJson || "Результат появится после запуска парсинга."}</pre>
          </article>
        </section>
      </main>
    </div>
  );
}
