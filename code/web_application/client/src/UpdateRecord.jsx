import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";

export default function UpdateRecord({ fixtures, onUpdate }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [fixtureName, setFixtureName] = useState("");
  const [teamsPlayers, setTeamsPlayers] = useState("");

  useEffect(() => {
    const existing = fixtures.find((f) => f.id === Number(id));
    if (existing) {
      setFixtureName(existing.fixture_name);
      setTeamsPlayers(existing.teams_players);
    }
  }, [id, fixtures]);

  async function handleSubmit(e) {
    e.preventDefault();
    await onUpdate(id, { fixture_name: fixtureName, teams_players: teamsPlayers });
    navigate("/");
  }

  return (
    <div className="page-card">
      <h2>Update Fixture #{id}</h2>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label>Fixture Name</label>
          <input value={fixtureName} onChange={(e) => setFixtureName(e.target.value)} required />
        </div>
        <div className="field">
          <label>Teams / Players</label>
          <input value={teamsPlayers} onChange={(e) => setTeamsPlayers(e.target.value)} required />
        </div>
        <button className="btn-primary" type="submit">Save Changes</button>
      </form>
    </div>
  );
}