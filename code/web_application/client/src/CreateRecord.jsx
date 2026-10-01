import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";

import { createFixture, selectFixtures } from "./fixturesSlice";
import { selectTeams } from "./teamsSlice";

// HW5 Part 1.III.4: create form. On submit it dispatches the createFixture
// thunk; the slice appends the new record, so the Home screen shows it
// without any refetch.
export default function CreateRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const teams = useSelector(selectTeams);
  const fixtures = useSelector(selectFixtures);

  // Suggest the next free FX-9871-##### so the form does not trip the
  // unique constraint on the very first try. The server is still the
  // authority - a clash comes back as a 409 and is shown below.
  const suggestedCode = () => {
    const nums = fixtures
      .map((f) => Number(String(f.fixture_code).split("-").pop()))
      .filter((n) => Number.isFinite(n));
    const next = (nums.length ? Math.max(...nums) : 0) + 1;
    return `FX-9871-${String(next).padStart(5, "0")}`;
  };

  const [form, setForm] = useState({
    fixture_name: "",
    teams_players: "",
    fixture_code: suggestedCode(),
    spots_available: 22,
    home_team_id: "",
  });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    // unwrap() rethrows a rejected thunk, so a 409 or 422 from the API is
    // surfaced on this form instead of silently navigating away.
    try {
      await dispatch(
        createFixture({
          ...form,
          spots_available: Number(form.spots_available),
          home_team_id: Number(form.home_team_id),
        })
      ).unwrap();
      navigate("/");
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-card">
      <h2>Add Fixture</h2>
      {error && <p className="error-text" data-testid="create-error">{error}</p>}
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label htmlFor="fixture_name">Fixture Name</label>
          <input id="fixture_name" value={form.fixture_name} onChange={set("fixture_name")} required />
        </div>
        <div className="field">
          <label htmlFor="teams_players">Teams / Players</label>
          <input id="teams_players" value={form.teams_players} onChange={set("teams_players")} required />
        </div>
        <div className="field">
          <label htmlFor="fixture_code">Fixture Code</label>
          <input id="fixture_code" value={form.fixture_code} onChange={set("fixture_code")} required />
          <small>Must match FX-9871-##### (validated by the API).</small>
        </div>
        <div className="field">
          <label htmlFor="spots_available">Spots Available</label>
          <input
            id="spots_available"
            type="number"
            min="0"
            max="999"
            value={form.spots_available}
            onChange={set("spots_available")}
            required
          />
          <small>Defaults to 22 &mdash; a full two-side roster.</small>
        </div>
        <div className="field">
          <label htmlFor="home_team_id">Home Team</label>
          <select id="home_team_id" value={form.home_team_id} onChange={set("home_team_id")} required>
            <option value="">Select a team...</option>
            {teams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.team_code} {t.team_name}
              </option>
            ))}
          </select>
        </div>
        <button className="btn-primary" type="submit" disabled={saving}>
          {saving ? "Saving..." : "Add Fixture"}
        </button>
      </form>
    </div>
  );
}
