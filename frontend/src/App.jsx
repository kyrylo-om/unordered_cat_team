import { useAuth } from "./context/AuthContext";
import { LoginPage } from "./pages/LoginPage";
import { MainPage } from "./pages/MainPage";
import "./App.css";

function AppContent() {
  const { isLoading, isAuthenticated } = useAuth();

  if (isLoading) {
    return (
      <div className="app-loading">
        <p>Loading...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return <MainPage />;
}

export default AppContent;
