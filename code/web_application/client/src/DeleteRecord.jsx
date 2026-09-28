import { useParams, useNavigate } from "react-router-dom";

export default function DeleteRecord({ fixtures, onDelete }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const fixture = fixtures.find((f) => f.id === Number(id));

  async function handleDelete() {
    await onDelete(id);
    navigate("/");
  }

  return (
    <div className="page-card">
      <h2>Delete Fixture</h2>
      {fixture ? (
        <p>Are you sure you want to delete "{fixture.fixture_name}"?</p>
      ) : (
        <p>Fixture #{id}</p>
      )}
      <button className="btn-primary" onClick={handleDelete}>Delete</button>
    </div>
  );
}