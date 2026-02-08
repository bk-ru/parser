import { useEffect, useMemo, useRef, useState } from "react";
import Select from "react-select";

const EXAMPLES = [
  "https://www.iana.org/contact",
  "https://www.icann.org/contact",
  "https://xn--c1akpdiz.xn--80adxhks/yuristy-moskvy/371-advokaty-yuristy-butovo.html"
];

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

const PHONE_REGION_OPTIONS = [
  { code: "RU", name: "Россия" },
  { code: "BY", name: "Беларусь" },
  { code: "KZ", name: "Казахстан" },
  { code: "UA", name: "Украина" },
  { code: "KG", name: "Кыргызстан" },
  { code: "UZ", name: "Узбекистан" },
  { code: "AM", name: "Армения" },
  { code: "AZ", name: "Азербайджан" },
  { code: "GE", name: "Грузия" },
  { code: "MD", name: "Молдова" },
  { code: "PL", name: "Польша" },
  { code: "DE", name: "Германия" },
  { code: "FR", name: "Франция" },
  { code: "IT", name: "Италия" },
  { code: "ES", name: "Испания" },
  { code: "GB", name: "Великобритания" },
  { code: "US", name: "США" },
  { code: "CA", name: "Канада" },
  { code: "AU", name: "Австралия" },
  { code: "JP", name: "Япония" },
  { code: "CN", name: "Китай" },
  { code: "IN", name: "Индия" }
];

const PHONE_REGION_SELECT_OPTIONS = PHONE_REGION_OPTIONS.map((option) => ({
  value: option.code,
  label: `${option.name} (${option.code})`
}));
const ALL_PHONE_REGION_CODES = PHONE_REGION_SELECT_OPTIONS.map((option) => option.value);

const PHONE_REGION_SELECT_STYLES = {
  control: (base, state) => ({
    ...base,
    minHeight: "46px",
    alignItems: "flex-start",
    borderRadius: "14px",
    borderColor: state.isFocused ? "rgba(0, 113, 227, 0.42)" : "rgba(0, 0, 0, 0.08)",
    boxShadow: state.isFocused ? "0 0 0 4px rgba(0, 113, 227, 0.12)" : "none",
    "&:hover": {
      borderColor: state.isFocused ? "rgba(0, 113, 227, 0.42)" : "rgba(0, 0, 0, 0.14)"
    }
  }),
  valueContainer: (base) => ({
    ...base,
    padding: "6px 10px",
    display: "flex",
    flexWrap: "wrap",
    gap: "4px",
    maxHeight: "88px",
    overflowY: "auto",
    overflowX: "hidden"
  }),
  multiValue: (base) => ({
    ...base,
    borderRadius: "999px",
    backgroundColor: "rgba(0, 113, 227, 0.12)",
    margin: 0
  }),
  multiValueLabel: (base) => ({
    ...base,
    color: "#0053a8",
    fontSize: "12px",
    fontWeight: 600,
    padding: "2px 6px"
  }),
  multiValueRemove: (base) => ({
    ...base,
    color: "#0053a8",
    borderRadius: "999px",
    padding: "2px 4px",
    ":hover": {
      backgroundColor: "rgba(0, 113, 227, 0.24)",
      color: "#003e7d"
    }
  }),
  menu: (base) => ({
    ...base,
    borderRadius: "14px",
    border: "1px solid rgba(0, 0, 0, 0.08)",
    boxShadow: "0 16px 32px rgba(0, 0, 0, 0.16)",
    overflow: "hidden"
  }),
  option: (base, state) => ({
    ...base,
    fontSize: "14px",
    backgroundColor: state.isFocused ? "rgba(0, 113, 227, 0.08)" : state.isSelected ? "rgba(0, 113, 227, 0.14)" : "#fff",
    color: "#1d1d1f",
    ":active": {
      backgroundColor: "rgba(0, 113, 227, 0.18)"
    }
  })
};

function formatPhoneRegionOption(option, meta) {
  if (meta.context === "value") {
    return option.value;
  }
  return option.label;
}

function SettingHeader({ label, description }) {
  return (
    <span className="field-label-row">
      <span>{label}</span>
      <span className="help-wrap">
        <span className="help-icon" aria-hidden="true">
          ?
        </span>
        <span className="help-tooltip" role="tooltip">
          {description}
        </span>
      </span>
    </span>
  );
}

function SettingDefault({ value }) {
  return <span className="field-default">По умолчанию: {value}</span>;
}

