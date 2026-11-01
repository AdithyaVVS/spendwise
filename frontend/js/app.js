const TOKEN_KEY = "spendwise_token";
const EMAIL_KEY = "spendwise_email";

/* ---------- login state (kept in the browser) ---------- */

function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch (_) { return null; }
}

function getEmail() {
  try { return localStorage.getItem(EMAIL_KEY) || ""; } catch (_) { return ""; }
}

function saveLogin(token, email) {
  try {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(EMAIL_KEY, email);
  } catch (_) {}
}

function clearLogin() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(EMAIL_KEY);
  } catch (_) {}
}

function requireLogin() {
  if (getToken()) return true;
  window.location.replace("login.html");
  return false;
}

function logout() {
  clearLogin();
  window.location.href = "login.html";
}

/* ---------- talking to the server ---------- */

function errorMessage(body) {
  if (!body) return "Something went wrong";
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => {
        const field = Array.isArray(e.loc) ? e.loc[e.loc.length - 1] : "";
        const msg = String(e.msg || "Invalid value").replace(/^Value error, /, "");
        return field && field !== "body" ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  return "Something went wrong";
}

async function request(path, options = {}) {
  const { skipAuthRedirect, ...fetchOptions } = options;
  const headers = { ...(fetchOptions.headers || {}) };
  const token = getToken();
  if (token) headers["Authorization"] = "Bearer " + token;

  let res;
  try {
    res = await fetch(path, { ...fetchOptions, headers });
  } catch (_) {
    throw new Error("Cannot reach the server. Check that it is running.");
  }

  // Token missing, expired or invalid: go back to the login page
  if (res.status === 401 && !skipAuthRedirect) {
    clearLogin();
    window.location.replace("login.html");
    throw new Error("Please log in again.");
  }

  if (!res.ok) {
    let body = null;
    try { body = await res.json(); } catch (_) {}
    throw new Error(errorMessage(body));
  }
  return res.status === 204 ? null : res.json();
}

function jsonOptions(method, body) {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

function queryString(params) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== "" && value !== null && value !== undefined) q.append(key, value);
  });
  const text = q.toString();
  return text ? "?" + text : "";
}

const api = {
  register: (email, password) =>
    request("/api/auth/register", jsonOptions("POST", { email, password })),
  login: (email, password) =>
    request("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: email, password }).toString(),
      skipAuthRedirect: true,
    }),
  listCategories: () => request("/api/categories"),
  createCategory: (name) => request("/api/categories", jsonOptions("POST", { name })),
  renameCategory: (id, name) => request(`/api/categories/${id}`, jsonOptions("PUT", { name })),
  deleteCategory: (id) => request(`/api/categories/${id}`, { method: "DELETE" }),
  listTransactions: (params) => request("/api/transactions" + queryString(params)),
  createTransaction: (body) => request("/api/transactions", jsonOptions("POST", body)),
  updateTransaction: (id, body) =>
    request(`/api/transactions/${id}`, jsonOptions("PUT", body)),
  deleteTransaction: (id) => request(`/api/transactions/${id}`, { method: "DELETE" }),
};

/* ---------- helpers for showing things ---------- */

// Escapes text before it goes into HTML, so user-typed text can never run as code (XSS)
function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const rupee = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });

// For display only: the server keeps exact decimal amounts
function formatMoney(value) {
  return rupee.format(Number(value));
}

function formatDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function todayISO() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function showMessage(box, text, kind) {
  box.textContent = text;
  box.className = "message " + kind;
  box.hidden = false;
}

function hideMessage(box) {
  box.hidden = true;
}

/* ---------- navigation bar ---------- */

const NAV_LINKS = [
  ["transactions", "transactions.html", "Transactions"],
  ["categories", "categories.html", "Categories"],
];

function renderNav(active) {
  const nav = document.getElementById("nav");
  nav.innerHTML = "";

  const brand = document.createElement("span");
  brand.className = "brand";
  brand.textContent = "SpendWise";
  nav.appendChild(brand);

  NAV_LINKS.forEach(([key, href, label]) => {
    const link = document.createElement("a");
    link.href = href;
    link.textContent = label;
    if (key === active) link.className = "active";
    nav.appendChild(link);
  });

  const spacer = document.createElement("span");
  spacer.className = "spacer";
  nav.appendChild(spacer);

  const who = document.createElement("span");
  who.className = "who";
  who.textContent = getEmail();
  nav.appendChild(who);

  const button = document.createElement("button");
  button.className = "small secondary";
  button.textContent = "Log out";
  button.addEventListener("click", logout);
  nav.appendChild(button);
}


