import { useState } from "react";
import { Link } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";

import {
  deleteFixture,
  selectFixtures,
  selectFixturesError,
  selectFixturesStatus,
  selectLastAction,
  selectLastTouchedId,
} from "./fixturesSlice";
import { selectTeams } from "./teamsSlice";

const PAGE_SIZE = 25;

// HW5 Part 1.III.3 (Home screen) + 1.III.5 (delete button per row).
// Everything rendered here comes from Redux state via useSelector, so the
// table updates itself the moment a create / update / delete reducer runs.
export default function Home({ user }) {
  const dispatch = useDispatch();
  const fixtures = useSelector(selectFixtures);
  const status = useSelector(selectFixturesStatus);
  const error = useSelector(selectFixturesError);
  const lastAction = useSelector(selectLastAction);
  const lastTouchedId = useSelector(selectLastTouchedId);
  const teams = useSelector(selectTeams);

  // Which page is on screen is a UI concern, not shared state, so it stays
  // in local component state rather than in the store.
  //
  // The initial value is NOT always 1. The assignment requires the updated
  // result to be shown on the Home screen, but a newly created fixture gets
  // the highest id and so lands on the LAST page - landing on page 1 would
  // show the confirmation banner and no visible row. Navigating here from
  // the create/update screen remounts this component, so the opening page
  // can simply be derived in the useState initialiser; no effect, and
  // therefore no cascading re-render.
  const [page, setPage] = useState(() => {
    if (lastTouchedId == null) return 1;
    const i = fixtures.findIndex((f) => f.id === lastTouchedId);
    return i === -1 ? 1 : Math.floor(i / PAGE_SIZE) + 1;
  });

  if (!user) {
    return (
      <div className="page-card">
        <p>Login required to view fixtures.</p>
      </div>
    );
  }

  const teamLabel = (id) => {
    const t = teams.find((x) => x.id === id);
    return t ? `${t.team_code} ${t.team_name}` : `#${id}`;
  };

  const totalPages = Math.max(1, Math.ceil(fixtures.length / PAGE_SIZE));
  const current = Math.min(page, totalPages);
  const visible = fixtures.slice((current - 1) * PAGE_SIZE, current * PAGE_SIZE);

  function handleDelete(fixture) {
    if (window.confirm(`Delete fixture #${fixture.id} (${fixture.fixture_code})?`)) {
      dispatch(deleteFixture(fixture.id));
    }
  }

  return (
    <div className="page-card">
      <h2>Fixture Board</h2>

      {status === "loading" && <p>Loading fixtures from the API...</p>}
      {error && <p className="error-text">{error}</p>}
      {lastAction && <p className="ok-text">{lastAction}</p>}

      {status === "succeeded" && (
        <p>
          <strong>{fixtures.length}</strong> fixtures in Redux state &mdash;
          showing {visible.length === 0 ? 0 : (current - 1) * PAGE_SIZE + 1}
          &ndash;{(current - 1) * PAGE_SIZE + visible.length}
        </p>
      )}

      {fixtures.length === 0 && status !== "loading" ? (
        <p>No fixtures yet.</p>
      ) : (
        <>
          <table className="fixture-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Code</th>
                <th>Fixture</th>
                <th>Teams / Players</th>
                <th>Spots</th>
                <th>Home team</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((f) => (
                <tr
                  key={f.id}
                  className={f.id === lastTouchedId ? "row-touched" : undefined}
                >
                  <td>{f.id}</td>
                  <td>{f.fixture_code}</td>
                  <td>{f.fixture_name}</td>
                  <td>{f.teams_players}</td>
                  <td>{f.spots_available}</td>
                  <td>{teamLabel(f.home_team_id)}</td>
                  <td>
                    <Link to={`/update/${f.id}`}>Edit</Link>
                    <button
                      className="btn-danger"
                      data-testid={`delete-${f.id}`}
                      onClick={() => handleDelete(f)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="pager">
            <button onClick={() => setPage(current - 1)} disabled={current <= 1}>
              Prev
            </button>
            <span>
              Page {current} of {totalPages}
            </span>
            <button
              onClick={() => setPage(current + 1)}
              disabled={current >= totalPages}
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
