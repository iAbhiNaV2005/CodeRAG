/**
 * API client for the Code RAG gateway.
 *
 * Requests route through Next.js proxy rewrites to Spring Boot gateway (:8080)
 * and downstream FastAPI RAG services.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api";

let _token = null;

/** Helper to extract a human-readable error string from a response. */
async function parseError(res, fallbackText) {
  try {
    const text = await res.text();
    if (!text) return `${fallbackText} (${res.status})`;
    try {
      const data = JSON.parse(text);
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail)) {
        return data.detail.map((d) => d.msg || JSON.stringify(d)).join(", ");
      }
      if (typeof data.message === "string") return data.message;
      if (typeof data.error === "string") return data.error;
    } catch {
      // not JSON
      return text.length > 200 ? text.slice(0, 200) + "..." : text;
    }
    return text;
  } catch {
    return `${fallbackText} (${res.status})`;
  }
}

/** Clear cached token if invalidated or expired. */
export function clearToken() {
  _token = null;
  if (typeof window !== "undefined") {
    localStorage.removeItem("rag_token");
  }
}

/** Get or create a JWT token. Automatically refreshes on demand. */
export async function getToken(forceRefresh = false) {
  if (!forceRefresh && _token) return _token;

  // Check localStorage if not forcing refresh
  if (!forceRefresh && typeof window !== "undefined") {
    const saved = localStorage.getItem("rag_token");
    if (saved) {
      _token = saved;
      return _token;
    }
  }

  const userId =
    (typeof window !== "undefined" && localStorage.getItem("rag_user_id")) ||
    "user_" + Math.random().toString(36).slice(2, 8);

  const res = await fetch(`${API_BASE}/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });

  if (!res.ok) {
    const msg = await parseError(res, "Authentication failed");
    throw new Error(msg);
  }

  const data = await res.json();
  _token = data.token;

  if (typeof window !== "undefined") {
    localStorage.setItem("rag_token", _token);
    localStorage.setItem("rag_user_id", userId);
  }

  return _token;
}

function authHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

/** Internal fetch with automatic token refresh on 401. */
async function fetchWithAuth(url, options = {}) {
  let token = await getToken();
  let headers = { ...authHeaders(token), ...(options.headers || {}) };

  let res = await fetch(url, { ...options, headers });

  // If 401 Unauthorized, token likely expired — refresh once and retry
  if (res.status === 401) {
    clearToken();
    token = await getToken(true);
    headers = { ...authHeaders(token), ...(options.headers || {}) };
    res = await fetch(url, { ...options, headers });
  }

  return res;
}

/** POST /ingest — start repo ingestion */
export async function ingestRepo(repoUrl) {
  const res = await fetchWithAuth(`${API_BASE}/ingest`, {
    method: "POST",
    body: JSON.stringify({ repo_url: repoUrl }),
  });

  if (!res.ok) {
    const msg = await parseError(res, "Ingestion request failed");
    throw new Error(msg);
  }
  return res.json();
}

/** GET /ingest/status/:repoId — poll ingestion status */
export async function getIngestStatus(repoId) {
  const res = await fetchWithAuth(`${API_BASE}/ingest/status/${encodeURIComponent(repoId)}`);

  if (!res.ok) {
    const msg = await parseError(res, "Could not fetch status");
    throw new Error(msg);
  }
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
  let res;
  try {
    res = await fetchWithAuth(`${API_BASE}/chat`, {
      method: "POST",
      body: JSON.stringify({
        repo_id: repoId,
        question,
        session_id: sessionId || null,
      }),
    });
  } catch (err) {
    onError?.(err.message || "Network error contacting gateway");
    return;
  }

  if (!res.ok) {
    const msg = await parseError(res, "Chat request failed");
    onError?.(msg);
    return;
  }

  if (!res.body) {
    onError?.("No response stream received from gateway");
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
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
              onError?.(event.content || "Stream error");
              break;
          }
        } catch {
          // skip unparseable lines
        }
      }
    }
    onDone?.();
  } catch (err) {
    onError?.(err.message || "Stream interrupted");
  }
}
