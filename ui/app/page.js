"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { ingestRepo, getIngestStatus, streamChat } from "./lib/api";

export default function Home() {
  // ── State ──────────────────────────────────────
  const [repoUrl, setRepoUrl] = useState("");
  const [repoId, setRepoId] = useState(null);
  const [ingestState, setIngestState] = useState(null); // null | {status, chunk_count, ...}
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [ingesting, setIngesting] = useState(false);

  const chatRef = useRef(null);
  const questionRef = useRef(null);
  const pollRef = useRef(null);

  // Restore session from localStorage
  useEffect(() => {
    if (typeof window === "undefined") return;
    const savedRepo = localStorage.getItem("rag_repo_id");
    const savedUrl = localStorage.getItem("rag_repo_url");
    const savedSession = localStorage.getItem("rag_session_id");
    if (savedRepo) {
      setRepoId(savedRepo);
      setRepoUrl(savedUrl || "");
      setSessionId(savedSession);
      setIngestState({ status: "READY" });
    }
  }, []);

  // Auto-scroll chat
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

  // ── Ingest ─────────────────────────────────────
  const handleIngest = useCallback(async (e) => {
    e.preventDefault();
    if (!repoUrl.trim() || ingesting) return;

    setIngesting(true);
    setIngestState({ status: "PROCESSING" });
    setMessages([]);
    setSessionId(null);

    try {
      const data = await ingestRepo(repoUrl.trim());
      setRepoId(data.repo_id);

      if (data.status === "READY") {
        setIngestState({ status: "READY", ...data });
        setIngesting(false);
        localStorage.setItem("rag_repo_id", data.repo_id);
        localStorage.setItem("rag_repo_url", repoUrl.trim());
        questionRef.current?.focus();
        return;
      }

      // Poll for status
      pollRef.current = setInterval(async () => {
        try {
          const status = await getIngestStatus(data.repo_id);
          setIngestState(status);

          if (status.status === "READY" || status.status === "FAILED") {
            clearInterval(pollRef.current);
            setIngesting(false);
            if (status.status === "READY") {
              localStorage.setItem("rag_repo_id", data.repo_id);
              localStorage.setItem("rag_repo_url", repoUrl.trim());
              questionRef.current?.focus();
            }
          }
        } catch {
          clearInterval(pollRef.current);
          setIngesting(false);
        }
      }, 3000);
    } catch (err) {
      setIngestState({ status: "FAILED", error_message: err.message });
      setIngesting(false);
    }
  }, [repoUrl, ingesting]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ── Chats ───────────────────────────────────────
  const handleAsk = useCallback(async (e) => {
    e.preventDefault();
    if (!question.trim() || streaming || !repoId) return;

    const q = question.trim();
    setQuestion("");
    setStreaming(true);

    // Add user message
    setMessages((prev) => [...prev, { role: "user", content: q }]);

    // Add empty assistant message (will be streamed into)
    const assistantIdx = messages.length + 1;
    setMessages((prev) => [...prev, { role: "assistant", content: "", sources: [] }]);

    let fullText = "";

    await streamChat(repoId, q, sessionId, {
      onSession: (sid) => {
        setSessionId(sid);
        localStorage.setItem("rag_session_id", sid);
      },
      onToken: (token) => {
        fullText += token;
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === "assistant") {
            updated[updated.length - 1] = { ...last, content: fullText };
          }
          return updated;
        });
      },
      onSources: (sources) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === "assistant") {
            updated[updated.length - 1] = { ...last, sources };
          }
          return updated;
        });
      },
      onDone: () => {
        setStreaming(false);
      },
      onError: (err) => {
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (last?.role === "assistant") {
            updated[updated.length - 1] = {
              ...last,
              content: `Error: ${err}`,
            };
          }
          return updated;
        });
        setStreaming(false);
      },
    });
  }, [question, streaming, repoId, sessionId, messages.length]);

  // ── Render ─────────────────────────────────────
  const isReady = ingestState?.status === "READY";

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <h1>code rag</h1>
        {repoId && (
          <span className="status">
            {repoId.replace("github_", "").replace(/_[a-f0-9]+$/, "").replace(/_/g, "/")}
          </span>
        )}
      </header>

      {/* Repo Input */}
      <div className="repo-input-area">
        <form className="repo-form" onSubmit={handleIngest}>
          <input
            type="text"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="github.com/user/repo"
            disabled={ingesting}
          />
          <button type="submit" disabled={ingesting || !repoUrl.trim()}>
            {ingesting ? "ingesting" : "ingest"}
          </button>
        </form>

        {/* Ingestion Status */}
        {ingestState && (
          <div className="ingest-status">
            <span className={`dot ${ingestState.status?.toLowerCase()}`} />
            <span>
              {ingestState.status === "PROCESSING" && (
                <span className="loading-dots">processing</span>
              )}
              {ingestState.status === "READY" && (
                <span>
                  ready
                  {ingestState.chunk_count > 0 && (
                    <span className="ingest-meta">
                      {" "}&middot; {ingestState.chunk_count} chunks
                    </span>
                  )}
                </span>
              )}
              {ingestState.status === "FAILED" && (
                <span style={{ color: "var(--red)" }}>
                  failed{ingestState.error_message && `: ${ingestState.error_message}`}
                </span>
              )}
            </span>
          </div>
        )}
      </div>

      {/* Chat Area */}
      <div className="chat-area" ref={chatRef}>
        {messages.length === 0 && isReady && (
          <div className="empty-state">
            ask anything about the codebase
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className="message">
            <span className="role">{msg.role}</span>
            <div className={`content ${msg.role === "assistant" && streaming && i === messages.length - 1 ? "streaming-cursor" : ""}`}>
              {msg.content}
            </div>

            {/* Source citations */}
            {msg.sources?.length > 0 && (
              <div className="sources">
                <span className="sources-label">sources</span>
                {msg.sources.map((src, j) => (
                  <div key={j} className="source-item">
                    <span className="file">
                      {src.file_path}:{src.start_line}-{src.end_line}
                    </span>
                    <span className="sim">{(src.similarity * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Question Input */}
      {isReady && (
        <div className="question-area">
          <form className="question-form" onSubmit={handleAsk}>
            <input
              ref={questionRef}
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="ask a question..."
              disabled={streaming}
              autoFocus
            />
            <button type="submit" disabled={streaming || !question.trim()}>
              {streaming ? "..." : "ask"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
