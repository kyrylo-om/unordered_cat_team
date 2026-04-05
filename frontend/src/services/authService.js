const API_BASE = "/api";

export async function fetchCSRFToken() {
  const response = await fetch(`${API_BASE}/auth/csrf-token/`, {
    method: "GET",
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch CSRF token");
  }

  return response.json();
}

export async function fetchLogin(username, password, csrfToken) {
  const response = await fetch(`${API_BASE}/auth/login/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
    },
    body: JSON.stringify({ username, password }),
    credentials: "include",
  });

  return response;
}

export async function fetchCheckAuth() {
  const response = await fetch(`${API_BASE}/auth/check/`, {
    method: "GET",
    credentials: "include",
  });

  return response;
}

export async function fetchLogout(csrfToken) {
  const response = await fetch(`${API_BASE}/auth/logout/`, {
    method: "POST",
    headers: {
      "X-CSRFToken": csrfToken,
    },
    credentials: "include",
  });

  return response;
}
