import { useState, useEffect } from "react";
import { AuthContext } from "./authContextObject";

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  // Check if session exists on component mount
  useEffect(() => {
    checkAuth();
  }, []);

  async function checkAuth() {
    try {
      const response = await fetch("/api/auth/check/", {
        method: "GET",
        credentials: "include",
      });

      if (response.ok) {
        const data = await response.json();
        if (data?.authenticated === false || !data?.user) {
          setUser(null);
          setIsAuthenticated(false);
        } else {
          setUser(data.user);
          setIsAuthenticated(true);
          setError("");
        }
      } else {
        setUser(null);
        setIsAuthenticated(false);
      }
    } catch {
      setUser(null);
      setIsAuthenticated(false);
      setError("Failed to check authentication status");
    } finally {
      setIsLoading(false);
    }
  }

  async function login(username, password, csrfToken) {
    setIsLoading(true);
    setError("");

    try {
      const response = await fetch("/api/auth/login/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
        },
        body: JSON.stringify({ username, password }),
        credentials: "include",
      });

      if (response.ok) {
        const data = await response.json();
        setUser(data.user);
        setIsAuthenticated(true);
        setError("");
        return true;
      } else if (response.status === 429) {
        setError("Too many login attempts. Try again later.");
        return false;
      } else {
        const data = await response.json();
        setError(data.error || "Login failed");
        return false;
      }
    } catch {
      setError("An error occurred during login. Please try again.");
      return false;
    } finally {
      setIsLoading(false);
    }
  }

  async function logout(csrfToken) {
    setIsLoading(true);
    try {
      await fetch("/api/auth/logout/", {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken,
        },
        credentials: "include",
      });

      setUser(null);
      setIsAuthenticated(false);
      setError("");
    } catch {
      setError("Error during logout");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isLoading,
        error,
        setError,
        login,
        logout,
        checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