const DEFAULT_ADVANCED = {
  maxDepth: "",
  maxPages: "",
  maxSeconds: "",
  maxConcurrency: "",
  requestTimeout: "",
  maxLinksPerPage: "",
  maxBodyBytes: "",
  retryTotal: "",
  phoneRegions: [],
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

function preventNumberInputWheel(event) {
  event.preventDefault();
  event.currentTarget.blur();
}

function buildOverrides(values) {
  const overrides = {};

  const maxDepth = parseNumber(values.maxDepth, "Глубина обхода", "int");
  if (maxDepth !== null) overrides.max_depth = maxDepth;

  const maxPages = parseNumber(values.maxPages, "Лимит страниц", "int");
  if (maxPages !== null) overrides.max_pages = maxPages;

  const maxSeconds = parseNumber(values.maxSeconds, "Лимит времени", "float");
  if (maxSeconds !== null) overrides.max_seconds = maxSeconds;

  const maxConcurrency = parseNumber(values.maxConcurrency, "Параллельные запросы", "int");
  if (maxConcurrency !== null) overrides.max_concurrency = maxConcurrency;

  const requestTimeout = parseNumber(values.requestTimeout, "Таймаут запроса", "float");
  if (requestTimeout !== null) overrides.request_timeout = requestTimeout;

  const maxLinksPerPage = parseNumber(values.maxLinksPerPage, "Ссылок со страницы", "int");
  if (maxLinksPerPage !== null) overrides.max_links_per_page = maxLinksPerPage;

  const maxBodyBytes = parseNumber(values.maxBodyBytes, "Размер ответа", "int");
  if (maxBodyBytes !== null) overrides.max_body_bytes = maxBodyBytes;

  const retryTotal = parseNumber(values.retryTotal, "Повторные попытки", "int");
  if (retryTotal !== null) overrides.retry_total = retryTotal;

  if (Array.isArray(values.phoneRegions) && values.phoneRegions.length > 0) {
    overrides.phone_regions = values.phoneRegions;
  }

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

function formatLogLine(item) {
  return `[${item.timestamp}] ${item.level} ${item.logger}: ${item.message}`;
}

export default function App() {
  const [url, setUrl] = useState(EXAMPLES[0]);
  const [configPath, setConfigPath] = useState("parser.example.toml");
  const [advanced, setAdvanced] = useState(DEFAULT_ADVANCED);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [result, setResult] = useState(null);
  const [rawJson, setRawJson] = useState("");
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [errorText, setErrorText] = useState("");
  const [elapsedMs, setElapsedMs] = useState(null);
  const logsRef = useRef(null);
  const lastLogIdRef = useRef(0);

  const summary = useMemo(() => {
    if (!result) {
      return { emails: 0, phones: 0 };
    }
    return {
      emails: result.emails?.length || 0,
      phones: result.phones?.length || 0
    };
  }, [result]);

  const selectedPhoneRegionOptions = useMemo(() => {
    if (!Array.isArray(advanced.phoneRegions) || advanced.phoneRegions.length === 0) {
      return [];
    }
    const selected = new Set(advanced.phoneRegions);
    return PHONE_REGION_SELECT_OPTIONS.filter((option) => selected.has(option.value));
  }, [advanced.phoneRegions]);
  const hasPhoneRegionsSelected = advanced.phoneRegions.length > 0;
  const allPhoneRegionsSelected = advanced.phoneRegions.length === ALL_PHONE_REGION_CODES.length;

  useEffect(() => {
    const pollLogs = async () => {
      try {
        const response = await fetch(buildApiUrl(`/api/logs?after=${lastLogIdRef.current}&limit=300`));
        if (!response.ok) {
          return;
        }
        const payload = await readJsonSafe(response);
        const items = Array.isArray(payload?.items) ? payload.items : [];
        if (!items.length) {
          return;
        }
        lastLogIdRef.current = items[items.length - 1].id;
        setLogs((previous) => [...previous, ...items].slice(-1000));
      } catch {
        // Игнорируем временные сетевые ошибки лог-пула
      }
    };

    const timerId = setInterval(pollLogs, 700);
    pollLogs();
    return () => clearInterval(timerId);
  }, []);

  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [logs]);

  function updateAdvanced(key, value) {
    setAdvanced((previous) => ({ ...previous, [key]: value }));
  }

  function resetAdvanced() {
    setAdvanced(DEFAULT_ADVANCED);
  }

  function handlePhoneRegionsChange(selectedOptions) {
    const selected = Array.isArray(selectedOptions) ? selectedOptions.map((option) => option.value) : [];
    updateAdvanced("phoneRegions", selected);
  }

  function selectAllPhoneRegions() {
    updateAdvanced("phoneRegions", ALL_PHONE_REGION_CODES);
  }

  function clearPhoneRegions() {
    updateAdvanced("phoneRegions", []);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      setErrorText("Укажите URL для парсинга.");
      return;
    }

    setLogs([]);
    lastLogIdRef.current = 0;
    setLoading(true);
    setErrorText("");
    const startedAt = performance.now();

    try {
      await fetch(buildApiUrl("/api/logs/clear"), { method: "POST" }).catch(() => null);
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
              <button
                type="button"
                className="secondary-button"
                onClick={() => setShowAdvanced((value) => !value)}
                aria-expanded={showAdvanced}
                aria-controls="parser-settings-panel"
              >
                {showAdvanced ? "Скрыть настройки" : "Настройки парсера"}
              </button>
            </div>
            <div
              id="parser-settings-panel"
              className={`advanced-panel-wrap${showAdvanced ? " is-open" : ""}`}
              aria-hidden={!showAdvanced}
            >
              <div className="advanced-panel">
                <p className="advanced-title">Настройки парсера</p>
                <p className="advanced-note">
                  Эти параметры действуют только для текущего запуска из веб-интерфейса.
                </p>
                <div className="advanced-grid">
                  <label>
                    <SettingHeader
                      label="Глубина обхода"
                      description="Определяет, насколько глубоко парсер переходит по ссылкам: 0 - только стартовая страница, большее значение - больше найденных данных, но дольше выполнение."
                    />
                    <input
                      type="number"
                      value={advanced.maxDepth}
                      onChange={(event) => updateAdvanced("maxDepth", event.target.value)}
                      onWheel={preventNumberInputWheel}
                      placeholder="0..50"
                    />
                    <SettingDefault value="0" />
                  </label>
                  <label>
                    <SettingHeader
                      label="Лимит страниц"
                      description="Ограничивает общее число страниц за запуск. Увеличение повышает полноту результатов, но растит время и нагрузку."
                    />
                    <input
                      type="number"
                      value={advanced.maxPages}
                      onChange={(event) => updateAdvanced("maxPages", event.target.value)}
                      onWheel={preventNumberInputWheel}
                      placeholder="1..5000"
                    />
                    <SettingDefault value="200" />
                  </label>
                  <label>
                    <SettingHeader
                      label="Лимит времени, сек"
                      description="Жёсткий тайм-лимит всего запуска. Когда время истекает, парсер останавливается и возвращает уже собранный результат."
                    />
                    <input
                      type="number"
                      step="0.1"
                      value={advanced.maxSeconds}
                      onChange={(event) => updateAdvanced("maxSeconds", event.target.value)}
                      onWheel={preventNumberInputWheel}
                      placeholder="1..3600"
                    />
                    <SettingDefault value="30.0" />
                  </label>
                  <label>
                    <SettingHeader
                      label="Параллельные запросы"
                      description="Сколько HTTP-запросов выполняется одновременно. Больше значение ускоряет обход, но повышает риск блокировок и ответов 429."
                    />
                    <input
                      type="number"
                      value={advanced.maxConcurrency}
                      onChange={(event) => updateAdvanced("maxConcurrency", event.target.value)}
                      onWheel={preventNumberInputWheel}
                      placeholder="1..64"
                    />
                    <SettingDefault value="4" />
                  </label>
                  <label>
                    <SettingHeader
                      label="Таймаут запроса, сек"
                      description="Максимальное ожидание одного HTTP-запроса. Меньше значение быстрее отбрасывает медленные сайты, больше повышает шанс дождаться ответа."
                    />
                    <input
                      type="number"
                      step="0.1"
                      value={advanced.requestTimeout}
                      onChange={(event) => updateAdvanced("requestTimeout", event.target.value)}
                      onWheel={preventNumberInputWheel}
                      placeholder="0.5..120"
                    />
                    <SettingDefault value="10.0" />
                  </label>
                  <label>
                    <SettingHeader
                      label="Ссылок со страницы"
                      description="Ограничивает, сколько ссылок парсер возьмёт с каждой страницы в очередь обхода. Меньше - быстрее и стабильнее, больше - выше полнота."
                    />
                    <input
                      type="number"
                      value={advanced.maxLinksPerPage}
                      onChange={(event) => updateAdvanced("maxLinksPerPage", event.target.value)}
                      onWheel={preventNumberInputWheel}
                      placeholder="1..5000"
                    />
                    <SettingDefault value="200" />
                  </label>
                  <label>
                    <SettingHeader
                      label="Размер ответа, байт"
                      description="Лимит размера загружаемого HTML. Защищает от слишком тяжёлых страниц и снижает расход памяти."
                    />
                    <input
                      type="number"
                      value={advanced.maxBodyBytes}
                      onChange={(event) => updateAdvanced("maxBodyBytes", event.target.value)}
                      onWheel={preventNumberInputWheel}
                      placeholder="1024..50000000"
                    />
                    <SettingDefault value="2000000" />
                  </label>
                  <label>
                    <SettingHeader
                      label="Повторные попытки"
                      description="Сколько раз повторять запрос при временных сетевых ошибках и ошибках сервера. Большее значение повышает устойчивость, но увеличивает время."
                    />
                    <input
                      type="number"
                      value={advanced.retryTotal}
                      onChange={(event) => updateAdvanced("retryTotal", event.target.value)}
                      onWheel={preventNumberInputWheel}
                      placeholder="0..10"
                    />
                    <SettingDefault value="2" />
                  </label>
                  <div className="phone-region-field setting-field">
                    <div className="phone-region-header">
                      <SettingHeader
                        label="Регионы телефонов"
                        description="Нужны для распознавания локальных номеров без '+' (например, 495...). Если не указано, используется автоопределение по стартовому URL."
                      />
                      <div className="region-select-actions">
                        <button
                          type="button"
                          className="region-action-button"
                          onClick={selectAllPhoneRegions}
                          disabled={allPhoneRegionsSelected}
                        >
                          Выбрать все
                        </button>
                        <button
                          type="button"
                          className="region-action-button"
                          onClick={clearPhoneRegions}
                          disabled={!hasPhoneRegionsSelected}
                        >
                          Очистить
                        </button>
                      </div>
                    </div>
                    <Select
                      inputId="phone-regions"
                      className="phone-region-select"
                      classNamePrefix="region-select"
                      isMulti
                      isClearable
                      isSearchable
                      closeMenuOnSelect={false}
                      hideSelectedOptions={false}
                      options={PHONE_REGION_SELECT_OPTIONS}
                      value={selectedPhoneRegionOptions}
                      onChange={handlePhoneRegionsChange}
                      placeholder="Выберите один или несколько регионов"
                      noOptionsMessage={() => "Ничего не найдено"}
                      formatOptionLabel={formatPhoneRegionOption}
                      styles={PHONE_REGION_SELECT_STYLES}
                    />
                    <SettingDefault value="не задано (автоопределение по URL)" />
                  </div>
                  <label>
                    <SettingHeader
                      label="Разрешённые домены e-mail"
                      description="Фильтр по доменам e-mail. Если заполнить, в результате останутся только адреса из указанных доменов и поддоменов."
                    />
                    <input
                      type="text"
                      value={advanced.emailDomainAllowlist}
                      onChange={(event) => updateAdvanced("emailDomainAllowlist", event.target.value)}
                      placeholder="gmail.com,mail.ru"
                    />
                    <SettingDefault value="не задано (без фильтра)" />
                  </label>
                  <label>
                    <SettingHeader
                      label="User-Agent"
                      description="HTTP-заголовок User-Agent для запросов. Полезно менять, если сайт блокирует стандартные клиенты."
                    />
                    <input
                      type="text"
                      value={advanced.userAgent}
                      onChange={(event) => updateAdvanced("userAgent", event.target.value)}
                      placeholder="Mozilla/5.0 ..."
                    />
                    <SettingDefault value="site-parser/0.1.0" />
                  </label>
                  <label>
                    <SettingHeader
                      label="Фокусированный обход"
                      description="При включении парсер в первую очередь обходит страницы, похожие на контакты/поддержку. Обычно это ускоряет поиск телефонов и e-mail."
                    />
                    <select
                      value={advanced.focusedCrawling}
                      onChange={(event) => updateAdvanced("focusedCrawling", event.target.value)}
                    >
                      <option value="">по умолчанию</option>
                      <option value="true">включить</option>
                      <option value="false">выключить</option>
                    </select>
                    <SettingDefault value="включено" />
                  </label>
                  <label>
                    <SettingHeader
                      label="Учитывать query-параметры"
                      description="Если включено, URL с разными query считаются разными страницами (/page?a=1 и /page?a=2). Если выключено, такие URL объединяются."
                    />
                    <select value={advanced.includeQuery} onChange={(event) => updateAdvanced("includeQuery", event.target.value)}>
                      <option value="">по умолчанию</option>
                      <option value="true">включить</option>
                      <option value="false">выключить</option>
                    </select>
                    <SettingDefault value="выключено" />
                  </label>
                </div>
                <div className="advanced-actions">
                  <button type="button" className="secondary-button" onClick={resetAdvanced}>
                    Сбросить настройки
                  </button>
                </div>
              </div>
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

        <section className="result-card logs-card">
          <h2>Логи</h2>
          <pre className="logs-console" ref={logsRef}>
            {logs.length ? logs.map(formatLogLine).join("\n") : "Логи появятся после запуска парсинга."}
          </pre>
        </section>
      </main>
    </div>
  );
}
