import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import { useDispatch } from "react-redux";

import { api, tokenStore } from "./api";
import { fetchFixtures } from "./fixturesSlice";
import { fetchTeams } from "./teamsSlice";
import Login from "./Login";
import Home from "./Home";
import CreateRecord from "./CreateRecord";
import UpdateRecord from "./UpdateRecord";
import DeleteRecord from "./DeleteRecord";

// HW5 Part 1.III: the fixture list no longer lives in this component's
// useState and is no longer passed down as props. App only decides who is
// logged in; every screen reads fixtures straight out of the Redux store.
export default function App() {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const dispatch = useDispatch();

  // HW7: only ask the server who we are if a token was kept from earlier in this tab, and
  // forget the user the moment any request is answered with 401 (expired / invalid token).
  useEffect(() => {
    if (tokenStore.get()) {
      api
        .me()
        .then((u) => setUser(u))
        .catch(() => setUser(null))
        .finally(() => setAuthChecked(true));
    } else {
      setAuthChecked(true);
    }
    const onExpired = () => setUser(null);
    window.addEventListener("auth:expired", onExpired);
    return () => window.removeEventListener("auth:expired", onExpired);
  }, []);

  // The server enforces the roles; the UI only hides what the role could not use anyway.
  const canWrite = user && (user.role === "writer" || user.role === "moderator");

  // One fetch on login; after that the reducers keep the store in step with
  // every create / update / delete, so nothing re-fetches the list.
  useEffect(() => {
    if (user) {
      dispatch(fetchFixtures());
      dispatch(fetchTeams());
    }
  }, [user, dispatch]);

  async function handleLogout() {
    await api.logout();
    setUser(null);
  }

  if (!authChecked) {
    return <p>Loading...</p>;
  }

  return (
    <BrowserRouter>
      <div className="app-shell">
        <nav className="app-nav">
          <Link to="/">Home</Link>
          {canWrite && <Link to="/create">Add Record</Link>}
          {canWrite && <Link to="/update">Update Record</Link>}
          <span className="spacer"></span>
          {user ? (
            <>
              <span className="user-tag">Logged in as {user.username} ({user.role})</span>
              <button onClick={handleLogout}>Log out</button>
            </>
          ) : (
            <Link to="/login">Login</Link>
          )}
        </nav>

        <Routes>
          <Route path="/" element={<Home user={user} />} />
          <Route path="/login" element={<Login onLoginSuccess={setUser} />} />
          <Route
            path="/create"
            element={canWrite ? <CreateRecord /> : <Navigate to={user ? "/" : "/login"} />}
          />
          <Route
            path="/update"
            element={canWrite ? <UpdateRecord /> : <Navigate to={user ? "/" : "/login"} />}
          />
          <Route
            path="/update/:id"
            element={canWrite ? <UpdateRecord /> : <Navigate to={user ? "/" : "/login"} />}
          />
          <Route
            path="/delete/:id"
            element={user && user.role === "moderator" ? <DeleteRecord /> : <Navigate to={user ? "/" : "/login"} />}
          />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
