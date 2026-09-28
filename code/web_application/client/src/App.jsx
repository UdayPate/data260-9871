import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import { api } from "./api";
import Login from "./Login";
import Home from "./Home";
import CreateRecord from "./CreateRecord";
import UpdateRecord from "./UpdateRecord";
import DeleteRecord from "./DeleteRecord";

export default function App() {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [fixtures, setFixtures] = useState([]);

  useEffect(() => {
    api
      .me()
      .then((u) => setUser(u))
      .catch(() => setUser(null))
      .finally(() => setAuthChecked(true));
  }, []);

  useEffect(() => {
    if (user) {
      api.listFixtures().then(setFixtures).catch(() => setFixtures([]));
    } else {
      setFixtures([]);
    }
  }, [user]);

  async function handleLogout() {
    await api.logout();
    setUser(null);
  }

  async function addFixture(data) {
    const created = await api.createFixture(data);
    setFixtures((prev) => [...prev, created]);
  }

  async function editFixture(id, data) {
    const updated = await api.updateFixture(id, data);
    setFixtures((prev) => prev.map((f) => (f.id === Number(id) ? updated : f)));
  }

  async function removeFixture(id) {
    await api.deleteFixture(id);
    setFixtures((prev) => prev.filter((f) => f.id !== Number(id)));
  }

  if (!authChecked) {
    return <p>Loading...</p>;
  }

  return (
    <BrowserRouter>
      <div className="app-shell">
        <nav className="app-nav">
          <Link to="/">Home</Link>
          {user && <Link to="/create">Add Record</Link>}
          <span className="spacer"></span>
          {user ? (
            <>
              <span className="user-tag">Logged in as {user.name}</span>
              <button onClick={handleLogout}>Log out</button>
            </>
          ) : (
            <Link to="/login">Login</Link>
          )}
        </nav>

        <Routes>
          <Route path="/" element={<Home user={user} fixtures={fixtures} />} />
          <Route path="/login" element={<Login onLoginSuccess={setUser} />} />
          <Route
            path="/create"
            element={user ? <CreateRecord onCreate={addFixture} /> : <Navigate to="/login" />}
          />
          <Route
            path="/update/:id"
            element={user ? <UpdateRecord fixtures={fixtures} onUpdate={editFixture} /> : <Navigate to="/login" />}
          />
          <Route
            path="/delete/:id"
            element={user ? <DeleteRecord fixtures={fixtures} onDelete={removeFixture} /> : <Navigate to="/login" />}
          />
        </Routes>
      </div>
    </BrowserRouter>
  );
}