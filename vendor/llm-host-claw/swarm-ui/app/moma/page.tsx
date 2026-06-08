"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type SessionEntry = {
  session_id: string;
  created_at?: string;
  prompt?: string;
};

type ResponseEvent = {
  type?: string;
  agent?: { name?: string; kind?: string };
  data?: Record<string, unknown>;
};

const BACKEND_ORIGIN =
  (process.env.NEXT_PUBLIC_BACKEND_ORIGIN || "").trim().replace(/\/$/, "") || "";

function backendUrl(path: string): string {
  if (!BACKEND_ORIGIN) return path;
  return `${BACKEND_ORIGIN}${path}`;
}

function formatTime(value?: string): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function MomaPage() {
  const [sessions, setSessions] = useState<SessionEntry[]>([]);
  const [sessionId, setSessionId] = useState<string>("");
  const [prompt, setPrompt] = useState("");
  const [events, setEvents] = useState<ResponseEvent[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    try {
      const res = await fetch(backendUrl("/api/web/sessions"), { cache: "no-store" });
      if (!res.ok) {
        throw new Error(`Failed to load sessions: ${res.status}`);
      }
      const payload = await res.json();
      const nextSessions = Array.isArray(payload.sessions) ? payload.sessions : [];
      setSessions(nextSessions);
      if (!sessionId && nextSessions.length > 0) {
        setSessionId(nextSessions[0].session_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [sessionId]);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  async function resumeSelected(targetSessionId: string) {
    if (!targetSessionId) return;
    const res = await fetch(
      backendUrl(`/api/web/history/latest?session_id=${encodeURIComponent(targetSessionId)}`),
      { cache: "no-store" },
    );
    const payload = await res.json();
    setEvents(Array.isArray(payload.events) ? payload.events : []);
  }

  async function sendPrompt() {
    const message = prompt.trim();
    if (!message || sending) return;
    setSending(true);
    setError(null);
    setPrompt("");
    setEvents((prev) => [
      ...prev,
      { type: "response.output_text.delta", agent: { name: "you", kind: "user" }, data: { delta: message } },
    ]);
    try {
      const response = await fetch(backendUrl("/api/orchestrator/run"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId || undefined, userspace: null }),
      });
      if (!response.body) throw new Error("Missing response stream");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop() || "";
        for (const chunk of chunks) {
          const dataLine = chunk.split("\n").find((line) => line.startsWith("data: "));
          if (!dataLine) continue;
          try {
            const parsed = JSON.parse(dataLine.slice(6)) as ResponseEvent;
            setEvents((prev) => [...prev, parsed]);
          } catch {
            // ignore malformed chunks
          }
        }
      }
      await loadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSending(false);
    }
  }

  const messageBlocks = useMemo(() => {
    const blocks: Array<{ role: string; kind: string; text: string }> = [];
    for (const event of events) {
      if (event.type === "response.output_text.delta") {
        const role = event.agent?.name || "agent";
        const text = String(event.data?.delta || "");
        const prev = blocks[blocks.length - 1];
        if (prev && prev.role === role && prev.kind === "message") {
          prev.text += text;
        } else {
          blocks.push({ role, kind: "message", text });
        }
      } else if (event.type?.includes("tool_call")) {
        blocks.push({ role: event.agent?.name || "tool", kind: "tool", text: String(event.data?.name || event.type) });
      } else if (event.type?.includes("subagent")) {
        blocks.push({ role: event.agent?.name || "subagent", kind: "subagent", text: String(event.data?.subagent_name || event.type) });
      }
    }
    return blocks;
  }, [events]);

  return (
    <div className="moma-layout">
      <aside className="moma-sidebar">
        <div className="header" style={{ flexDirection: "column", alignItems: "flex-start", gap: 8 }}>
          <div className="eyebrow">MOMA</div>
          <div style={{ fontSize: 28, fontWeight: 800, letterSpacing: "0.08em" }}>Web Console</div>
          <div className="muted">Resume local sessions and stream live agent output</div>
        </div>
        <div className="list">
          {sessions.map((item) => (
            <button
              key={item.session_id}
              className={`row ${item.session_id === sessionId ? "active" : ""}`}
              onClick={() => setSessionId(item.session_id)}
            >
              <div style={{ fontWeight: 700 }}>{item.session_id}</div>
              <div className="muted mono" style={{ fontSize: 12 }}>{formatTime(item.created_at)}</div>
              <div className="muted" style={{ marginTop: 6 }}>{item.prompt || "—"}</div>
            </button>
          ))}
          {sessions.length === 0 ? <div className="empty">No local sessions yet.</div> : null}
        </div>
      </aside>

      <main className="moma-main">
        <div className="header" style={{ alignItems: "center" }}>
          <div>
            <div className="eyebrow">Current Session</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{sessionId || "new session"}</div>
          </div>
          <button className="btn" onClick={() => void resumeSelected(sessionId)} disabled={!sessionId}>
            Resume Session
          </button>
        </div>

        <div className="chat" style={{ display: "grid", gap: 16 }}>
          {messageBlocks.map((item, index) => (
            <article
              key={`${item.role}-${index}`}
              className="card"
              style={{
                padding: 16,
                borderRadius: 18,
                background: item.role === "you" ? "#10213a" : "var(--surface-1)",
                color: item.role === "you" ? "#fff" : "var(--text-body)",
                marginLeft: item.role === "you" ? "auto" : 0,
                maxWidth: item.role === "you" ? "78%" : "82%",
                boxShadow: "var(--shadow-card)",
              }}
            >
              <div className="mono" style={{ fontSize: 12, opacity: 0.72, marginBottom: 8 }}>
                {item.kind.toUpperCase()} · {item.role}
              </div>
              <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{item.text || "—"}</div>
            </article>
          ))}
          {messageBlocks.length === 0 ? <div className="empty">No messages yet.</div> : null}
        </div>

        <div style={{ borderTop: "1px solid var(--line-strong)", padding: 16, display: "grid", gap: 10 }}>
          {error ? <div className="toast" style={{ color: "var(--red-strong)" }}>{error}</div> : null}
          <textarea
            className="input"
            style={{ minHeight: 110, resize: "vertical" }}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Type a prompt. Ctrl/Cmd+Enter to send."
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                event.preventDefault();
                void sendPrompt();
              }
            }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <div className="muted">Streams standard `response.*` SSE from MOMA backend</div>
            <button className="btn btn-primary" onClick={() => void sendPrompt()} disabled={sending}>
              {sending ? "Streaming..." : "Send"}
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
