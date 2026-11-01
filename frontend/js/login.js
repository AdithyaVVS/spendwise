let mode = "login";

const form = document.getElementById("auth-form");
const title = document.getElementById("auth-title");
const submitButton = document.getElementById("auth-submit");
const confirmRow = document.getElementById("confirm-row");
const confirmInput = document.getElementById("confirm");
const passwordInput = document.getElementById("password");
const toggleText = document.getElementById("toggle-text");
const toggleLink = document.getElementById("toggle-link");
const messageBox = document.getElementById("auth-message");

function setMode(newMode) {
  mode = newMode;
  const registering = mode === "register";
  title.textContent = registering ? "Create your account" : "Log in to SpendWise";
  submitButton.textContent = registering ? "Create account" : "Log in";
  confirmRow.hidden = !registering;
  confirmInput.required = registering;
  passwordInput.autocomplete = registering ? "new-password" : "current-password";
  toggleText.textContent = registering ? "Already have an account?" : "New here?";
  toggleLink.textContent = registering ? "Log in" : "Create an account";
  hideMessage(messageBox);
}

toggleLink.addEventListener("click", (event) => {
  event.preventDefault();
  setMode(mode === "login" ? "register" : "login");
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideMessage(messageBox);

  const email = document.getElementById("email").value.trim().toLowerCase();
  const password = passwordInput.value;

  if (mode === "register" && password !== confirmInput.value) {
    showMessage(messageBox, "Passwords do not match", "error");
    return;
  }

  submitButton.disabled = true;
  try {
    if (mode === "register") await api.register(email, password);
    const token = await api.login(email, password);
    saveLogin(token.access_token, email);
    window.location.replace("dashboard.html");
  } catch (err) {
    showMessage(messageBox, err.message, "error");
  } finally {
    submitButton.disabled = false;
  }
});

// Already logged in? Skip this page.
if (getToken()) window.location.replace("dashboard.html");

