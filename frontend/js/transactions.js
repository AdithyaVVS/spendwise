const state = {
  page: 1,
  pageSize: 20,
  categories: [],
  rows: new Map(),
  editingId: null,
};

const el = (id) => document.getElementById(id);

/* ---------- categories in the two dropdowns ---------- */

function fillCategorySelects() {
  const formSelect = el("tx-category");
  const filterSelect = el("filter-category");
  const keepForm = formSelect.value;
  const keepFilter = filterSelect.value;

  formSelect.innerHTML = "";
  filterSelect.innerHTML = "";
  formSelect.add(new Option("Choose a category", ""));
  filterSelect.add(new Option("All categories", ""));
  state.categories.forEach((c) => {
    formSelect.add(new Option(c.name, c.id));
    filterSelect.add(new Option(c.name, c.id));
  });
  formSelect.value = keepForm;
  filterSelect.value = keepFilter;

  const none = state.categories.length === 0;
  el("no-categories").hidden = !none;
  el("tx-submit").disabled = none;
}

/* ---------- the table ---------- */

function currentFilters() {
  return {
    date_from: el("filter-from").value,
    date_to: el("filter-to").value,
    category_id: el("filter-category").value,
    search: el("filter-search").value.trim(),
    page: state.page,
    page_size: state.pageSize,
  };
}

function renderRows(items) {
  state.rows = new Map(items.map((t) => [t.id, t]));
  el("tx-body").innerHTML = items
    .map(
      (t) => `
      <tr>
        <td>${escapeHtml(formatDate(t.date))}</td>
        <td>${t.description ? escapeHtml(t.description) : '<span class="muted">-</span>'}</td>
        <td>${escapeHtml(t.category_name)}</td>
        <td class="amount">${escapeHtml(formatMoney(t.amount))}</td>
        <td class="row-actions">
          <button class="small secondary" data-action="edit" data-id="${t.id}">Edit</button>
          <button class="small danger" data-action="delete" data-id="${t.id}">Delete</button>
        </td>
      </tr>`
    )
    .join("");
}

async function load() {
  hideMessage(el("list-message"));
  try {
    const data = await api.listTransactions(currentFilters());

    // We were on a page that no longer exists (for example after deleting the last row on it)
    if (data.items.length === 0 && state.page > 1) {
      state.page = data.total_pages;
      return load();
    }

    renderRows(data.items);
    el("empty").hidden = data.total !== 0;
    el("summary").textContent =
      data.total === 0
        ? ""
        : `${data.total} transaction${data.total === 1 ? "" : "s"} found, totalling ${formatMoney(data.total_amount)}`;

    el("pager").hidden = data.total === 0;
    el("page-info").textContent = `Page ${data.page} of ${data.total_pages}`;
    el("prev").disabled = data.page <= 1;
    el("next").disabled = data.page >= data.total_pages;
  } catch (err) {
    showMessage(el("list-message"), err.message, "error");
  }
}

/* ---------- the add / edit form ---------- */

function resetForm() {
  const keepCategory = el("tx-category").value;
  el("tx-form").reset();
  el("tx-category").value = keepCategory;
  el("tx-date").value = todayISO();
  state.editingId = null;
  el("form-title").textContent = "Add a transaction";
  el("tx-submit").textContent = "Add transaction";
  el("tx-cancel").hidden = true;
}

function startEditing(transaction) {
  state.editingId = transaction.id;
  el("tx-category").value = String(transaction.category_id);
  el("tx-amount").value = transaction.amount;
  el("tx-date").value = transaction.date;
  el("tx-description").value = transaction.description || "";
  el("form-title").textContent = "Edit transaction";
  el("tx-submit").textContent = "Save changes";
  el("tx-cancel").hidden = false;
  hideMessage(el("form-message"));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

el("tx-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const box = el("form-message");
  hideMessage(box);

  const amount = el("tx-amount").value.replace(/,/g, "").trim();
  if (!/^\d+(\.\d{1,2})?$/.test(amount)) {
    showMessage(box, "Enter an amount like 250 or 250.50", "error");
    return;
  }
  if (!el("tx-category").value) {
    showMessage(box, "Choose a category", "error");
    return;
  }

  const body = {
    category_id: Number(el("tx-category").value),
    amount,
    description: el("tx-description").value,
    date: el("tx-date").value,
  };

  const submit = el("tx-submit");
  submit.disabled = true;
  try {
    const wasEditing = state.editingId !== null;
    if (wasEditing) {
      await api.updateTransaction(state.editingId, body);
    } else {
      await api.createTransaction(body);
      state.page = 1;
    }
    resetForm();
    showMessage(box, wasEditing ? "Transaction updated" : "Transaction added", "success");
    await load();
  } catch (err) {
    showMessage(box, err.message, "error");
  } finally {
    submit.disabled = state.categories.length === 0;
  }
});

el("tx-cancel").addEventListener("click", () => {
  resetForm();
  el("tx-category").value = "";
});

/* ---------- edit and delete buttons in the table ---------- */

el("tx-body").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const id = Number(button.dataset.id);
  const transaction = state.rows.get(id);
  if (!transaction) return;

  if (button.dataset.action === "edit") {
    startEditing(transaction);
  } else if (button.dataset.action === "delete") {
    const what = transaction.description || "this transaction";
    if (!(await askConfirm(`Delete "${what}" (${formatMoney(transaction.amount)})?`))) return;
    try {
      await api.deleteTransaction(id);
      if (state.editingId === id) resetForm();
      await load();
    } catch (err) {
      showMessage(el("list-message"), err.message, "error");
    }
  }
});

/* ---------- filters and paging ---------- */

el("filter-form").addEventListener("submit", (event) => {
  event.preventDefault();
  state.page = 1;
  load();
});

el("filter-reset").addEventListener("click", () => {
  el("filter-form").reset();
  state.page = 1;
  load();
});

el("prev").addEventListener("click", () => {
  if (state.page > 1) {
    state.page -= 1;
    load();
  }
});

el("next").addEventListener("click", () => {
  state.page += 1;
  load();
});

el("page-size").addEventListener("change", () => {
  state.pageSize = Number(el("page-size").value);
  state.page = 1;
  load();
});

/* ---------- start ---------- */

async function init() {
  if (!requireLogin()) return;
  renderNav("transactions");
  el("tx-date").value = todayISO();
  try {
    state.categories = await api.listCategories();
    fillCategorySelects();
  } catch (err) {
    showMessage(el("list-message"), err.message, "error");
  }
  await load();
}
init();

