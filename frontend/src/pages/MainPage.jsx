import { LogoutButton } from "../components/LogoutButton";
import { MainContent } from "../components/MainContent";
import { StoreView } from "./StoreView";
import { useAuth } from "../context/useAuth";
import "../styles/MainPage.css";

function resolveRole(user) {
  const value =
    user?.role ||
    user?.user_type ||
    user?.userType ||
    user?.accountType ||
    user?.type ||
    "";
  const role = String(value).toLowerCase();

  if (role.includes("store") || role.includes("worker")) {
    return "store";
  }

  return "manager";
}

export function MainPage() {
  const { user } = useAuth();
  const role = resolveRole(user);

  if (role === "store") {
    return (
      <div className="main-page store-layout">
        <header className="app-header">
          <h1>Transportation Management System</h1>
          <LogoutButton />
        </header>

        <main className="store-main-area">
          <StoreView />
        </main>
      </div>
    );
  }

  return (
    <div className="main-page">
      <header className="app-header">
        <h1>Transportation Management System</h1>
        <LogoutButton />
      </header>

      <div className="app-layout">
        <aside className="left-sidebar">
          <div className="sidebar-placeholder">
            <h3>Data Panel</h3>
            <p>General data and statistics will be displayed here</p>
          </div>
        </aside>

        <main className="main-area">
          <MainContent />
        </main>

        <aside className="right-sidebar">
          <div className="sidebar-placeholder">
            <h3>Details Panel</h3>
            <p>Selected item properties will be displayed here</p>
          </div>
        </aside>
      </div>
    </div>
  );
}
