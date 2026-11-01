const el = (id) => document.getElementById(id);

const PALETTE = [
  "#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed",
  "#0891b2", "#db2777", "#65a30d", "#ea580c", "#475569",
];
const STATE_LABELS = { ok: "On track", warning: "Close to limit", over: "Over budget" };

let categoryChart = null;
let dailyChart = null;
let latestRequest = 0; // so a slow answer for an old month can't overwrite a newer one
let picker;

function chartsAvailable() {
  return typeof Chart !== "undefined";
}

/* ---------- the four number cards ---------- */

function describeChange(d) {
  const total = Number(d.total_spent);
  const previous = Number(d.previous_total);
  const diff = Number(d.change_amount);
  const monthName = formatMonth(d.previous_month);

  if (total === 0 && previous === 0) return { text: "No spending in either month", cls: "" };
  if (diff === 0) return { text: "Same as " + monthName, cls: "" };

  const percent =
    d.change_percent === null ? "" : ` (${Math.abs(Number(d.change_percent)).toFixed(1)}%)`;
  const direction = diff > 0 ? "more" : "less";
  return {
    text: `${formatMoney(Math.abs(diff))}${percent} ${direction} than ${monthName}`,
    cls: diff > 0 ? "bad" : "good", // spending more is the bad direction
  };
}

function renderStats(d) {
  el("stat-total").textContent = formatMoney(d.total_spent);
  el("stat-count").textContent = d.transaction_count;
  el("stat-previous").textContent = formatMoney(d.previous_total);
  el("stat-previous-label").textContent = "Spent in " + formatMonth(d.previous_month);
  const change = describeChange(d);
  const node = el("stat-change");
  node.textContent = change.text;
  node.className = "change " + change.cls;
}

/* ---------- budget progress bars ---------- */

function renderBudgets(report) {
  const box = el("budget-list");
  if (report.items.length === 0) {
    box.innerHTML = '<p class="muted">No budgets set for this month. <a href="budgets.html">Set one</a>.</p>';
    return;
  }
  box.innerHTML = report.items
    .map((item) => {
      const used = Number(item.percent_used);
      const width = Math.min(Math.max(used, 0), 100);
      const remaining = Number(item.remaining);
      const note =
        remaining >= 0 ? `${formatMoney(remaining)} left` : `${formatMoney(-remaining)} over`;
      return `
        <div class="budget-row">
          <div class="budget-head">
            <strong>${escapeHtml(item.category_name)}</strong>
            <span class="badge ${item.state}">${STATE_LABELS[item.state] || item.state}</span>
          </div>
          <div class="bar"><div class="bar-fill ${item.state}" style="width: ${width}%"></div></div>
          <div class="muted">${escapeHtml(formatMoney(item.spent))} of ${escapeHtml(formatMoney(item.budget))}
            (${used.toFixed(1)}%) - ${escapeHtml(note)}</div>
        </div>`;
    })
    .join("");
}

/* ---------- categories: pie chart and table ---------- */

function renderCategories(d) {
  const withSpending = d.by_category.filter((c) => Number(c.spent) > 0);

  if (categoryChart) {
    categoryChart.destroy();
    categoryChart = null;
  }
  el("category-empty").hidden = withSpending.length > 0;
  el("category-box").hidden = withSpending.length === 0 || !chartsAvailable();
  if (withSpending.length > 0 && chartsAvailable()) {
    categoryChart = new Chart(el("category-chart"), {
      type: "doughnut",
      data: {
        labels: withSpending.map((c) => c.category_name),
        datasets: [
          {
            data: withSpending.map((c) => Number(c.spent)),
            backgroundColor: withSpending.map((_, i) => PALETTE[i % PALETTE.length]),
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom" },
          tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${formatMoney(ctx.parsed)}` } },
        },
      },
    });
  }

  el("table-empty").hidden = d.by_category.length > 0;
  el("category-table").hidden = d.by_category.length === 0;
  el("category-body").innerHTML = d.by_category
    .map((c) => {
      let change = '<span class="muted">New</span>';
      if (c.change_percent !== null) {
        const p = Number(c.change_percent);
        const cls = p > 0 ? "bad" : p < 0 ? "good" : "";
        change = `<span class="${cls}">${p > 0 ? "+" : ""}${p.toFixed(1)}%</span>`;
      }
      return `
        <tr>
          <td>${escapeHtml(c.category_name)}</td>
          <td class="amount">${escapeHtml(formatMoney(c.spent))}</td>
          <td class="amount">${Number(c.percent_of_total).toFixed(1)}%</td>
          <td class="amount">${escapeHtml(formatMoney(c.previous_spent))}</td>
          <td class="amount">${change}</td>
        </tr>`;
    })
    .join("");
}

/* ---------- daily bar chart ---------- */

function renderDaily(d) {
  if (dailyChart) {
    dailyChart.destroy();
    dailyChart = null;
  }
  const hasSpending = Number(d.total_spent) > 0;
  el("daily-empty").hidden = hasSpending;
  el("daily-box").hidden = !hasSpending || !chartsAvailable();
  if (!hasSpending || !chartsAvailable()) return;

  dailyChart = new Chart(el("daily-chart"), {
    type: "bar",
    data: {
      labels: d.daily.map((x) => String(Number(x.date.slice(8)))),
      datasets: [{ label: "Spent", data: d.daily.map((x) => Number(x.spent)), backgroundColor: "#2563eb" }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { title: { display: true, text: "Day of month" } },
        y: { beginAtZero: true, ticks: { callback: (value) => formatMoney(value) } },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: (items) => formatDate(d.daily[items[0].dataIndex].date),
            label: (ctx) => formatMoney(ctx.parsed.y),
          },
        },
      },
    },
  });
}

/* ---------- loading a month ---------- */

async function load(month) {
  const mine = ++latestRequest;
  hideMessage(el("dash-message"));
  try {
    const [dash, budgets] = await Promise.all([api.dashboard(month), api.budgetStatus(month)]);
    if (mine !== latestRequest) return;
    el("dash-content").hidden = false;
    renderStats(dash);
    renderBudgets(budgets);
    renderCategories(dash);
    renderDaily(dash);
  } catch (err) {
    if (mine !== latestRequest) return;
    showMessage(el("dash-message"), err.message, "error");
  }
}

function init() {
  if (!requireLogin()) return;
  renderNav("dashboard");
  if (!chartsAvailable()) el("chart-warning").hidden = false;
  picker = setupMonthPicker(load);
  picker.start();
}
init();
