const el = (id) => document.getElementById(id);

const STATE_LABELS = { ok: "On track", warning: "Close to limit", over: "Over budget" };
const state = { categories: [], items: new Map() };
let latestRequest = 0;
let picker;

function fillCategorySelect() {
  const select = el("budget-category");
  const keep = select.value;
  select.innerHTML = "";
  select.add(new Option("Overall (all spending)", "overall"));
  state.categories.forEach((c) => select.add(new Option(c.name, String(c.id))));
  select.value = keep || "overall";
  if (!select.value) select.value = "overall";
}

function renderItems(report) {
  state.items = new Map(report.items.map((i) => [i.budget_id, i]));
  el("empty").hidden = report.items.length !== 0;
  el("budget-table").hidden = report.items.length === 0;
  el("budget-body").innerHTML = report.items
    .map((i) => {
      const remaining = Number(i.remaining);
      return `
        <tr>
          <td>${escapeHtml(i.category_name)}</td>
          <td class="amount">${escapeHtml(formatMoney(i.budget))}</td>
          <td class="amount">${escapeHtml(formatMoney(i.spent))}</td>
          <td class="amount ${remaining < 0 ? "bad" : ""}">${escapeHtml(formatMoney(i.remaining))}</td>
          <td class="amount">${Number(i.percent_used).toFixed(1)}%</td>
          <td><span class="badge ${i.state}">${STATE_LABELS[i.state] || i.state}</span></td>
          <td class="row-actions">
            <button class="small secondary" data-action="edit" data-id="${i.budget_id}">Edit</button>
            <button class="small danger" data-action="delete" data-id="${i.budget_id}">Delete</button>
          </td>
        </tr>`;
    })
    .join("");
}

async function loadBudgets(month) {
  const mine = ++latestRequest;
  el("form-title").textContent = "Set a budget for " + formatMonth(month);
  el("list-title").textContent = "Budgets for " + formatMonth(month);
  hideMessage(el("list-message"));
  try {
    const report = await api.budgetStatus(month);
    if (mine !== latestRequest) return;
    renderItems(report);
  } catch (err) {
    if (mine !== latestRequest) return;
    showMessage(el("list-message"), err.message, "error");
  }
}

el("budget-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const box = el("form-message");
  hideMessage(box);

  const amount = el("budget-amount").value.replace(/,/g, "").trim();
  if (!/^\d+(\.\d{1,2})?$/.test(amount) || Number(amount) <= 0) {
    showMessage(box, "Enter an amount like 5000 or 5000.50", "error");
    return;
  }

  const body = { month: picker.month, amount };
  const category = el("budget-category").value;
  if (category !== "overall") body.category_id = Number(category);

  const submit = el("budget-submit");
  submit.disabled = true;
  try {
    await api.setBudget(body);
    el("budget-amount").value = "";
    showMessage(box, "Budget saved for " + formatMonth(picker.month), "success");
    await loadBudgets(picker.month);
  } catch (err) {
    showMessage(box, err.message, "error");
  } finally {
    submit.disabled = false;
  }
});

el("budget-body").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button) return;
  const item = state.items.get(Number(button.dataset.id));
  if (!item) return;

  if (button.dataset.action === "edit") {
    el("budget-category").value = item.category_id === null ? "overall" : String(item.category_id);
    el("budget-amount").value = item.budget;
    hideMessage(el("form-message"));
    window.scrollTo({ top: 0, behavior: "smooth" });
    el("budget-amount").focus();
  } else if (button.dataset.action === "delete") {
    if (!(await askConfirm(`Delete the budget for "${item.category_name}"?`))) return;
    try {
      await api.deleteBudget(item.budget_id);
      await loadBudgets(picker.month);
    } catch (err) {
      showMessage(el("list-message"), err.message, "error");
    }
  }
});

async function init() {
  if (!requireLogin()) return;
  renderNav("budgets");
  try {
    state.categories = await api.listCategories();
  } catch (err) {
    showMessage(el("list-message"), err.message, "error");
  }
  fillCategorySelect();
  picker = setupMonthPicker(loadBudgets);
  picker.start();
}
init();
