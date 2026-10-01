import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";

import { updateFixture, selectFixtures } from "./fixturesSlice";
import { selectTeams } from "./teamsSlice";

// HW5 Part 1.III.4: update form, selecting the record by ID.
// Reachable two ways: /update (type an ID) and /update/:id (the Edit link on
// the Home screen). Either way the current values are read out of Redux
// state, never re-fetched.
//
// The form is a separate component given key={fixture.id}. Changing the id
// therefore remounts it, and useState picks up the new record's values on
// first render. That replaces the usual "useEffect + setForm" pattern,
// which React's own lint rule rejects because setting state inside an
// effect causes a second, cascading render.
export default function UpdateRecord() {
  const { id: routeId } = useParams();
  const fixtures = useSelector(selectFixtures);
  const [selectedId, setSelectedId] = useState(routeId || "");

  const existing = fixtures.find((f) => f.id === Number(selectedId));

  return (
    <div className="page-card">
      <h2>Update Fixture{existing ? ` #${existing.id}` : ""}</h2>

      <div className="field">
        <label htmlFor="select-id">Fixture ID</label>
        <input
          id="select-id"
          type="number"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
          placeholder="Enter the id of the fixture to edit"
        />
        {selectedId && !existing && (
          <small className="error-text" data-testid="update-no-such-id">
            No fixture with id {selectedId} in Redux state.
          </small>
        )}
      </div>

      {existing && <FixtureForm key={existing.id} fixture={existing} />}
    </div>
  );
}

function FixtureForm({ fixture }) {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const teams = useSelector(selectTeams);

  const [form, setForm] = useState({
    fixture_name: fixture.fixture_name,
    teams_players: fixture.teams_players,
    fixture_code: fixture.fixture_code,
    spots_available: fixture.spots_available,
    home_team_id: fixture.home_team_id,
  });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    // unwrap() rethrows a rejected thunk, so a 404/409/422 from the API is
    // shown on this form instead of silently navigating away.
    try {
      await dispatch(
        updateFixture({
          id: fixture.id,
          changes: {
            ...form,
            spots_available: Number(form.spots_available),
            home_team_id: Number(form.home_team_id),
          },
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
    <>
      {error && <p className="error-text" data-testid="update-error">{error}</p>}
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
          {saving ? "Saving..." : "Save Changes"}
        </button>
      </form>
    </>
  );
}
