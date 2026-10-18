const SESSION_KEY = "vglpos.session";
let refreshInFlight = null;

export function getSession() {
  const raw = sessionStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    sessionStorage.removeItem(SESSION_KEY);
    return null;
  }
}

export function saveSession(session) {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession() {
  sessionStorage.removeItem(SESSION_KEY);
}

export function requireSession() {
  const session = getSession();
  if (!session) {
    const next = encodeURIComponent(`${location.pathname}${location.search}`);
    location.replace(`/login?next=${next}`);
    return null;
  }
  return session;
}

async function rotateOnce(session) {
  const response = await fetch("/api/v1/auth/refresh", {
    method: "POST",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${session.refresh_token}`,
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: "{}",
  });
  if (!response.ok) return null;
  const refreshed = await response.json();
  if (getSession()?.refresh_token !== session.refresh_token) return null;
  saveSession(refreshed);
  return refreshed;
}

function rotateTokens(session) {
  if (!refreshInFlight) refreshInFlight = rotateOnce(session).finally(() => { refreshInFlight = null; });
  return refreshInFlight;
}

export class ApiError extends Error {
  constructor(message, status, problem = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }
}

async function problemFrom(response) {
  const type = response.headers.get("content-type") || "";
  if (!type.includes("json")) return null;
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function apiFetch(path, options = {}, allowRefresh = true) {
  let session = getSession();
  if (!session) {
    document.dispatchEvent(new CustomEvent("vgl:session-expired"));
    throw new ApiError("Authentication is required.", 401);
  }

  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  headers.set("Accept", "application/json");
  headers.set("Authorization", `Bearer ${session.access_token}`);
  if (["POST", "PUT", "PATCH"].includes(method) && !headers.has("Idempotency-Key")) {
    headers.set("Idempotency-Key", crypto.randomUUID());
  }
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");

  let response = await fetch(path, { ...options, method, headers });
  if (response.status === 401 && allowRefresh) {
    const latest = getSession();
    session = latest && latest.access_token !== session.access_token ? latest : await rotateTokens(session);
    if (session) {
      headers.set("Authorization", `Bearer ${session.access_token}`);
      response = await fetch(path, { ...options, method, headers });
    }
  }
  if (!response.ok) {
    const problem = await problemFrom(response);
    if (response.status === 401) {
      clearSession();
      document.dispatchEvent(new CustomEvent("vgl:session-expired"));
    }
    throw new ApiError(
      problem?.detail || problem?.title || `Request failed with status ${response.status}.`,
      response.status,
      problem,
    );
  }
  return response;
}

export async function apiJson(path, options = {}) {
  const response = await apiFetch(path, options);
  if (response.status === 204) return null;
  return response.json();
}

export async function logout() {
  try {
    await apiJson("/api/v1/auth/logout", { method: "POST", body: "{}" });
  } finally {
    clearSession();
    location.replace("/login");
  }
}
