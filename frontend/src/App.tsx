import { useCallback, useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";

type Person = { owner_id: string; name: string };
type Message = {
  id: string;
  title: string;
  body: string;
  kind: string;
  source_id: string | null;
  external_id: string | null;
  publisher: string | null;
  topic: string | null;
  channel: string | null;
  recipients: string[];
  version: number;
  status: string;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  enrichment: unknown;
  revisions?: Revision[];
  deliveries?: Delivery[];
  responses?: ResponseItem[];
  response_counts?: Record<string, number>;
};
type Revision = {
  version: number;
  content: { title: string; body: string };
  created_at: string;
};
type Delivery = {
  id: string;
  message_id: string;
  version: number;
  owner_id: string;
  mode: string;
  status: string;
  notified: boolean;
  human_read: boolean;
  attempts: number;
  last_error: string | null;
  summary: string | null;
  created_at: string;
  updated_at: string;
};
type ResponseItem = {
  owner_id: string;
  response: string;
  note: string | null;
  updated_at: string;
};
type Source = {
  id: string;
  name: string;
  type: "webhook" | "poll" | "manual";
  enabled: boolean;
  url: string | null;
  poll_interval_seconds: number | null;
  last_error: string | null;
  next_poll_at: string | null;
};
type Subscription = {
  id: string;
  owner_id: string;
  channel: string | null;
  topic: string | null;
  mode: "immediate" | "digest";
  enabled: boolean;
};
type Dashboard = {
  messages: number;
  active_messages: number;
  sources: number;
  subscriptions: number;
  deliveries: number;
  pending: number;
  accepted: number;
  processed: number;
  failed: number;
  cancelled: number;
};
type Config = {
  service_configured: boolean;
  duet_configured: boolean;
  enrichment_enabled: boolean;
};
type Page =
  | "Overview"
  | "Messages"
  | "Deliveries"
  | "Sources"
  | "Subscriptions";
type Modal =
  | { type: "message"; value?: Message }
  | { type: "source"; value?: Source }
  | { type: "subscription"; value?: Subscription }
  | { type: "response"; value: Message }
  | null;

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch("/api" + path, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options?.body ? { "Content-Type": "application/json" } : {}),
      ...options?.headers,
    },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : Array.isArray(body.detail)
          ? body.detail.map((item: { msg: string }) => item.msg).join("; ")
          : `Request failed (${response.status})`,
    );
  }
  return response.json();
}
async function loadAll<T>(path: string): Promise<T[]> {
  const items: T[] = [];
  let batch: T[];
  do {
    batch = await api<T[]>(`${path}?limit=500&offset=${items.length}`);
    items.push(...batch);
  } while (batch.length === 500);
  return items;
}
const send = <T,>(path: string, method: string, body?: unknown) =>
  api<T>(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
const date = (value?: string | null) =>
  value
    ? new Date(value).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : "—";
const messageStatus = (message: Message) =>
  message.status === "active" &&
  message.expires_at &&
  new Date(message.expires_at).getTime() <= Date.now()
    ? "expired"
    : message.status;
const titleCase = (value: string) =>
  value.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
const personName = (people: Person[], id: string) =>
  people.find((p) => p.owner_id === id)?.name || id;

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    overview: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    messages: (
      <>
        <path d="M4 5h16v11H8l-4 3V5Z" />
        <path d="M8 9h8M8 12h6" />
      </>
    ),
    deliveries: (
      <>
        <path d="M3 6h12v11H3zM15 10h3l3 3v4h-6z" />
        <circle cx="7" cy="18" r="2" />
        <circle cx="18" cy="18" r="2" />
      </>
    ),
    sources: (
      <>
        <path d="M12 3v6M12 15v6M3 12h6M15 12h6" />
        <circle cx="12" cy="12" r="3" />
        <circle cx="12" cy="3" r="1" />
        <circle cx="21" cy="12" r="1" />
        <circle cx="12" cy="21" r="1" />
        <circle cx="3" cy="12" r="1" />
      </>
    ),
    subscriptions: (
      <>
        <path d="M4 7h16M4 12h16M4 17h16" />
        <circle cx="8" cy="7" r="2" fill="white" />
        <circle cx="16" cy="12" r="2" fill="white" />
        <circle cx="10" cy="17" r="2" fill="white" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    close: <path d="M6 6l12 12M18 6 6 18" />,
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 4 4" />
      </>
    ),
    edit: (
      <>
        <path d="m4 16-1 5 5-1L20 8l-4-4L4 16ZM14 6l4 4" />
      </>
    ),
    refresh: (
      <>
        <path d="M20 7v5h-5M4 17v-5h5" />
        <path d="M5 9a8 8 0 0 1 13-3l2 2M19 15a8 8 0 0 1-13 3l-2-2" />
      </>
    ),
    arrow: <path d="M5 12h14M14 7l5 5-5 5" />,
    back: <path d="M19 12H5M10 7l-5 5 5 5" />,
    logout: (
      <>
        <path d="M10 4H5v16h5M14 8l4 4-4 4M8 12h10" />
      </>
    ),
    spark: (
      <path d="m12 2 1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2ZM19 16l.7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16Z" />
    ),
    check: <path d="m5 12 4 4L19 6" />,
    warning: (
      <>
        <path d="M12 3 2 21h20L12 3ZM12 9v5M12 17v1" />
      </>
    ),
    trash: (
      <>
        <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5M14 11v5" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
function IconButton({
  name,
  label,
  onClick,
  disabled,
}: {
  name: string;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      className="icon-button"
      title={label}
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
    >
      <Icon name={name} size={17} />
    </button>
  );
}
function Badge({ value }: { value: string }) {
  return (
    <span className={"badge " + value.toLowerCase()}>
      <i />
      {titleCase(value)}
    </span>
  );
}
function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon name="messages" size={22} />
      </div>
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}
function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
function ModalFrame({
  title,
  subtitle,
  close,
  children,
}: {
  title: string;
  subtitle?: string;
  close: () => void;
  children: ReactNode;
}) {
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header>
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <IconButton name="close" label="Close" onClick={close} />
        </header>
        {children}
      </section>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState<Person | null>(null),
    [authLoading, setAuthLoading] = useState(true);
  const [page, setPage] = useState<Page>("Overview"),
    [people, setPeople] = useState<Person[]>([]),
    [config, setConfig] = useState<Config | null>(null);
  const [messages, setMessages] = useState<Message[]>([]),
    [deliveries, setDeliveries] = useState<Delivery[]>([]),
    [sources, setSources] = useState<Source[]>([]),
    [subscriptions, setSubscriptions] = useState<Subscription[]>([]),
    [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [modal, setModal] = useState<Modal>(null),
    [detail, setDetail] = useState<Message | null>(null),
    [deliveryDetail, setDeliveryDetail] = useState<Delivery | null>(null);
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState(""),
    [topic, setTopic] = useState(""),
    [sourceFilter, setSourceFilter] = useState(""),
    [ownerFilter, setOwnerFilter] = useState("");
  useEffect(() => {
    api<Person>("/auth/me")
      .then(setUser)
      .catch(() => {})
      .finally(() => setAuthLoading(false));
  }, []);
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [p, c, m, d, s, sub, dash] = await Promise.all([
        api<Person[]>("/people"),
        api<Config>("/config"),
        loadAll<Message>("/messages"),
        loadAll<Delivery>("/deliveries"),
        api<Source[]>("/sources"),
        api<Subscription[]>("/subscriptions"),
        api<Dashboard>("/dashboard"),
      ]);
      setPeople(p);
      setConfig(c);
      setMessages(m);
      setDeliveries(d);
      setSources(s);
      setSubscriptions(sub);
      setDashboard(dash);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    if (user) void refresh();
  }, [user, refresh]);
  const openMessage = async (id: string) => {
    try {
      setDetail(await api<Message>("/messages/" + id));
      setDeliveryDetail(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const action = async (
    work: () => Promise<unknown>,
    message: string,
    currentId?: string,
  ) => {
    try {
      await work();
      setModal(null);
      setNotice(message);
      await refresh();
      if (currentId) await openMessage(currentId);
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    }
  };
  const switchPage = (next: Page) => {
    setPage(next);
    setDetail(null);
    setDeliveryDetail(null);
    setQuery("");
    setStatus("");
    setTopic("");
    setSourceFilter("");
    setOwnerFilter("");
  };
  if (authLoading)
    return (
      <div className="center-screen">
        <div className="spinner" />
        Loading Message Center…
      </div>
    );
  if (!user)
    return (
      <Login
        onLogin={(person) => {
          setPage("Overview");
          setUser(person);
        }}
      />
    );
  const filteredMessages = messages.filter(
    (m) =>
      (!query ||
        `${m.title} ${m.body} ${m.publisher || ""}`
          .toLowerCase()
          .includes(query.toLowerCase())) &&
      (!status || messageStatus(m) === status) &&
      (!topic || (m.topic || "").toLowerCase().includes(topic.toLowerCase())) &&
      (!sourceFilter ||
        (sourceFilter === "manual"
          ? !m.source_id
          : m.source_id === sourceFilter)),
  );
  const filteredDeliveries = deliveries.filter(
    (d) =>
      (!status || d.status === status) &&
      (!ownerFilter || d.owner_id === ownerFilter) &&
      (!query ||
        `${messages.find((m) => m.id === d.message_id)?.title || ""} ${d.message_id}`
          .toLowerCase()
          .includes(query.toLowerCase())),
  );
  const nav: Page[] = [
    "Overview",
    "Messages",
    "Deliveries",
    "Sources",
    "Subscriptions",
  ];
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <span />
            <span />
            <span />
          </div>
          <div>
            <strong>Message Center</strong>
            <small>Operations workspace</small>
          </div>
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {nav.map((item) => (
            <button
              key={item}
              className={page === item ? "active" : ""}
              onClick={() => switchPage(item)}
            >
              <Icon name={item.toLowerCase()} />
              <span>{item}</span>
              {item === "Deliveries" && !!dashboard?.failed && (
                <b>{dashboard.failed}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="environment">
            <span className="live-dot" />
            <div>
              <strong>Demo workspace</strong>
              <small>Manual operations</small>
            </div>
          </div>
          <div className="user-row">
            <div className="avatar">
              {user.name
                .split(" ")
                .map((x) => x[0])
                .join("")
                .slice(0, 2)}
            </div>
            <div>
              <strong>{user.name}</strong>
              <small>{user.owner_id}</small>
            </div>
            <IconButton
              name="logout"
              label="Sign out"
              onClick={() => {
                void send("/auth/logout", "POST")
                  .then(() => setUser(null))
                  .catch((e) => setError(e.message));
              }}
            />
          </div>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div className="breadcrumbs">
            WORKSPACE <span>/</span> <strong>{page.toUpperCase()}</strong>
          </div>
          <div className="top-actions">
            <span className="connection">
              <i /> {error ? "Attention" : "Connected"}
            </span>
            <IconButton
              name="refresh"
              label="Refresh data"
              onClick={() => void refresh()}
              disabled={loading}
            />
            <div className="top-avatar">{user.name[0]}</div>
            <span className="mobile-signout">
              <IconButton
                name="logout"
                label="Sign out"
                onClick={() => {
                  void send("/auth/logout", "POST")
                    .then(() => setUser(null))
                    .catch((e) => setError(e.message));
                }}
              />
            </span>
          </div>
        </header>
        <div className="page-scroll">
          <div className="page-content">
            {page === "Overview" && (
              <Overview
                dashboard={dashboard}
                messages={messages}
                deliveries={deliveries}
                config={config}
                loading={loading}
                openMessage={openMessage}
                navigate={switchPage}
                compose={() => setModal({ type: "message" })}
              />
            )}
            {page === "Messages" && (
              <>
                <PageHeader
                  eyebrow="MESSAGE MANAGEMENT"
                  title="Messages"
                  description="Create, track and maintain messages across your workspace."
                  action={
                    <button
                      className="primary"
                      onClick={() => setModal({ type: "message" })}
                    >
                      <Icon name="plus" size={16} /> Compose message
                    </button>
                  }
                />
                <div className="panel">
                  <div className="panel-toolbar">
                    <div>
                      <h2>
                        All messages{" "}
                        <span className="count">{filteredMessages.length}</span>
                      </h2>
                      <p>Published messages and their current status</p>
                    </div>
                  </div>
                  <div className="filters">
                    <div className="search">
                      <Icon name="search" size={16} />
                      <input
                        aria-label="Search messages"
                        placeholder="Search messages"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </div>
                    <select
                      aria-label="Filter message status"
                      value={status}
                      onChange={(e) => setStatus(e.target.value)}
                    >
                      <option value="">All statuses</option>
                      {["active", "withdrawn", "expired"].map((s) => (
                        <option key={s} value={s}>
                          {titleCase(s)}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label="Filter message source"
                      value={sourceFilter}
                      onChange={(e) => setSourceFilter(e.target.value)}
                    >
                      <option value="">All sources</option>
                      <option value="manual">Manual</option>
                      {sources.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                    <input
                      aria-label="Filter message topic"
                      placeholder="Filter topic"
                      value={topic}
                      onChange={(e) => setTopic(e.target.value)}
                    />
                  </div>
                  {loading && !messages.length ? (
                    <div className="loading">Loading messages…</div>
                  ) : filteredMessages.length ? (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>MESSAGE</th>
                            <th>SOURCE / TOPIC</th>
                            <th>STATUS</th>
                            <th>UPDATED</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredMessages.map((m) => (
                            <tr
                              key={m.id}
                              className="clickable"
                              onClick={() => void openMessage(m.id)}
                            >
                              <td>
                                <button className="row-link">{m.title}</button>
                                <small>{m.body}</small>
                              </td>
                              <td>
                                <span>
                                  {sources.find((s) => s.id === m.source_id)
                                    ?.name || "Manual"}
                                </span>
                                <small>{m.topic || "No topic"}</small>
                              </td>
                              <td>
                                <Badge value={messageStatus(m)} />
                              </td>
                              <td className="subtle">{date(m.updated_at)}</td>
                              <td>
                                <Icon name="arrow" size={16} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty
                      title="No messages found"
                      text={
                        messages.length
                          ? "Try another search or filter."
                          : "Compose a message to get started."
                      }
                    />
                  )}
                </div>
              </>
            )}
            {page === "Deliveries" && (
              <>
                <PageHeader
                  eyebrow="DELIVERY MONITOR"
                  title="Deliveries"
                  description="Follow each message as it moves through the delivery pipeline."
                />
                <div className="panel">
                  <div className="panel-toolbar">
                    <div>
                      <h2>
                        Delivery activity{" "}
                        <span className="count">
                          {filteredDeliveries.length}
                        </span>
                      </h2>
                      <p>Delivery status does not imply a message was read</p>
                    </div>
                  </div>
                  <div className="filters">
                    <div className="search">
                      <Icon name="search" size={16} />
                      <input
                        aria-label="Search deliveries"
                        placeholder="Search messages"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </div>
                    <select
                      aria-label="Filter delivery status"
                      value={status}
                      onChange={(e) => setStatus(e.target.value)}
                    >
                      <option value="">All statuses</option>
                      {[
                        "pending",
                        "accepted",
                        "processed",
                        "failed",
                        "cancelled",
                      ].map((s) => (
                        <option key={s} value={s}>
                          {titleCase(s)}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label="Filter recipient"
                      value={ownerFilter}
                      onChange={(e) => setOwnerFilter(e.target.value)}
                    >
                      <option value="">All recipients</option>
                      {people.map((p) => (
                        <option key={p.owner_id} value={p.owner_id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  {filteredDeliveries.length ? (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>MESSAGE</th>
                            <th>RECIPIENT</th>
                            <th>MODE</th>
                            <th>STATUS</th>
                            <th>UPDATED</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredDeliveries.map((d) => (
                            <tr
                              key={d.id}
                              className="clickable"
                              onClick={() => setDeliveryDetail(d)}
                            >
                              <td>
                                <button className="row-link">
                                  {messages.find((m) => m.id === d.message_id)
                                    ?.title || d.message_id}
                                </button>
                                <small>Version {d.version}</small>
                              </td>
                              <td>{personName(people, d.owner_id)}</td>
                              <td>{titleCase(d.mode)}</td>
                              <td>
                                <Badge value={d.status} />
                              </td>
                              <td className="subtle">{date(d.updated_at)}</td>
                              <td>
                                <Icon name="arrow" size={16} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty
                      title="No deliveries found"
                      text="Delivery activity will appear here when messages are routed."
                    />
                  )}
                </div>
              </>
            )}
            {page === "Sources" && (
              <>
                <PageHeader
                  eyebrow="INGESTION"
                  title="Sources"
                  description="Connect external systems or manage messages manually."
                  action={
                    <button
                      className="primary"
                      onClick={() => setModal({ type: "source" })}
                    >
                      <Icon name="plus" size={16} /> Add source
                    </button>
                  }
                />
                <div className="panel">
                  <div className="panel-toolbar">
                    <div>
                      <h2>
                        Connected sources{" "}
                        <span className="count">{sources.length}</span>
                      </h2>
                      <p>
                        Control which sources can send messages to this
                        workspace
                      </p>
                    </div>
                  </div>
                  {sources.length ? (
                    <div className="source-list">
                      {sources.map((s) => (
                        <article className="source-row" key={s.id}>
                          <div className="source-icon">
                            <Icon name="sources" />
                          </div>
                          <div className="source-info">
                            <div className="inline">
                              <strong>{s.name}</strong>
                              <Badge
                                value={s.enabled ? "enabled" : "disabled"}
                              />
                            </div>
                            <p>
                              {s.type === "poll"
                                ? "HTTP polling"
                                : titleCase(s.type)}{" "}
                              {s.url ? `· ${s.url}` : ""}
                            </p>
                            {s.type === "webhook" && (
                              <small>
                                POST {window.location.origin}/api/ingress/{s.id}
                              </small>
                            )}
                            {s.last_error && (
                              <small className="error-text">
                                {s.last_error}
                              </small>
                            )}
                          </div>
                          <div className="row-actions">
                            <button
                              className="switch"
                              role="switch"
                              aria-checked={s.enabled}
                              aria-label={`${s.enabled ? "Disable" : "Enable"} ${s.name}`}
                              onClick={() =>
                                void action(
                                  () =>
                                    send("/sources/" + s.id, "PATCH", {
                                      enabled: !s.enabled,
                                    }),
                                  "Source updated",
                                )
                              }
                            >
                              <span />
                            </button>
                            <IconButton
                              name="edit"
                              label={`Edit ${s.name}`}
                              onClick={() =>
                                setModal({ type: "source", value: s })
                              }
                            />
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <Empty
                      title="No sources yet"
                      text="Add a webhook or polling source to bring messages in."
                    />
                  )}
                </div>
              </>
            )}
            {page === "Subscriptions" && (
              <>
                <PageHeader
                  eyebrow="ROUTING"
                  title="Subscriptions"
                  description="Choose which topics reach each person and how they are delivered."
                  action={
                    <button
                      className="primary"
                      onClick={() => setModal({ type: "subscription" })}
                    >
                      <Icon name="plus" size={16} /> Add subscription
                    </button>
                  }
                />
                <div className="info-strip">
                  <Icon name="subscriptions" size={17} />
                  <span>
                    Blank channel or topic matches any value. Immediate delivery
                    takes precedence when subscriptions overlap.
                  </span>
                </div>
                <div className="panel">
                  <div className="panel-toolbar">
                    <div>
                      <h2>
                        Subscriptions{" "}
                        <span className="count">{subscriptions.length}</span>
                      </h2>
                      <p>Routing preferences for the demo workspace</p>
                    </div>
                  </div>
                  {subscriptions.length ? (
                    <div className="table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>RECIPIENT</th>
                            <th>CHANNEL</th>
                            <th>TOPIC</th>
                            <th>DELIVERY</th>
                            <th>STATUS</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {subscriptions.map((s) => (
                            <tr key={s.id}>
                              <td>
                                <strong>
                                  {personName(people, s.owner_id)}
                                </strong>
                                <small>{s.owner_id}</small>
                              </td>
                              <td>{s.channel || "Any channel"}</td>
                              <td>{s.topic || "Any topic"}</td>
                              <td>{titleCase(s.mode)}</td>
                              <td>
                                <Badge
                                  value={s.enabled ? "enabled" : "disabled"}
                                />
                              </td>
                              <td>
                                <div className="row-actions">
                                  <button
                                    className="switch"
                                    role="switch"
                                    aria-checked={s.enabled}
                                    aria-label={`${s.enabled ? "Disable" : "Enable"} subscription for ${personName(people, s.owner_id)}`}
                                    onClick={() =>
                                      void action(
                                        () =>
                                          send(
                                            "/subscriptions/" + s.id,
                                            "PATCH",
                                            { enabled: !s.enabled },
                                          ),
                                        "Subscription updated",
                                      )
                                    }
                                  >
                                    <span />
                                  </button>
                                  <IconButton
                                    name="edit"
                                    label={`Edit subscription for ${personName(people, s.owner_id)}`}
                                    onClick={() =>
                                      setModal({
                                        type: "subscription",
                                        value: s,
                                      })
                                    }
                                  />
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty
                      title="No subscriptions yet"
                      text="Add a subscription to route matching messages to a person."
                    />
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </main>
      {detail && (
        <MessageDetail
          message={detail}
          people={people}
          sources={sources}
          config={config}
          close={() => setDetail(null)}
          edit={() => setModal({ type: "message", value: detail })}
          respond={() => setModal({ type: "response", value: detail })}
          withdraw={() => {
            if (
              window.confirm(
                "Withdraw this message? Pending deliveries will be cancelled.",
              )
            )
              void action(
                () => send("/messages/" + detail.id + "/withdraw", "POST"),
                "Message withdrawn",
                detail.id,
              );
          }}
          enrich={() =>
            void action(
              () => send("/messages/" + detail.id + "/enrich", "POST"),
              "Message enriched",
              detail.id,
            )
          }
        />
      )}
      {deliveryDetail && (
        <DeliveryDetail
          delivery={deliveryDetail}
          message={messages.find((m) => m.id === deliveryDetail.message_id)}
          people={people}
          close={() => setDeliveryDetail(null)}
          openMessage={() => void openMessage(deliveryDetail.message_id)}
          retry={() =>
            void action(
              () => send("/deliveries/" + deliveryDetail.id + "/retry", "POST"),
              "Delivery queued for retry",
            ).then(() => setDeliveryDetail(null))
          }
        />
      )}
      {modal?.type === "message" && (
        <MessageForm
          value={modal.value}
          people={people}
          close={() => setModal(null)}
          save={(body) =>
            action(
              () =>
                send(
                  modal.value ? "/messages/" + modal.value.id : "/messages",
                  modal.value ? "PATCH" : "POST",
                  body,
                ),
              modal.value ? "Message updated" : "Message published",
              modal.value?.id,
            )
          }
        />
      )}
      {modal?.type === "source" && (
        <SourceForm
          value={modal.value}
          close={() => setModal(null)}
          save={(body) =>
            void action(
              () =>
                send(
                  modal.value ? "/sources/" + modal.value.id : "/sources",
                  modal.value ? "PATCH" : "POST",
                  body,
                ),
              "Source saved",
            )
          }
        />
      )}
      {modal?.type === "subscription" && (
        <SubscriptionForm
          value={modal.value}
          people={people}
          close={() => setModal(null)}
          save={(body) =>
            void action(
              () =>
                send(
                  modal.value
                    ? "/subscriptions/" + modal.value.id
                    : "/subscriptions",
                  modal.value ? "PATCH" : "POST",
                  body,
                ),
              "Subscription saved",
            )
          }
        />
      )}
      {modal?.type === "response" && (
        <ResponseForm
          message={modal.value}
          people={people}
          user={user}
          close={() => setModal(null)}
          save={(body) =>
            void action(
              () =>
                send(
                  "/messages/" + modal.value.id + "/responses",
                  "POST",
                  body,
                ),
              "Feedback recorded",
              modal.value.id,
            )
          }
        />
      )}
      {error && (
        <div className="toast error-toast" role="alert">
          <Icon name="warning" size={17} />
          <span>{error}</span>
          <IconButton
            name="close"
            label="Dismiss error"
            onClick={() => setError("")}
          />
        </div>
      )}
      {notice && (
        <div className="toast" role="status">
          <Icon name="check" size={17} />
          <span>{notice}</span>
          <IconButton
            name="close"
            label="Dismiss notification"
            onClick={() => setNotice("")}
          />
        </div>
      )}
    </div>
  );
}

function Login({ onLogin }: { onLogin: (person: Person) => void }) {
  const [username, setUsername] = useState("DEV-AAA"),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      onLogin(await send<Person>("/auth/login", "POST", { username }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="login">
      <div className="login-brand">
        <div className="brand-mark">
          <span />
          <span />
          <span />
        </div>
        <strong>Message Center</strong>
      </div>
      <div className="login-card">
        <div className="login-symbol">
          <Icon name="messages" size={23} />
        </div>
        <div className="eyebrow">OPERATIONS WORKSPACE</div>
        <h1>Welcome back.</h1>
        <p>
          Sign in to manage messages, routing and delivery across your
          workspace.
        </p>
        <form onSubmit={submit}>
          <Field label="Demo account">
            <select
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            >
              <option value="DEV-AAA">DEV-AAA · Alex</option>
              <option value="DEV-BBB">DEV-BBB · Maya</option>
              <option value="DEV-CCC">DEV-CCC · Jordan</option>
            </select>
          </Field>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button className="primary login-button" disabled={busy}>
            {busy ? "Signing in…" : "Continue to workspace"}{" "}
            <Icon name="arrow" size={16} />
          </button>
        </form>
        <div className="login-note">
          <span className="live-dot" /> Development environment
        </div>
      </div>
      <div className="login-footer">
        MESSAGE CENTER <span>·</span> OPERATIONS, IN ONE PLACE
      </div>
    </div>
  );
}
function PageHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
function Overview({
  dashboard: d,
  messages,
  deliveries,
  config,
  loading,
  openMessage,
  navigate,
  compose,
}: {
  dashboard: Dashboard | null;
  messages: Message[];
  deliveries: Delivery[];
  config: Config | null;
  loading: boolean;
  openMessage: (id: string) => void;
  navigate: (page: Page) => void;
  compose: () => void;
}) {
  const days = Array.from({ length: 7 }, (_, index) => {
    const day = new Date();
    day.setHours(0, 0, 0, 0);
    day.setDate(day.getDate() - (6 - index));
    const end = new Date(day);
    end.setDate(end.getDate() + 1);
    return {
      label: day.toLocaleDateString("en-US", { weekday: "short" }),
      count: messages.filter(
        (m) => new Date(m.created_at) >= day && new Date(m.created_at) < end,
      ).length,
    };
  });
  const max = Math.max(1, ...days.map((day) => day.count));
  const recent = [...messages]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, 5);
  return (
    <>
      <PageHeader
        eyebrow="WORKSPACE OVERVIEW"
        title="Message operations"
        description="A clear view of what’s moving across your workspace."
        action={
          <button className="primary" onClick={compose}>
            <Icon name="plus" size={16} /> Compose message
          </button>
        }
      />
      <div className="stat-grid">
        <Stat
          label="TOTAL MESSAGES"
          value={d?.messages}
          note="All messages"
          icon="messages"
        />
        <Stat
          label="ACTIVE MESSAGES"
          value={d?.active_messages}
          note="Currently available"
          icon="check"
        />
        <Stat
          label="DELIVERIES"
          value={d?.deliveries}
          note="Across all recipients"
          icon="deliveries"
        />
        <Stat
          label="NEEDS ATTENTION"
          value={d?.failed}
          note="Failed deliveries"
          icon="warning"
          accent
        />
      </div>
      <div className="overview-grid">
        <section className="panel trend-panel">
          <div className="panel-toolbar">
            <div>
              <h2>Message activity</h2>
              <p>Messages created over the last 7 days</p>
            </div>
            <span className="period">LAST 7 DAYS</span>
          </div>
          <div
            className="chart"
            aria-label={
              "Messages created over the last 7 days: " +
              days.map((x) => `${x.label} ${x.count}`).join(", ")
            }
          >
            {days.map((day, index) => (
              <div className="chart-column" key={index}>
                <div className="chart-track">
                  <div
                    className={"chart-bar " + (index === 6 ? "today" : "")}
                    style={{
                      height: `${Math.max(day.count ? 8 : 2, (day.count / max) * 100)}%`,
                    }}
                    title={`${day.count} messages`}
                  />
                </div>
                <span>{day.label}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="panel pipeline">
          <div className="panel-toolbar">
            <div>
              <h2>Delivery pipeline</h2>
              <p>Current delivery statuses</p>
            </div>
            <button
              className="text-link"
              onClick={() => navigate("Deliveries")}
            >
              View all <Icon name="arrow" size={14} />
            </button>
          </div>
          <div className="pipeline-total">
            <strong>{d?.deliveries ?? "—"}</strong>
            <span>total deliveries</span>
          </div>
          <div className="pipeline-bar">
            {(
              [
                "processed",
                "accepted",
                "pending",
                "failed",
                "cancelled",
              ] as const
            ).map((s) => (
              <span
                key={s}
                className={s}
                style={{
                  width: `${d?.deliveries ? (d[s] / d.deliveries) * 100 : 0}%`,
                }}
              />
            ))}
          </div>
          <div className="pipeline-list">
            {(
              [
                "processed",
                "accepted",
                "pending",
                "failed",
                "cancelled",
              ] as const
            ).map((s) => (
              <div key={s}>
                <span>
                  <i className={s} />
                  {titleCase(s)}
                </span>
                <strong>{d?.[s] ?? "—"}</strong>
              </div>
            ))}
          </div>
        </section>
      </div>
      <div className="overview-grid bottom-grid">
        <section className="panel recent">
          <div className="panel-toolbar">
            <div>
              <h2>Recent messages</h2>
              <p>Latest updates across your workspace</p>
            </div>
            <button className="text-link" onClick={() => navigate("Messages")}>
              View all <Icon name="arrow" size={14} />
            </button>
          </div>
          {recent.length ? (
            <div className="recent-list">
              {recent.map((m) => (
                <button key={m.id} onClick={() => openMessage(m.id)}>
                  <span className="recent-icon">
                    <Icon name="messages" size={16} />
                  </span>
                  <span className="recent-copy">
                    <strong>{m.title}</strong>
                    <small>
                      {m.topic || "General"} <span>·</span> {date(m.updated_at)}
                    </small>
                  </span>
                  <Badge value={messageStatus(m)} />
                  <Icon name="arrow" size={15} />
                </button>
              ))}
            </div>
          ) : (
            <Empty
              title={loading ? "Loading messages…" : "No messages yet"}
              text="Your recent messages will appear here."
            />
          )}
        </section>
        <section className="panel system">
          <div className="panel-toolbar">
            <div>
              <h2>Workspace status</h2>
              <p>Integration configuration</p>
            </div>
          </div>
          <div className="system-list">
            <div>
              <span>
                <i className={config?.duet_configured ? "good" : ""} /> Duet
                delivery
              </span>
              <strong>
                {config?.duet_configured ? "Configured" : "Not configured"}
              </strong>
            </div>
            <div>
              <span>
                <i className={config?.service_configured ? "good" : ""} />{" "}
                Service connection
              </span>
              <strong>
                {config?.service_configured ? "Configured" : "Not configured"}
              </strong>
            </div>
            <div>
              <span>
                <i className={config?.enrichment_enabled ? "good" : ""} /> AI
                enrichment
              </span>
              <strong>
                {config?.enrichment_enabled ? "Available" : "Not configured"}
              </strong>
            </div>
          </div>
          <div className="system-note">
            AI enrichment is optional and runs only when requested on a message.
          </div>
        </section>
      </div>
      <div className="footer-note">
        <span className="live-dot" /> {deliveries.length} delivery records in
        this workspace <span>·</span> Updated when refreshed
      </div>
    </>
  );
}
function Stat({
  label,
  value,
  note,
  icon,
  accent,
}: {
  label: string;
  value?: number;
  note: string;
  icon: string;
  accent?: boolean;
}) {
  return (
    <div className="stat">
      <div className="stat-top">
        <span>{label}</span>
        <div className={accent ? "stat-icon accent" : "stat-icon"}>
          <Icon name={icon} size={16} />
        </div>
      </div>
      <strong>{value ?? "—"}</strong>
      <small>{note}</small>
    </div>
  );
}
function MessageDetail({
  message: m,
  people,
  sources,
  config,
  close,
  edit,
  respond,
  withdraw,
  enrich,
}: {
  message: Message;
  people: Person[];
  sources: Source[];
  config: Config | null;
  close: () => void;
  edit: () => void;
  respond: () => void;
  withdraw: () => void;
  enrich: () => void;
}) {
  return (
    <div
      className="drawer-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <aside className="drawer" aria-label="Message details">
        <header>
          <div>
            <span className="eyebrow">MESSAGE DETAIL</span>
            <h2>{m.title}</h2>
          </div>
          <IconButton name="close" label="Close details" onClick={close} />
        </header>
        <div className="drawer-content">
          <div className="detail-actions">
            <Badge value={messageStatus(m)} />
            <span className="version">VERSION {m.version}</span>
            <div className="spacer" />
            <IconButton
              name="edit"
              label="Edit message"
              onClick={edit}
              disabled={m.status !== "active"}
            />
            <button className="secondary small" onClick={respond}>
              Add feedback
            </button>
          </div>
          <div className="detail-body">{m.body}</div>
          <div className="detail-meta">
            <div>
              <span>Publisher</span>
              <strong>{m.publisher || "—"}</strong>
            </div>
            <div>
              <span>Source</span>
              <strong>
                {sources.find((s) => s.id === m.source_id)?.name || "Manual"}
              </strong>
            </div>
            <div>
              <span>Topic</span>
              <strong>{m.topic || "—"}</strong>
            </div>
            <div>
              <span>Channel</span>
              <strong>{m.channel || "—"}</strong>
            </div>
            <div>
              <span>Created</span>
              <strong>{date(m.created_at)}</strong>
            </div>
            <div>
              <span>Updated</span>
              <strong>{date(m.updated_at)}</strong>
            </div>
            <div>
              <span>Expires</span>
              <strong>{date(m.expires_at)}</strong>
            </div>
            <div>
              <span>Message ID</span>
              <strong className="mono">{m.id}</strong>
            </div>
          </div>
          <section className="detail-section">
            <div className="section-heading">
              <h3>Recipients & delivery</h3>
              <span>{m.deliveries?.length || 0}</span>
            </div>
            {m.deliveries?.length ? (
              m.deliveries.map((d) => (
                <div className="detail-row" key={d.id}>
                  <span className="mini-avatar">
                    {personName(people, d.owner_id)[0]}
                  </span>
                  <div>
                    <strong>{personName(people, d.owner_id)}</strong>
                    <small>
                      {titleCase(d.mode)} · Version {d.version}
                    </small>
                    {d.last_error && (
                      <small className="error-text">{d.last_error}</small>
                    )}
                  </div>
                  <Badge value={d.status} />
                </div>
              ))
            ) : (
              <p className="detail-empty">
                No delivery records for this message.
              </p>
            )}
          </section>
          <section className="detail-section">
            <div className="section-heading">
              <h3>Feedback</h3>
              <span>{m.responses?.length || 0}</span>
            </div>
            <div className="feedback-counts">
              {["acknowledge", "attending", "declined"].map((k) => (
                <div key={k}>
                  <strong>{m.response_counts?.[k] || 0}</strong>
                  <span>{titleCase(k)}</span>
                </div>
              ))}
            </div>
            {m.responses?.map((r, i) => (
              <div className="response-row" key={i}>
                <div>
                  <strong>{personName(people, r.owner_id)}</strong>{" "}
                  <Badge value={r.response} />
                </div>
                {r.note && <p>{r.note}</p>}
                <small>{date(r.updated_at)}</small>
              </div>
            ))}
          </section>
          <section className="detail-section">
            <div className="section-heading">
              <h3>Version history</h3>
              <span>{m.revisions?.length || 0}</span>
            </div>
            {m.revisions?.length ? (
              m.revisions.map((r, i) => (
                <details className="revision" key={i}>
                  <summary>
                    <strong>Version {r.version}</strong>
                    <span>{date(r.created_at)}</span>
                  </summary>
                  <p>{r.content.title}</p>
                  <p>{r.content.body}</p>
                </details>
              ))
            ) : (
              <p className="detail-empty">No earlier versions.</p>
            )}
          </section>
          <section className="detail-section">
            <div className="section-heading">
              <h3>AI enrichment</h3>
            </div>
            <p className="detail-empty">
              {config?.enrichment_enabled
                ? "Generate optional enrichment for this message."
                : "Not configured for this workspace."}
            </p>
            {m.enrichment != null && (
              <pre className="enrichment">
                {typeof m.enrichment === "string"
                  ? m.enrichment
                  : JSON.stringify(m.enrichment, null, 2)}
              </pre>
            )}
            <button
              className="secondary small"
              disabled={!config?.enrichment_enabled}
              onClick={enrich}
            >
              <Icon name="spark" size={15} /> Enrich message
            </button>
          </section>
          {m.status === "active" && (
            <div className="danger-zone">
              <button className="danger-link" onClick={withdraw}>
                Withdraw message
              </button>
              <p>Pending deliveries will be cancelled.</p>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
function DeliveryDetail({
  delivery: d,
  message,
  people,
  close,
  openMessage,
  retry,
}: {
  delivery: Delivery;
  message?: Message;
  people: Person[];
  close: () => void;
  openMessage: () => void;
  retry: () => void;
}) {
  return (
    <div
      className="drawer-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <aside className="drawer" aria-label="Delivery details">
        <header>
          <div>
            <span className="eyebrow">DELIVERY DETAIL</span>
            <h2>{message?.title || "Delivery"}</h2>
          </div>
          <IconButton name="close" label="Close details" onClick={close} />
        </header>
        <div className="drawer-content">
          <div className="detail-actions">
            <Badge value={d.status} />
            <span className="version">VERSION {d.version}</span>
          </div>
          <div className="detail-meta single">
            <div>
              <span>Recipient</span>
              <strong>{personName(people, d.owner_id)}</strong>
            </div>
            <div>
              <span>Mode</span>
              <strong>{titleCase(d.mode)}</strong>
            </div>
            <div>
              <span>Attempts</span>
              <strong>{d.attempts}</strong>
            </div>
            <div>
              <span>Owner update confirmed</span>
              <strong>{d.notified ? "Confirmed" : "Not confirmed"}</strong>
            </div>
            <div>
              <span>Human read</span>
              <strong>{d.human_read ? "Yes" : "No"}</strong>
            </div>
            <div>
              <span>Created</span>
              <strong>{date(d.created_at)}</strong>
            </div>
            <div>
              <span>Updated</span>
              <strong>{date(d.updated_at)}</strong>
            </div>
            <div>
              <span>Delivery ID</span>
              <strong className="mono">{d.id}</strong>
            </div>
          </div>
          {d.last_error && (
            <div className="error-box">
              <strong>Last error</strong>
              <p>{d.last_error}</p>
            </div>
          )}
          {d.summary && (
            <div className="detail-section">
              <h3>Summary</h3>
              <p>{d.summary}</p>
            </div>
          )}
          <div className="drawer-buttons">
            <button className="secondary" onClick={openMessage}>
              View message <Icon name="arrow" size={15} />
            </button>
            {d.status === "failed" && (
              <button className="primary" onClick={retry}>
                <Icon name="refresh" size={15} /> Retry delivery
              </button>
            )}
          </div>
        </div>
      </aside>
    </div>
  );
}

function MessageForm({
  value,
  people,
  close,
  save,
}: {
  value?: Message;
  people: Person[];
  close: () => void;
  save: (body: unknown) => Promise<boolean>;
}) {
  const [requestKey] = useState(() => crypto.randomUUID()),
    [busy, setBusy] = useState(false);
  const [title, setTitle] = useState(value?.title || ""),
    [body, setBody] = useState(value?.body || ""),
    [publisher, setPublisher] = useState(value?.publisher || ""),
    [topic, setTopic] = useState(value?.topic || ""),
    [channel, setChannel] = useState(value?.channel || ""),
    [kind, setKind] = useState(value?.kind || "announcement"),
    [recipients, setRecipients] = useState<string[]>(value?.recipients || []),
    [expires, setExpires] = useState(
      value?.expires_at
        ? new Date(
            new Date(value.expires_at).getTime() -
              new Date(value.expires_at).getTimezoneOffset() * 60000,
          )
            .toISOString()
            .slice(0, 16)
        : "",
    );
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    await save({
      title,
      body,
      publisher: publisher || null,
      topic: topic || null,
      channel: channel || null,
      kind,
      recipients,
      expires_at: expires ? new Date(expires).toISOString() : null,
      ...(!value ? { client_request_key: requestKey } : {}),
    });
    setBusy(false);
  };
  return (
    <ModalFrame
      title={value ? "Edit message" : "Compose message"}
      subtitle={
        value
          ? "Saving creates a new version and updates routing."
          : "Publish an update to your workspace."
      }
      close={close}
    >
      <form onSubmit={submit}>
        <Field label="Title">
          <input
            required
            maxLength={300}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Give this message a clear title"
          />
        </Field>
        <Field label="Message">
          <textarea
            aria-label="Message"
            required
            rows={5}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Write your message…"
          />
        </Field>
        <div className="form-grid">
          <Field label="Publisher">
            <input
              value={publisher}
              onChange={(e) => setPublisher(e.target.value)}
              placeholder="Name or team"
            />
          </Field>
          <Field label="Type">
            <input
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              placeholder="announcement"
            />
          </Field>
          <Field label="Topic">
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g. operations"
            />
          </Field>
          <Field label="Channel">
            <input
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              placeholder="e.g. updates"
            />
          </Field>
        </div>
        <Field label="Expires at" hint="Optional. Leave blank for no expiry.">
          <input
            type="datetime-local"
            value={expires}
            onChange={(e) => setExpires(e.target.value)}
          />
        </Field>
        <fieldset className="recipient-field">
          <legend>Recipients</legend>
          <p>
            Select people to override subscriptions. Leave all unselected to use
            matching subscriptions.
          </p>
          <div className="recipient-options">
            {people.map((p) => (
              <label key={p.owner_id}>
                <input
                  type="checkbox"
                  checked={recipients.includes(p.owner_id)}
                  onChange={(e) =>
                    setRecipients(
                      e.target.checked
                        ? [...recipients, p.owner_id]
                        : recipients.filter((x) => x !== p.owner_id),
                    )
                  }
                />
                <span>{p.name}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={close}>
            Cancel
          </button>
          <button className="primary" disabled={busy}>
            {busy ? "Saving…" : value ? "Save changes" : "Publish message"}
          </button>
        </div>
      </form>
    </ModalFrame>
  );
}
function SourceForm({
  value,
  close,
  save,
}: {
  value?: Source;
  close: () => void;
  save: (body: unknown) => void;
}) {
  const [name, setName] = useState(value?.name || ""),
    [type, setType] = useState(value?.type || "webhook"),
    [url, setUrl] = useState(value?.url || ""),
    [token, setToken] = useState(""),
    [interval, setInterval] = useState(value?.poll_interval_seconds || 60),
    [enabled, setEnabled] = useState(value?.enabled ?? true);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save({
      name,
      type,
      enabled,
      url: type === "poll" ? url : null,
      ...(type === "poll" ? { poll_interval_seconds: Number(interval) } : {}),
      ...(token ? { token } : {}),
    });
  };
  return (
    <ModalFrame
      title={value ? "Edit source" : "Add source"}
      subtitle="Configure a source for incoming messages."
      close={close}
    >
      <form onSubmit={submit}>
        <Field label="Source name">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Operations webhook"
          />
        </Field>
        <Field label="Source type">
          <select
            value={type}
            onChange={(e) => setType(e.target.value as Source["type"])}
          >
            <option value="webhook">Webhook</option>
            <option value="poll">HTTP polling</option>
            <option value="manual">Manual</option>
          </select>
        </Field>
        {type === "poll" && (
          <>
            <Field
              label="JSON endpoint URL"
              hint="The endpoint should return a message object or an array of messages."
            >
              <input
                required
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com/messages"
              />
            </Field>
            <Field label="Poll interval (seconds)">
              <input
                required
                type="number"
                min="10"
                value={interval}
                onChange={(e) => setInterval(Number(e.target.value))}
              />
            </Field>
          </>
        )}
        {type !== "manual" && (
          <Field
            label={value ? "Replace token" : "Source token"}
            hint={
              value
                ? "Leave blank to keep the current token. Tokens are never displayed."
                : type === "webhook"
                  ? "Send this token in the X-Source-Token header. It will not be displayed again."
                  : "Optional token for the polling endpoint. It will not be displayed again."
            }
          >
            <input
              required={!value && type === "webhook"}
              type="password"
              autoComplete="new-password"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder={value ? "Unchanged" : "Enter a token"}
            />
          </Field>
        )}
        <label className="check-label">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />{" "}
          Source enabled
        </label>
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={close}>
            Cancel
          </button>
          <button className="primary">
            {value ? "Save changes" : "Add source"}
          </button>
        </div>
      </form>
    </ModalFrame>
  );
}
function SubscriptionForm({
  value,
  people,
  close,
  save,
}: {
  value?: Subscription;
  people: Person[];
  close: () => void;
  save: (body: unknown) => void;
}) {
  const [owner, setOwner] = useState(
      value?.owner_id || people[0]?.owner_id || "",
    ),
    [topic, setTopic] = useState(value?.topic || ""),
    [channel, setChannel] = useState(value?.channel || ""),
    [mode, setMode] = useState(value?.mode || "immediate"),
    [enabled, setEnabled] = useState(value?.enabled ?? true);
  return (
    <ModalFrame
      title={value ? "Edit subscription" : "Add subscription"}
      subtitle="Route matching messages to a person."
      close={close}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save({
            owner_id: owner,
            topic: topic || null,
            channel: channel || null,
            mode,
            enabled,
          });
        }}
      >
        <Field label="Recipient">
          <select
            required
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
          >
            {people.map((p) => (
              <option key={p.owner_id} value={p.owner_id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <div className="form-grid">
          <Field label="Topic" hint="Blank matches any topic.">
            <input
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="Any topic"
            />
          </Field>
          <Field label="Channel" hint="Blank matches any channel.">
            <input
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
              placeholder="Any channel"
            />
          </Field>
        </div>
        <Field label="Delivery mode">
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as Subscription["mode"])}
          >
            <option value="immediate">Immediate</option>
            <option value="digest">Digest</option>
          </select>
        </Field>
        <label className="check-label">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />{" "}
          Subscription enabled
        </label>
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={close}>
            Cancel
          </button>
          <button className="primary">
            {value ? "Save changes" : "Add subscription"}
          </button>
        </div>
      </form>
    </ModalFrame>
  );
}
function ResponseForm({
  message,
  people,
  user,
  close,
  save,
}: {
  message: Message;
  people: Person[];
  user: Person;
  close: () => void;
  save: (body: unknown) => void;
}) {
  const [owner, setOwner] = useState(user.owner_id),
    [response, setResponse] = useState("acknowledge"),
    [note, setNote] = useState("");
  return (
    <ModalFrame
      title="Add feedback"
      subtitle={`Record a response to “${message.title}”.`}
      close={close}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          save({ owner_id: owner, response, note: note || null });
        }}
      >
        <Field label="Person">
          <select value={owner} onChange={(e) => setOwner(e.target.value)}>
            {people.map((p) => (
              <option key={p.owner_id} value={p.owner_id}>
                {p.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Response">
          <select
            value={response}
            onChange={(e) => setResponse(e.target.value)}
          >
            <option value="acknowledge">Acknowledge</option>
            <option value="attending">Attending</option>
            <option value="declined">Declined</option>
          </select>
        </Field>
        <Field label="Note (optional)">
          <textarea
            rows={3}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Add context…"
          />
        </Field>
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={close}>
            Cancel
          </button>
          <button className="primary">Record feedback</button>
        </div>
      </form>
    </ModalFrame>
  );
}
