// Get a reference to the form
const fixtureForm = document.getElementById("fixtureForm");

//closure for tracking submission count
function createSubmissionCounter() {
  let count = 0;
  return function() {
    count = count + 1;
    return count;
  };
}

const trackSubmission = createSubmissionCounter();

// Requirement II.1: arrow function to validate description length + checkbox
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

// Handle form submission
fixtureForm.addEventListener("submit", function(event) {
  event.preventDefault(); // stop the page from reloading

  const description = document.getElementById("description").value;
  const agreeTerms = document.getElementById("agreeTerms").checked;

  if (!validateForm(description, agreeTerms)) {
    return; // stop here if validation failed
  }

  // Requirement II.2: convert form data to JSON string, log it
  const formData = {
    fixtureName: document.getElementById("fixtureName").value,
    teamsPlayers: document.getElementById("teamsPlayers").value,
    submitterEmail: document.getElementById("submitterEmail").value,
    description: description,
    category: document.getElementById("category").value,
    agreeTerms: agreeTerms
  };

  const jsonString = JSON.stringify(formData);
  console.log("Form data as JSON string:", jsonString);

  // Requirement II.3: parse it back, then destructure
  const parsedObject = JSON.parse(jsonString);
  const { fixtureName, submitterEmail } = parsedObject;
  console.log("Fixture Name:", fixtureName);
  console.log("Submitter Email:", submitterEmail);

  // Requirement II.4: spread operator to add submissionDate
  const updatedObject = { ...parsedObject, submissionDate: new Date().toISOString() };
  console.log("Updated object with submission date:", updatedObject);

  // Requirement II.5: log the submission count using the closure
  const submissionCount = trackSubmission();
  console.log("Submission count:", submissionCount);
});