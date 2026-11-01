const el = (id) => document.getElementById(id);

// Colours taken from the rupee notes
const PALETTE = [
  "#6a52cf", "#1f8fa3", "#f0a31e", "#c0266b", "#4aa564",
  "#8a948d", "#8a5a44", "#5aa0e6", "#c7a2e8", "#a3a82a",
];
const STATE_LABELS = { ok: "On track", warning: "Close to limit", over: "Over budget" };

let categoryChart = null;
let dailyChart = null;
let latestRequest = 0; // so a slow answer for an old month can't overwrite a newer one
let picker;

function chartsAvailable() {
  return typeof Chart !== "undefined";
}

/* ---------- which part of the month are we in? ---------- */

function monthInfo(month) {
  const now = currentMonth();
  const [y, m] = month.split("-").map(Number);
  const days = new Date(y, m, 0).getDate();
  if (month < now) return { days, phase: "past" };
  if (month > now) return { days, phase: "future" };
  return { days, phase: "now", day: Number(todayISO().slice(8)) };
}

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

/* ---------- the big number and the budget strip ---------- */

function renderHero(d, report) {
  el("hero-lead").textContent = "Spent in " + formatMonth(d.month);
  el("hero-amount").textContent = formatMoney(d.total_spent);

  const count = d.transaction_count;
  el("meta-count").textContent = `${count} transaction${count === 1 ? "" : "s"}`;
  const change = describeChange(d);
  const changeNode = el("meta-change");
  changeNode.textContent = change.text;
  changeNode.className = change.cls;

  const overall = report.items.find((i) => i.category_id === null);
  const sub = el("hero-sub");
  const strip = el("strip");
  const fill = el("strip-fill");
  const pace = el("strip-pace");
  const note = el("pace-note");

  note.className = "pace-note";
  note.textContent = "";
  pace.hidden = true;

  if (!overall) {
    sub.innerHTML = 'No overall budget for this month. <a href="budgets.html">Set one</a>.';
    strip.hidden = true;
    fill.style.width = "0%";
    return;
  }

  const remaining = Number(overall.remaining);
  const budgetText = formatMoney(overall.budget);
  sub.textContent =
    remaining >= 0
      ? `of your ${budgetText} budget. ${formatMoney(remaining)} left.`
      : `of your ${budgetText} budget. ${formatMoney(-remaining)} over.`;

  const info = monthInfo(d.month);
  const used = Number(overall.percent_used);

  strip.hidden = false;
  strip.style.setProperty("--days", info.days);
  fill.className = "strip-fill " + overall.state;
  fill.style.width = "0%";
  const width = Math.min(Math.max(used, 0), 100);
  // Two frames, so the browser animates the fill growing from empty
  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      fill.style.width = width + "%";
    })
  );

  if (info.phase === "now") {
    const paced = (info.day / info.days) * 100;
    pace.style.left = paced + "%";
    pace.hidden = false;

    let verdict = "at about an even pace";
    let cls = "";
    if (used > paced + 3) {
      verdict = "faster than an even pace";
      cls = "bad";
    } else if (used < paced - 3) {
      verdict = "slower than an even pace";
      cls = "good";
    }
    note.textContent =
      `Day ${info.day} of ${info.days}. ${Math.round(paced)}% of the month has passed ` +
      `and ${Math.round(used)}% of the budget is used, so you are spending ${verdict}.`;
    note.className = "pace-note " + cls;
  } else if (info.phase === "past") {
    note.textContent = "This month is over.";
  } else {
    note.textContent = "This month has not started yet.";
  }
}

/* ---------- category budgets ---------- */

function renderBudgets(report) {
  const items = report.items.filter((i) => i.category_id !== null);
  el("budget-section").hidden = items.length === 0;
  el("budget-list").innerHTML = items
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
            <span class="budget-figures">${escapeHtml(formatMoney(item.spent))} of ${escapeHtml(formatMoney(item.budget))}</span>
          </div>
          <div class="bar"><div class="bar-fill ${item.state}" style="width: ${width}%"></div></div>
          <div class="budget-foot">
            <span class="badge ${item.state}">${STATE_LABELS[item.state] || item.state}</span>
            <span>${escapeHtml(note)} (${used.toFixed(1)}% used)</span>
          </div>
        </div>`;
    })
    .join("");
}

/* ---------- categories: doughnut chart and table ---------- */

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
            borderColor: "#f8faf7",
            borderWidth: 3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "62%",
        plugins: {
          legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
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
      datasets: [
        {
          label: "Spent",
          data: d.daily.map((x) => Number(x.spent)),
          backgroundColor: "#6a52cf",
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { title: { display: true, text: "Day of month" }, grid: { display: false } },
        y: {
          beginAtZero: true,
          grid: { color: "rgba(21, 38, 44, 0.08)" },
          ticks: { callback: (value) => formatMoney(value) },
        },
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
    renderHero(dash, budgets);
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
  if (chartsAvailable()) {
    Chart.defaults.font.family = '"Hanken Grotesk", system-ui, sans-serif';
    Chart.defaults.color = "#506268";
  } else {
    el("chart-warning").hidden = false;
  }
  picker = setupMonthPicker(load);
  picker.start();
}
init();
