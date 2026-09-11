// ---------------------------------------------------------------
// HW1 carryover: client-side validation + closure-based counter.
// The form now submits for real (to FastAPI), so we only
// preventDefault() when validation FAILS - on success we let the
// browser submit natively, which is what triggers the server's
// redirect back to "/".
// ---------------------------------------------------------------

const fixtureForm = document.getElementById("fixtureForm");

function createSubmissionCounter() {
  let count = 0;
  return function () {
    count = count + 1;
    return count;
  };
}
const trackSubmission = createSubmissionCounter();

const validateForm = (description, agreeTerms) => {
  if (description.length <= 25) {
    alert("Match details must be more than 25 characters.");
    return false;
  }
  if (!agreeTerms) {
    alert("You must agree to the terms and conditions.");
    return false;
  }
  return true;
};

fixtureForm.addEventListener("submit", function (event) {
  const description = document.getElementById("description").value;
  const agreeTerms = document.getElementById("agreeTerms").checked;

  if (!validateForm(description, agreeTerms)) {
    event.preventDefault(); // block submission only on failure
    return;
  }

  // Demonstrate JSON.stringify / destructuring / spread, purely for
  // logging - the actual data still gets submitted to the server
  // normally right after this (we do NOT preventDefault here).
  const formData = {
    fixtureName: document.getElementById("fixtureName").value,
    teamsPlayers: document.getElementById("teamsPlayers").value,
    submitterEmail: document.getElementById("submitterEmail").value,
    description: description,
    category: document.getElementById("category").value,
    agreeTerms: agreeTerms,
  };
  const jsonString = JSON.stringify(formData);
  console.log("Form data as JSON string:", jsonString);

  const parsedObject = JSON.parse(jsonString);
  const { fixtureName, submitterEmail } = parsedObject;
  console.log("Fixture Name:", fixtureName);
  console.log("Submitter Email:", submitterEmail);

  const updatedObject = { ...parsedObject, submissionDate: new Date().toISOString() };
  console.log("Updated object with submission date:", updatedObject);

  console.log("Submission count:", trackSubmission());
  // No event.preventDefault() here - the form submits to the server.
});


// ---------------------------------------------------------------
// HW2 Part 2: fetch the fixture list from the JSON API, drive the
// loading / empty / error states, and support search.
// ---------------------------------------------------------------

const loadingState = document.getElementById("loadingState");
const emptyState = document.getElementById("emptyState");
const errorState = document.getElementById("errorState");
const fixtureTable = document.getElementById("fixtureTable");
const fixtureTableBody = document.getElementById("fixtureTableBody");
const searchInput = document.getElementById("searchInput");
const searchButton = document.getElementById("searchButton");
const clearSearchButton = document.getElementById("clearSearchButton");

function setState(state) {
  // state is one of: "loading", "empty", "error", "loaded"
  [loadingState, emptyState, errorState].forEach((el) => el.classList.remove("active"));
  fixtureTable.style.display = "none";

  if (state === "loading") loadingState.classList.add("active");
  if (state === "empty") emptyState.classList.add("active");
  if (state === "error") errorState.classList.add("active");
  if (state === "loaded") fixtureTable.style.display = "";
}

function renderFixtures(fixtures) {
  fixtureTableBody.innerHTML = "";
  fixtures.forEach((f) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td data-label="ID">${f.id}</td>
      <td data-label="Fixture">${f.fixture_name}</td>
      <td data-label="Teams / Players">${f.teams_players}</td>
      <td data-label="Sport">${f.category}</td>
      <td data-label="Submitted">${f.submitted}</td>
    `;
    fixtureTableBody.appendChild(row);
  });
}

async function loadFixtures(query) {
  setState("loading");
  try {
    const url = query
      ? `/api/fixtures?q=${encodeURIComponent(query)}`
      : "/api/fixtures";
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Request failed with status ${response.status}`);
    }
    const fixtures = await response.json();

    if (fixtures.length === 0) {
      setState("empty");
    } else {
      renderFixtures(fixtures);
      setState("loaded");
    }
  } catch (err) {
    console.error("Failed to load fixtures:", err);
    setState("error");
  }
}

searchButton.addEventListener("click", () => {
  loadFixtures(searchInput.value.trim());
});

clearSearchButton.addEventListener("click", () => {
  searchInput.value = "";
  loadFixtures();
});

searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    loadFixtures(searchInput.value.trim());
  }
});

// Load the list as soon as the page loads (this is also what runs
// right after a create/update/delete redirect brings us back here).
document.addEventListener("DOMContentLoaded", () => loadFixtures());