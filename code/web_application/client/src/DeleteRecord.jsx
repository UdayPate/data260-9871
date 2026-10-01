import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useDispatch, useSelector } from "react-redux";

import { deleteFixture, selectFixtures } from "./fixturesSlice";

// HW5 Part 1.III.5: the /delete/:id confirmation route kept from HW4, now
// dispatching the Redux thunk instead of calling a prop. The delete button
// the assignment asks for sits next to each row on the Home screen.
export default function DeleteRecord() {
  const { id } = useParams();
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const fixtures = useSelector(selectFixtures);
  const fixture = fixtures.find((f) => f.id === Number(id));
  const [error, setError] = useState(null);

  async function handleDelete() {
    setError(null);
    try {
      await dispatch(deleteFixture(Number(id))).unwrap();
      navigate("/");
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="page-card">
      <h2>Delete Fixture</h2>
      {error && <p className="error-text">{error}</p>}
      {fixture ? (
        <p>
          Are you sure you want to delete &quot;{fixture.fixture_name}&quot; (
          {fixture.fixture_code})?
        </p>
      ) : (
        <p>Fixture #{id} is not in Redux state.</p>
      )}
      <button className="btn-primary" onClick={handleDelete}>
        Delete
      </button>
    </div>
  );
}
