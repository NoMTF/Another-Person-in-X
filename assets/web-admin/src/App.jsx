import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Bot,
  Check,
  Database,
  Lock,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Save,
  Shield,
  SlidersHorizontal,
  Trash2,
  Users,
} from "lucide-react";

const API_BASE = import.meta.env.VITE_ADMIN_API || "";

const featureLabels = {
  auto_post: "Posts",
  auto_reply: "Replies",
  browse_timeline: "Timeline",
  like: "Likes",
  repost: "Reposts",
  quote: "Quotes",
  follow: "Follows",
  shadow_mode: "Shadow",
  read_only: "Read only",
  pause_all: "Pause all",
};

const limitLabels = {
  daily_posts: "Daily posts",
  reply_delay_min_seconds: "Reply min sec",
  reply_delay_max_seconds: "Reply max sec",
  browse_interval_min_minutes: "Browse min",
  likes_per_day: "Likes/day",
  reposts_per_day: "Reposts/day",
  quotes_per_day: "Quotes/day",
  follows_per_day: "Follows/day",
  max_replies_per_hour: "Replies/hour",
};

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function api(path, token, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(token),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function IconButton({ title, children, onClick, tone = "neutral", type = "button" }) {
  return (
    <button className={`iconButton ${tone}`} type={type} title={title} aria-label={title} onClick={onClick}>
      {children}
    </button>
  );
}

function Toggle({ label, value, onChange }) {
  return (
    <label className="toggleRow">
      <span>{label}</span>
      <input type="checkbox" checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

function Section({ title, icon: Icon, children, actions }) {
  return (
    <section className="panel">
      <div className="sectionHeader">
        <div className="sectionTitle">
          <Icon size={18} />
          <h2>{title}</h2>
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem("factory_admin_token") || "");
  const [health, setHealth] = useState(null);
  const [config, setConfig] = useState({ features: {}, limits: {} });
  const [personas, setPersonas] = useState([]);
  const [owners, setOwners] = useState([]);
  const [audit, setAudit] = useState([]);
  const [pending, setPending] = useState([]);
  const [memoryQuery, setMemoryQuery] = useState("");
  const [memoryRows, setMemoryRows] = useState([]);
  const [status, setStatus] = useState("Ready");
  const [personaDraft, setPersonaDraft] = useState({ slug: "", name: "", path: "", version: "1", notes: "", rollout_group: "stable", traffic_weight: 1 });
  const [ownerDraft, setOwnerDraft] = useState({ kind: "telegram_id", value: "" });

  const paused = Boolean(config.features.pause_all);
  const riskMode = paused || config.features.read_only ? "locked" : config.features.shadow_mode ? "shadow" : "live";

  const loadAll = async () => {
    try {
      const [healthData, configData, personaData, ownerData, auditData, pendingData] = await Promise.all([
        api("/api/health", token),
        api("/api/config", token),
        api("/api/personas", token),
        api("/api/owners", token),
        api("/api/audit?limit=60", token),
        api("/api/pending?limit=60", token),
      ]);
      setHealth(healthData);
      setConfig(configData);
      setPersonas(personaData);
      setOwners(ownerData);
      setAudit(auditData);
      setPending(pendingData);
      setStatus("Synced");
    } catch (error) {
      setStatus(error.message);
    }
  };

  useEffect(() => {
    sessionStorage.setItem("factory_admin_token", token);
  }, [token]);

  useEffect(() => {
    loadAll();
  }, []);

  const featureEntries = useMemo(() => Object.entries(featureLabels), []);
  const limitEntries = useMemo(() => Object.entries(limitLabels), []);

  const setFeature = async (key, enabled) => {
    setConfig((current) => ({ ...current, features: { ...current.features, [key]: enabled } }));
    await api("/api/config/feature", token, { method: "POST", body: JSON.stringify({ key, enabled }) });
    loadAll();
  };

  const setLimit = async (key, value) => {
    const parsed = Number(value);
    setConfig((current) => ({ ...current, limits: { ...current.limits, [key]: parsed } }));
    await api("/api/config/limit", token, { method: "POST", body: JSON.stringify({ key, value: parsed }) });
  };

  const savePersona = async (event) => {
    event.preventDefault();
    await api("/api/personas", token, { method: "POST", body: JSON.stringify({ ...personaDraft, enabled: true }) });
    setPersonaDraft({ slug: "", name: "", path: "", version: "1", notes: "", rollout_group: "stable", traffic_weight: 1 });
    loadAll();
  };

  const saveOwner = async (event) => {
    event.preventDefault();
    await api("/api/owners", token, { method: "POST", body: JSON.stringify({ ...ownerDraft, enabled: true }) });
    setOwnerDraft({ kind: "telegram_id", value: "" });
    loadAll();
  };

  const searchMemory = async () => {
    if (!memoryQuery.trim()) return;
    try {
      const rows = await api(`/api/memory/search?q=${encodeURIComponent(memoryQuery)}&limit=30`, token);
      setMemoryRows(rows);
    } catch (error) {
      setStatus(error.message);
    }
  };

  const cancelPending = async (id) => {
    await api(`/api/pending/${id}/cancel`, token, { method: "POST", body: "{}" });
    loadAll();
  };

  const cancelAllPending = async () => {
    await api("/api/pending/cancel-all", token, { method: "POST", body: "{}" });
    loadAll();
  };

  return (
    <main className="appShell">
      <header className="topBar">
        <div className="brandBlock">
          <div className="brandMark">
            <Bot size={22} />
          </div>
          <div>
            <h1>OpenClaw Agent Factory</h1>
            <p>{health?.profile || "local"} · {health?.state_dir || "waiting for API"}</p>
          </div>
        </div>
        <div className="toolbar">
          <span className={`modePill ${riskMode}`}>{riskMode}</span>
          <label className="tokenField">
            <Lock size={15} />
            <input value={token} placeholder="Admin token" type="password" onChange={(event) => setToken(event.target.value)} />
          </label>
          <IconButton title="Refresh" onClick={loadAll}>
            <RotateCcw size={17} />
          </IconButton>
        </div>
      </header>

      <div className="statusStrip">
        <span>{status}</span>
        <span>{personas.length} personas</span>
        <span>{owners.length} owners</span>
        <span>{audit.length} audit rows</span>
        <span>{pending.length} pending</span>
      </div>

      <div className="grid">
        <Section
          title="Controls"
          icon={Shield}
          actions={
            <div className="buttonGroup">
              <IconButton title={paused ? "Resume all" : "Pause all"} tone={paused ? "success" : "danger"} onClick={() => setFeature("pause_all", !paused)}>
                {paused ? <Play size={17} /> : <Pause size={17} />}
              </IconButton>
            </div>
          }
        >
          <div className="toggles">
            {featureEntries.map(([key, label]) => (
              <Toggle key={key} label={label} value={config.features[key]} onChange={(enabled) => setFeature(key, enabled)} />
            ))}
          </div>
        </Section>

        <Section title="Limits" icon={SlidersHorizontal}>
          <div className="limitGrid">
            {limitEntries.map(([key, label]) => (
              <label key={key} className="numberField">
                <span>{label}</span>
                <input type="number" min="0" value={config.limits[key] ?? 0} onChange={(event) => setLimit(key, event.target.value)} />
              </label>
            ))}
          </div>
        </Section>

        <Section title="Personas" icon={Users}>
          <form className="inlineForm" onSubmit={savePersona}>
            <input placeholder="slug" value={personaDraft.slug} onChange={(event) => setPersonaDraft({ ...personaDraft, slug: event.target.value })} />
            <input placeholder="name" value={personaDraft.name} onChange={(event) => setPersonaDraft({ ...personaDraft, name: event.target.value })} />
            <input placeholder="skill path" value={personaDraft.path} onChange={(event) => setPersonaDraft({ ...personaDraft, path: event.target.value })} />
            <IconButton title="Save persona" type="submit" tone="success">
              <Save size={17} />
            </IconButton>
          </form>
          <div className="tableList">
            {personas.map((persona) => (
              <div className="row" key={persona.slug}>
                <strong>{persona.name}</strong>
                <span>{persona.slug}</span>
                <span>{persona.rollout_group || "stable"}</span>
                <span>{persona.enabled ? `w${persona.traffic_weight ?? 1}` : "off"}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Owners" icon={Lock}>
          <form className="inlineForm compact" onSubmit={saveOwner}>
            <select value={ownerDraft.kind} onChange={(event) => setOwnerDraft({ ...ownerDraft, kind: event.target.value })}>
              <option value="telegram_id">Telegram ID</option>
              <option value="telegram_username">Telegram user</option>
              <option value="x_username">X user</option>
            </select>
            <input placeholder="value" value={ownerDraft.value} onChange={(event) => setOwnerDraft({ ...ownerDraft, value: event.target.value })} />
            <IconButton title="Add owner" type="submit" tone="success">
              <Plus size={17} />
            </IconButton>
          </form>
          <div className="tableList">
            {owners.map((owner) => (
              <div className="row" key={`${owner.kind}:${owner.value}`}>
                <strong>{owner.kind}</strong>
                <span>{owner.value}</span>
                <span>{owner.enabled ? "active" : "off"}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Audit" icon={Activity}>
          <div className="auditList">
            {audit.map((item) => (
              <article className="auditRow" key={item.id}>
                <div>
                  <strong>{item.action}</strong>
                  <span>{item.risk}</span>
                  {item.shadow ? <span>shadow</span> : item.sent ? <span>sent</span> : <span>held</span>}
                </div>
                <p>{item.text || item.reason || item.target}</p>
              </article>
            ))}
          </div>
        </Section>

        <Section
          title="Pending"
          icon={Pause}
          actions={
            <IconButton title="Cancel all pending" onClick={cancelAllPending} tone="danger">
              <Trash2 size={17} />
            </IconButton>
          }
        >
          <div className="auditList">
            {pending.map((item) => (
              <article className="auditRow" key={item.id}>
                <div>
                  <strong>{item.action}</strong>
                  <span>{item.risk}</span>
                  <span>{item.status}</span>
                  <IconButton title="Cancel pending" onClick={() => cancelPending(item.id)} tone="danger">
                    <Trash2 size={15} />
                  </IconButton>
                </div>
                <p>{item.text || item.reason || item.target}</p>
              </article>
            ))}
            {!pending.length && (
              <div className="emptyState">
                <Check size={18} />
                <span>No pending actions</span>
              </div>
            )}
          </div>
        </Section>

        <Section
          title="Memory"
          icon={Database}
          actions={
            <IconButton title="Search memory" onClick={searchMemory}>
              <Check size={17} />
            </IconButton>
          }
        >
          <div className="memorySearch">
            <input value={memoryQuery} placeholder="Search memory" onChange={(event) => setMemoryQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && searchMemory()} />
          </div>
          <div className="tableList">
            {memoryRows.map((row) => (
              <div className="memoryRow" key={row.id}>
                <strong>{row.category}</strong>
                <p>{row.content}</p>
              </div>
            ))}
          </div>
          {!memoryRows.length && (
            <div className="emptyState">
              <AlertTriangle size={18} />
              <span>No memory results</span>
            </div>
          )}
        </Section>
      </div>
    </main>
  );
}

export default App;
