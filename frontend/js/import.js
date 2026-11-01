const el = (id) => document.getElementById(id);
const MAX_BYTES = 1000000;

function statCard(value, label, cls) {
  return `<div class="stat"><div class="value ${cls}">${value}</div><div class="label">${label}</div></div>`;
}

function renderResult(r) {
  let html = '<div class="stat-grid">';
  html += statCard(r.imported, "Imported", r.imported > 0 ? "good" : "");
  html += statCard(r.duplicates_skipped, "Skipped as duplicates", "");
  html += statCard(r.rejected, "Rejected", r.rejected > 0 ? "bad" : "");
  html += statCard(r.categories_created.length, "New categories", "");
  html += "</div>";

  html += `<p class="muted">${r.total_rows} data row${r.total_rows === 1 ? "" : "s"} found in the file. Row numbers below match the line in your file (the header is row 1).</p>`;

  if (r.categories_created.length > 0) {
    html += `<p>New categories: ${r.categories_created.map(escapeHtml).join(", ")}</p>`;
  }

  if (r.errors.length > 0) {
    html += "<h2>Rejected rows</h2>";
    html += '<div class="table-wrap"><table><thead><tr><th>Row</th><th>Reason</th></tr></thead><tbody>';
    html += r.errors
      .map((e) => `<tr><td>${e.row}</td><td>${escapeHtml(e.reason)}</td></tr>`)
      .join("");
    html += "</tbody></table></div>";
    if (r.rejected > r.errors.length) {
      html += `<p class="muted">Showing the first ${r.errors.length} of ${r.rejected} rejected rows.</p>`;
    }
  }

  if (r.duplicate_rows.length > 0) {
    html += `<p>Rows skipped as duplicates: ${r.duplicate_rows.join(", ")}`;
    if (r.duplicates_skipped > r.duplicate_rows.length) {
      html += ` and ${r.duplicates_skipped - r.duplicate_rows.length} more`;
    }
    html += "</p>";
  }

  if (r.imported > 0) {
    html += '<p><a href="transactions.html">View your transactions</a> or <a href="dashboard.html">open the dashboard</a>.</p>';
  }

  el("result").innerHTML = html;
  el("result-card").hidden = false;
}

el("import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const box = el("import-message");
  hideMessage(box);
  el("result-card").hidden = true;

  const file = el("csv-file").files[0];
  if (!file) {
    showMessage(box, "Choose a CSV file first", "error");
    return;
  }
  if (file.size > MAX_BYTES) {
    showMessage(box, "That file is larger than 1 MB", "error");
    return;
  }

  const submit = el("import-submit");
  submit.disabled = true;
  submit.textContent = "Importing...";
  try {
    const result = await api.importCsv(file);
    renderResult(result);
    el("csv-file").value = "";
  } catch (err) {
    showMessage(box, err.message, "error");
  } finally {
    submit.disabled = false;
    submit.textContent = "Upload and import";
  }
});

function init() {
  if (!requireLogin()) return;
  renderNav("import");
}
init();
