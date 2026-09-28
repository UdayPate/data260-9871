import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function CreateRecord({ onCreate }) {
  const [fixtureName, setFixtureName] = useState("");
  const [teamsPlayers, setTeamsPlayers] = useState("");
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    await onCreate({ fixture_name: fixtureName, teams_players: teamsPlayers });
    navigate("/");
  }

  return (
    <div className="page-card">
      <h2>Add Fixture</h2>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label>Fixture Name</label>
          <input value={fixtureName} onChange={(e) => setFixtureName(e.target.value)} required />
        </div>
        <div className="field">
          <label>Teams / Players</label>
          <input value={teamsPlayers} onChange={(e) => setTeamsPlayers(e.target.value)} required />
        </div>
        <button className="btn-primary" type="submit">Add Fixture</button>
      </form>
    </div>
  );
}