"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { ingestRepo, getIngestStatus, streamChat, clearToken } from "./lib/api";

const SAMPLE_REPOS = [
  { name: "sindresorhus/is", url: "https://github.com/sindresorhus/is", note: "Indexed (275 chunks)" },
  { name: "expressjs/express", url: "https://github.com/expressjs/express", note: "Node.js framework" },
  { name: "pallets/flask", url: "https://github.com/pallets/flask", note: "Python web microframework" },
];

const SUGGESTED_QUESTIONS = [
  "What are the main functions and types exported by this repository?",
  "How does type checking and validation work under the hood?",
  "Show an example of how to use this library in production.",
];

/** Minimalist markdown formatter for code blocks, inline code, lists and paragraphs */
function FormattedMessage({ content }) {
  if (!content) return null;

  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="message-body">
      {parts.map((part, idx) => {
        if (!part) return null;

        if (part.startsWith("```") && part.endsWith("```")) {
          const lines = part.slice(3, -3).replace(/^\r?\n/, "").split(/\r?\n/);
          let lang = "code";
          let codeText = part.slice(3, -3).trim();

          if (lines.length > 1 && /^[a-zA-Z0-9_-]+$/.test(lines[0].trim())) {
            lang = lines[0].trim();
            codeText = lines.slice(1).join("\n");
          }

          return <CodeSnippetBlock key={idx} language={lang} code={codeText} />;
        }

        const paragraphs = part.split(/\n\n+/);
        return paragraphs.map((para, pIdx) => {
          const trimmed = para.trim();
          if (!trimmed) return null;

          if (trimmed.split("\n").every((l) => l.trim().startsWith("- ") || l.trim().startsWith("* "))) {
            const items = trimmed.split("\n").map((l) => l.replace(/^[-*]\s+/, ""));
            return (
              <ul key={`${idx}-${pIdx}`}>
                {items.map((item, iIdx) => (
                  <li key={iIdx}>
                    <InlineFormattedText text={item} />
                  </li>
                ))}
              </ul>
            );
          }

          return (
            <p key={`${idx}-${pIdx}`}>
              <InlineFormattedText text={trimmed} />
            </p>
          );
        });
      })}
    </div>
  );
}

