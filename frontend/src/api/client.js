/**
 * Single API access point for the SmartSpeak frontend.
 *
 * Every backend call goes through here so timeouts, error extraction, and
 * JSON handling are consistent. Components call `apiFetch(path)` and get
 * parsed JSON back, or an `APIError` with the server's `detail` message.
 */
const DEFAULT_TIMEOUT_MS = 15000;

export class APIError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'APIError';
    this.status = status;
  }
}

export async function apiFetch(path, { timeoutMs = DEFAULT_TIMEOUT_MS, ...init } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(path, { ...init, signal: controller.signal });
    let body = null;
    try {
      body = await res.json();
    } catch {
      /* non-JSON error bodies (proxy pages, empty responses) */
    }
    if (!res.ok) {
      const detail = body?.detail || `Request failed (HTTP ${res.status})`;
      throw new APIError(detail, res.status);
    }
    return body;
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new APIError('The server took too long to respond. Check that the backend is running.', 0);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
