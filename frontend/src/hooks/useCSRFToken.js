import { useState, useEffect } from "react";

export function useCSRFToken() {
  const [csrfToken, setCSRFToken] = useState("");

  useEffect(() => {
    async function fetchToken() {
      try {
        const response = await fetch("/api/auth/csrf-token/", {
          method: "GET",
          credentials: "include",
        });

        if (response.ok) {
          const data = await response.json();
          setCSRFToken(data.csrfToken);
        }
      } catch (err) {
        console.error("Failed to fetch CSRF token:", err);
      }
    }

    fetchToken();
  }, []);

  return csrfToken;
}
