import { useAuth } from "../context/useAuth";
import { useCSRFToken } from "../hooks/useCSRFToken";

export function LogoutButton() {
  const { logout, isLoading } = useAuth();
  const csrfToken = useCSRFToken();

  async function handleLogout() {
    await logout(csrfToken);
  }

  return (
    <button
      onClick={handleLogout}
      disabled={isLoading}
      className="logout-button"
    >
      {isLoading ? "Logging out..." : "Logout"}
    </button>
  );
}
