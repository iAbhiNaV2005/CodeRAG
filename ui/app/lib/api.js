/**
 * API client for the Code RAG gateway.
 *
 * All requests go through the Spring Boot gateway on :8080.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

let _token = null;

/** Get or create a JWT token. */
async function getToken() {
  if (_token) return _token;

  // Check localStorage first
  if (typeof window !== "undefined") {
    const saved = localStorage.getItem("rag_token");
    if (saved) {
      _token = saved;
      return _token;
    }
  }

  const userId = "user_" + Math.random().toString(36).slice(2, 8);
  const res = await fetch(`${API_BASE}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });

  const data = await res.json();
  _token = data.token;

  if (typeof window !== "undefined") {
    localStorage.setItem("rag_token", _token);
    localStorage.setItem("rag_user_id", userId);
  }

  return _token;
}

function authHeaders() {
  return {
    Authorization: `Bearer ${_token}`,
    "Content-Type": "application/json",
  };
}

/** POST /ingest — start repo ingestion */
export async function ingestRepo(repoUrl) {
  await getToken();
  const res = await fetch(`${API_BASE}/ingest`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ repo_url: repoUrl }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/** GET /ingest/status/:repoId — poll ingestion status */
export async function getIngestStatus(repoId) {
  await getToken();
  const res = await fetch(`${API_BASE}/ingest/status/${repoId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/**
 * POST /chat — SSE streaming chat.
 *
 * Calls onToken(text) for each streamed chunk,
 * onSources(sources) when citations arrive,
 * onDone() when stream completes.
 */
export async function streamChat(
  repoId,
  question,
  sessionId,
  { onToken, onSources, onSession, onDone, onError }
) {
  await getToken();

  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({
      repo_id: repoId,
      question,
      session_id: sessionId || null,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    onError?.(text);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data:")) continue;
      const jsonStr = line.slice(5).trim();
      if (!jsonStr) continue;

      try {
        const event = JSON.parse(jsonStr);

        switch (event.type) {
          case "session":
            onSession?.(event.session_id);
            break;
          case "token":
            onToken?.(event.content);
            break;
          case "sources":
            onSources?.(event.sources);
            break;
          case "done":
            onDone?.();
            break;
          case "error":
            onError?.(event.content);
            break;
        }
      } catch {
        // skip malformed events
      }
    }
  }
}
