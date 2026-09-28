import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "./api";

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
      setError("Invalid email or password.");
    }
  }

  return (
    <div className="page-card">
      <h2>League Admin Login</h2>
      {error && <p className="error-text">{error}</p>}
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label>Email</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="field">
          <label>Password</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        <button className="btn-primary" type="submit">Log In</button>
      </form>
    </div>
  );
}