/* ---------- in-page dialogs (the built-in browsers block prompt/confirm) ---------- */

function openDialog({ message, withInput, initial, maxLength, confirmLabel, danger, cancelValue }) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "overlay";

    const box = document.createElement("div");
    box.className = "dialog";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");

    const text = document.createElement("p");
    text.textContent = message;
    box.appendChild(text);

    let field = null;
    if (withInput) {
      field = document.createElement("input");
      field.type = "text";
      field.value = initial || "";
      field.maxLength = maxLength || 50;
      box.appendChild(field);
    }

    const row = document.createElement("div");
    row.className = "actions-row";
    const okButton = document.createElement("button");
    okButton.textContent = confirmLabel;
    if (danger) okButton.className = "danger";
    const cancelButton = document.createElement("button");
    cancelButton.textContent = "Cancel";
    cancelButton.className = "secondary";
    row.appendChild(okButton);
    row.appendChild(cancelButton);
    box.appendChild(row);

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    function close(result) {
      document.removeEventListener("keydown", onKey);
      overlay.remove();
      resolve(result);
    }
    function accept() {
      close(withInput ? field.value : true);
    }
    function onKey(event) {
      if (event.key === "Escape") close(cancelValue);
    }

    okButton.addEventListener("click", accept);
    cancelButton.addEventListener("click", () => close(cancelValue));
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) close(cancelValue);
    });
    if (field) {
      field.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          accept();
        }
      });
    }
    document.addEventListener("keydown", onKey);

    if (field) {
      field.focus();
      field.select();
    } else {
      cancelButton.focus(); // the safe choice is highlighted for delete confirmations
    }
  });
}

// Returns true if the user clicks the confirm button, false otherwise
function askConfirm(message) {
  return openDialog({
    message,
    confirmLabel: "Delete",
    danger: true,
    cancelValue: false,
  });
}

// Returns the typed text, or null if the user cancels
function askText(message, initial, maxLength) {
  return openDialog({
    message,
    withInput: true,
    initial,
    maxLength,
    confirmLabel: "Save",
    cancelValue: null,
  });
}


/* ---------- added in step 11: more API calls, menu and month picker ---------- */

Object.assign(api, {
  dashboard: (month) => request("/api/dashboard" + queryString({ month })),
  budgetStatus: (month) => request("/api/budgets/status" + queryString({ month })),
  setBudget: (body) => request("/api/budgets", jsonOptions("PUT", body)),
  deleteBudget: (id) => request(`/api/budgets/${id}`, { method: "DELETE" }),
  importCsv: (file) => {
    const form = new FormData();
    form.append("file", file);
    // No Content-Type header here: the browser sets it, including the file boundary
    return request("/api/transactions/import", { method: "POST", body: form });
  },
});

NAV_LINKS.length = 0;
NAV_LINKS.push(
  ["dashboard", "dashboard.html", "Dashboard"],
  ["transactions", "transactions.html", "Transactions"],
  ["budgets", "budgets.html", "Budgets"],
  ["import", "import.html", "Import"],
  ["categories", "categories.html", "Categories"]
);

function currentMonth() {
  return todayISO().slice(0, 7);
}

function shiftMonth(month, delta) {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function formatMonth(month) {
  const [y, m] = month.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

function isValidMonth(text) {
  return /^20\d{2}-(0[1-9]|1[0-2])$/.test(text);
}

// Month picker used by the dashboard and budgets pages. Calls onChange(month) whenever it changes.
function setupMonthPicker(onChange) {
  const input = document.getElementById("month-input");
  const label = document.getElementById("month-label");
  let month = currentMonth();

  function apply(newMonth) {
    month = newMonth;
    input.value = month;
    label.textContent = formatMonth(month);
    onChange(month);
  }

  document.getElementById("month-prev").addEventListener("click", () => {
    const earlier = shiftMonth(month, -1);
    if (isValidMonth(earlier)) apply(earlier);
  });
  document.getElementById("month-next").addEventListener("click", () => {
    const later = shiftMonth(month, 1);
    if (isValidMonth(later)) apply(later);
  });
  input.addEventListener("change", () => {
    if (isValidMonth(input.value)) apply(input.value);
    else input.value = month;
  });

  return {
    get month() { return month; },
    start() { apply(month); },
  };
}
