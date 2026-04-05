import { LogoutButton } from "../components/LogoutButton";
import { MainContent } from "../components/MainContent";
import "../styles/MainPage.css";

export function MainPage() {
  return (
    <div className="main-page">
      <header className="app-header">
        <h1>Transportation Management System</h1>
        <LogoutButton />
      </header>

      <div className="app-layout">
        {/* Left sidebar placeholder */}
        <aside className="left-sidebar">
          <div className="sidebar-placeholder">
            <h3>Data Panel</h3>
            <p>General data and statistics will be displayed here</p>
          </div>
        </aside>

        {/* Main content area - where graph will go */}
        <main className="main-area">
          <MainContent />
        </main>

        {/* Right sidebar placeholder */}
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
