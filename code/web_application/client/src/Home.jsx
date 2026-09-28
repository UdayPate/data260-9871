import { Link } from "react-router-dom";

export default function Home({ user, fixtures }) {
  if (!user) {
    return <div className="page-card"><p>Login required to view fixtures.</p></div>;
  }

  return (
    <div className="page-card">
      <h2>Fixture Board</h2>
      {fixtures.length === 0 ? (
        <p>No fixtures yet.</p>
      ) : (
        <table className="fixture-table">
          <thead>
            <tr><th>ID</th><th>Fixture</th><th>Teams / Players</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {fixtures.map((f) => (
              <tr key={f.id}>
                <td>{f.id}</td>
                <td>{f.fixture_name}</td>
                <td>{f.teams_players}</td>
                <td>
                  <Link to={`/update/${f.id}`}>Edit</Link>
                  <Link to={`/delete/${f.id}`}>Delete</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}