/** Render inline text with code backticks and bold text */
function InlineFormattedText({ text }) {
  if (!text) return null;

  const codeParts = text.split(/(`[^`]+`)/g);

  return (
    <>
      {codeParts.map((piece, cIdx) => {
        if (piece.startsWith("`") && piece.endsWith("`") && piece.length >= 2) {
          const codeVal = piece.slice(1, -1);
          return (
            <code key={cIdx} className="inline-code">
              {codeVal}
            </code>
          );
        }

        const boldParts = piece.split(/(\*\*[^*]+\*\*)/g);
        return boldParts.map((bPiece, bIdx) => {
          if (bPiece.startsWith("**") && bPiece.endsWith("**") && bPiece.length >= 4) {
            return <strong key={`${cIdx}-${bIdx}`}>{bPiece.slice(2, -2)}</strong>;
          }
          return <span key={`${cIdx}-${bIdx}`}>{bPiece}</span>;
        });
      })}
    </>
  );
}

/** Copyable syntax-styled code block */
function CodeSnippetBlock({ language, code }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard?.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="code-block-wrapper">
      <div className="code-block-header">
        <span>{language}</span>
        <button type="button" className="copy-btn" onClick={handleCopy}>
          {copied ? "Copied" : "Copy code"}
        </button>
      </div>
      <pre className="code-pre">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/** Grounded source citation item */
function CitationItem({ source }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="source-card">
      <div className="source-title-row" onClick={() => setExpanded(!expanded)}>
        <code className="source-path">
          {source.file_path}:{source.start_line}-{source.end_line}
        </code>
        <span className="source-sim">
          {(source.similarity * 100).toFixed(0)}% match {expanded ? "▲" : "▼"}
        </span>
      </div>
      {expanded && source.snippet && (
        <code className="source-snippet">{source.snippet}</code>
      )}
    </div>
  );
}

export default function Home() {
  const [repoUrl, setRepoUrl] = useState("");
  const [repoId, setRepoId] = useState(null);
  const [ingestState, setIngestState] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [streaming, setStreaming] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [gatewayOk, setGatewayOk] = useState(true);

  const chatRef = useRef(null);
  const questionRef = useRef(null);
  const pollRef = useRef(null);

  // Restore saved repo and verify state
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

      getIngestStatus(savedRepo)
        .then((data) => {
          setIngestState(data);
          setGatewayOk(true);
        })
        .catch(() => {
          // Token or repo will re-validate on action
        });
    }
  }, []);

  // Auto-scroll chat when messages update
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages, streaming]);

  // Ingestion handler
  const handleIngest = useCallback(
    async (urlToIngest) => {
      const targetUrl = (urlToIngest || repoUrl).trim();
      if (!targetUrl || ingesting) return;

      setIngesting(true);
      setIngestState({ status: "PROCESSING", message: "Starting repository ingestion pipeline..." });
      setMessages([]);
      setSessionId(null);

      try {
        const data = await ingestRepo(targetUrl);
        setRepoId(data.repo_id);

        if (data.status === "READY") {
          setIngestState({ status: "READY", ...data });
          setIngesting(false);
          localStorage.setItem("rag_repo_id", data.repo_id);
          localStorage.setItem("rag_repo_url", targetUrl);
          questionRef.current?.focus();
          return;
        }

        if (pollRef.current) clearInterval(pollRef.current);

        pollRef.current = setInterval(async () => {
          try {
            const status = await getIngestStatus(data.repo_id);
            setIngestState(status);

            if (status.status === "READY" || status.status === "FAILED") {
              clearInterval(pollRef.current);
              setIngesting(false);
              if (status.status === "READY") {
                localStorage.setItem("rag_repo_id", data.repo_id);
                localStorage.setItem("rag_repo_url", targetUrl);
                questionRef.current?.focus();
              }
            }
          } catch {
            clearInterval(pollRef.current);
            setIngesting(false);
          }
        }, 2500);
      } catch (err) {
        setIngestState({
          status: "FAILED",
          error_message: err.message || "Could not process repository",
        });
        setIngesting(false);
      }
    },
    [repoUrl, ingesting]
  );

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // Ask question handler
  const handleAsk = useCallback(
    async (questionText) => {
      const q = (questionText || question).trim();
      if (!q || streaming || !repoId) return;

      setQuestion("");
      setStreaming(true);

      setMessages((prev) => [
        ...prev,
        { role: "user", content: q },
        { role: "assistant", content: "", sources: [] },
      ]);

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
                content: `Response error: ${err}`,
              };
            }
            return updated;
          });
          setStreaming(false);
        },
      });
    },
    [question, streaming, repoId, sessionId]
  );

  const handleResetRepo = () => {
    setRepoId(null);
    setRepoUrl("");
    setIngestState(null);
    setMessages([]);
    setSessionId(null);
    localStorage.removeItem("rag_repo_id");
    localStorage.removeItem("rag_repo_url");
    localStorage.removeItem("rag_session_id");
  };

  const isReady = ingestState?.status === "READY";
  const displayRepoName = repoId
    ? repoId.replace(/^github_/, "").replace(/_[a-f0-9]{8,}$/, "").replace(/_/g, "/")
    : null;

  return (
    <div className="app-shell">
      {/* Top Bar */}
      <header className="top-bar animate-enter-1">
        <div className="brand">
          <span className="brand-name">code rag</span>
          <span className="brand-sub">grounded code reasoning</span>
        </div>

        <div className="top-actions">
          <div className="gateway-status">
            <span className={`status-dot ${gatewayOk ? "live" : "error"}`} />
            <span>{gatewayOk ? "Gateway active" : "Gateway offline"}</span>
          </div>

          {repoId && (
            <button type="button" className="text-btn" onClick={handleResetRepo}>
              Switch repository
            </button>
          )}

          <button
            type="button"
            className="text-btn"
            onClick={() => {
              clearToken();
              window.location.reload();
            }}
            title="Reset authentication token and reload"
          >
            Reset token
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main className="main-content">
        {/* Hero Headline (Dominant Focal Point, 2 lines maximum) */}
        {!isReady && (
          <section className="hero-statement animate-enter-2">
            <h1 className="hero-headline">Ground answers in real code.</h1>
            <p className="hero-lead">
              Paste a public GitHub repository. Ask questions and get cited answers with exact file and line references.
            </p>
          </section>
        )}

        {/* Repository Ingestion Card */}
        {!isReady && (
          <section className="ingest-card animate-enter-3">
            <form
              className="ingest-form"
              onSubmit={(e) => {
                e.preventDefault();
                handleIngest();
              }}
            >
              <input
                type="text"
                className="repo-input"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/owner/repository"
                disabled={ingesting}
              />
              <button
                type="submit"
                className="primary-btn"
                disabled={ingesting || !repoUrl.trim()}
              >
                {ingesting ? "Ingesting..." : "Ingest repository"}
              </button>
            </form>

            {/* Quick-load Presets */}
            <div className="presets-row">
              <span>Quick tests:</span>
              {SAMPLE_REPOS.map((sample) => (
                <button
                  key={sample.name}
                  type="button"
                  className="preset-chip"
                  disabled={ingesting}
                  onClick={() => {
                    setRepoUrl(sample.url);
                    handleIngest(sample.url);
                  }}
                >
                  {sample.name} ({sample.note})
                </button>
              ))}
            </div>

            {/* Ingestion Status Feedback */}
            {ingestState && (
              <div className={`status-banner ${ingestState.status?.toLowerCase()}`}>
                <span>
                  {ingestState.status === "PROCESSING" && (
                    <>
                      <strong>Processing repository:</strong> Fetching files, generating AST chunks, and computing vector embeddings...
                    </>
                  )}
                  {ingestState.status === "FAILED" && (
                    <>
                      <strong>Ingestion failed:</strong>{" "}
                      {ingestState.error_message || "Repository inaccessible or missing code files."}
                    </>
                  )}
                </span>
              </div>
            )}
          </section>
        )}

        {/* Real Visual Lineage & Compiler Toolchain (4 Real Pictures) */}
        {!isReady && (
          <section className="architecture-showcase animate-enter-4">
            <div className="showcase-card">
              <span className="showcase-title">Compilation and vector indexing pipeline</span>
              <p className="showcase-desc">
                Source code files are decomposed into semantic syntactic blocks before generating high-dimensional dense embeddings for cosine similarity retrieval.
              </p>
              <div className="showcase-img-wrap">
                <img
                  src="/assets/toolchain.png"
                  alt="Compiler toolchain diagram showing inputs, translation stages, and outputs"
                  className="showcase-img"
                  decoding="async"
                />
              </div>
            </div>

            <div className="showcase-card">
              <span className="showcase-title">Source code lineage and grounding</span>
              <p className="showcase-desc">
                Every synthesis cites verified line boundaries directly from fetched source artifacts rather than hallucinating API signatures.
              </p>
              <div className="showcase-img-wrap">
                <img
                  src="/assets/brainfuck-to-c-translator-in-unix-tmg.png"
                  alt="Archival Unix TMG compiler translation source code showing structured compiler grammar"
                  className="showcase-img"
                  decoding="async"
                />
              </div>
            </div>

            <div className="showcase-card">
              <span className="showcase-title">Abstract syntax tree grammar parsing</span>
              <p className="showcase-desc">
                Grammar trees isolate declaration boundaries, export symbols, and function scopes across diverse programming languages.
              </p>
              <div className="showcase-img-wrap">
                <img
                  src="/assets/grammar-parse-trees.png"
                  alt="Grammar parse trees showing hierarchical lexical breakdown"
                  className="showcase-img"
                  decoding="async"
                />
              </div>
            </div>

            <div className="showcase-card">
              <span className="showcase-title">Verification and validation standards</span>
              <p className="showcase-desc">
                Grounding validation verifies citations against source code signatures before streaming answers to the user.
              </p>
              <div className="showcase-img-wrap">
                <img
                  src="/assets/ajpo-validation-certificate-for-act-ada-1750a.jpg"
                  alt="Archival Ada validation certificate document showing formal verification standard"
                  className="showcase-img"
                  decoding="async"
                />
              </div>
            </div>
          </section>
        )}

        {/* Active Repository Bar */}
        {isReady && (
          <section className="active-repo-bar animate-enter-1">
            <div>
              <span className="active-repo-name">{displayRepoName || repoUrl}</span>
            </div>
            <div className="active-repo-meta">
              {ingestState.chunk_count > 0 && (
                <span>{ingestState.chunk_count} code chunks indexed</span>
              )}
              {ingestState.language_breakdown &&
                Object.entries(ingestState.language_breakdown)
                  .slice(0, 4)
                  .map(([lang, count]) => (
                    <span key={lang} className="lang-tag">
                      {lang}: {count}
                    </span>
                  ))}
              <button type="button" className="text-btn" onClick={handleResetRepo}>
                Change repo
              </button>
            </div>
          </section>
        )}

        {/* Chat Area */}
        {isReady && (
          <section className="chat-section animate-enter-2">
            <div className="messages-list" ref={chatRef}>
              {messages.length === 0 && (
                <div className="empty-chat">
                  <span className="empty-chat-title">Ask anything about {displayRepoName || "the codebase"}</span>
                  <p className="empty-chat-sub">
                    Answers are synthesized from retrieved source files with similarity rankings and line citations.
                  </p>
                  <div className="sample-prompts">
                    {SUGGESTED_QUESTIONS.map((sq, i) => (
                      <button
                        key={i}
                        type="button"
                        className="prompt-btn"
                        onClick={() => handleAsk(sq)}
                      >
                        {sq}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg, i) => (
                <div key={i} className={`message-card ${msg.role}`}>
                  <div className="message-meta">
                    <span>{msg.role === "assistant" ? "Code RAG" : "You"}</span>
                  </div>

                  <div className={streaming && i === messages.length - 1 ? "streaming-cursor" : ""}>
                    <FormattedMessage content={msg.content} />
                  </div>

                  {/* Grounded Source Citations */}
                  {msg.sources?.length > 0 && (
                    <div className="sources-drawer">
                      <span className="sources-header">Grounded code citations ({msg.sources.length})</span>
                      <div className="sources-grid">
                        {msg.sources.map((src, j) => (
                          <CitationItem key={j} source={src} />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Sticky Question Dock */}
            <div className="question-dock">
              <form
                className="question-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  handleAsk();
                }}
              >
                <input
                  ref={questionRef}
                  type="text"
                  className="question-input"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask a question about this repository..."
                  disabled={streaming}
                  autoFocus
                />
                <button
                  type="submit"
                  className="primary-btn"
                  disabled={streaming || !question.trim()}
                >
                  {streaming ? "Thinking..." : "Ask question"}
                </button>
              </form>
            </div>
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="site-footer">
        <div className="footer-credits">
          <p>
            Pictures: <a href="https://commons.wikimedia.org/wiki/File:Toolchain.png">&ldquo;Toolchain&rdquo;</a> by D. Justen (CC BY 4.0); <a href="https://commons.wikimedia.org/w/index.php?curid=87495509">&ldquo;Unix TMG&rdquo;</a> by A. Makukha (CC BY-SA 4.0); <a href="https://commons.wikimedia.org/wiki/File:Grammar_Parse_Trees.png">&ldquo;Grammar Trees&rdquo;</a> by AIProf (CC BY-SA 4.0); <a href="https://commons.wikimedia.org/wiki/File:AJPO_validation_certificate_for_ACT_Ada_1750A_compiler_July_1986.jpg">&ldquo;Ada Validation Certificate&rdquo;</a> by AJPO (Public Domain), via Wikimedia Commons.
          </p>
        </div>
        <div>
          <span>Architecture: Next.js &bull; Spring Boot Gateway &bull; FastAPI &bull; PostgreSQL (pgvector)</span>
        </div>
      </footer>
    </div>
  );
}
