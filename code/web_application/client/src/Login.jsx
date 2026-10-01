import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, errorMessage } from "./api";

export default function Login({ onLoginSuccess }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    try {
      const user = await api.login(email, password);
      onLoginSuccess(user);
      navigate("/");
    } catch (err) {
      // axios rejects on any non-2xx, so the 401 lands here.
      setError(errorMessage(err));
    }
  }

  return (
    <div className="page-card">
      <h2>League Admin Login</h2>
      {error && <p className="error-text" data-testid="login-error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <button className="btn-primary" type="submit">Log In</button>
      </form>
    </div>
  );
}
