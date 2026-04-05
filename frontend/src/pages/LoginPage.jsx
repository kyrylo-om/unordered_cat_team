import { LoginForm } from "../components/LoginForm";
import "../styles/LoginPage.css";

export function LoginPage() {
  return (
    <div className="login-page">
      <div className="login-container">
        <LoginForm />
      </div>
    </div>
  );
}
