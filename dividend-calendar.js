const calendarAccountFilter = document.querySelector("#calendar-account-filter");
const calendarYearFilter = document.querySelector("#calendar-year-filter");
const calendarHideZero = document.querySelector("#calendar-hide-zero");
const calendarNotice = document.querySelector("#calendar-notice");
const calendarTableBody = document.querySelector("#calendar-table-body");
const calendarRowTemplate = document.querySelector("#calendar-row-template");
const calendarTotalRow = document.querySelector("#calendar-total-row");
const calendarSelectedYear = document.querySelector("#calendar-selected-year");
const calendarStockCount = document.querySelector("#calendar-stock-count");
const calendarYearTotal = document.querySelector("#calendar-year-total");
const calendarPeakMonth = document.querySelector("#calendar-peak-month");

const state = {
  accounts: [],
  dividends: [],
  availableYears: [],
};

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "系統發生錯誤");
  }
  return payload;
}

function formatNumber(value, fractionDigits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  return new Intl.NumberFormat("zh-TW", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

function showNotice(message, type = "info") {
  calendarNotice.textContent = message;
  calendarNotice.hidden = false;
  calendarNotice.className = `page-notice is-${type}`;
}

function hideNotice() {
  calendarNotice.hidden = true;
  calendarNotice.className = "page-notice";
  calendarNotice.textContent = "";
}

async function fetchAccounts() {
  const payload = await requestJson("/api/accounts");
  state.accounts = payload.items || [];
}

async function fetchDividends() {
  const account = calendarAccountFilter.value || "ALL";
  const payload = await requestJson(`/api/dividends?account=${encodeURIComponent(account)}`);
  state.dividends = payload.items || [];
}

function getPaymentYear(item) {
  return item.payment_date ? item.payment_date.slice(0, 4) : "";
}

function getPaymentMonth(item) {
  return item.payment_date ? Number(item.payment_date.slice(5, 7)) : 0;
}

function renderAccountOptions() {
  const currentValue = calendarAccountFilter.value;
  calendarAccountFilter.innerHTML = '<option value="ALL">全部帳戶</option>';
  for (const account of state.accounts) {
    const option = document.createElement("option");
    option.value = account.name;
    option.textContent = account.name;
    calendarAccountFilter.append(option);
  }
  calendarAccountFilter.value = state.accounts.some((account) => account.name === currentValue)
    ? currentValue
    : "ALL";
}

function syncAvailableYears() {
  state.availableYears = [...new Set(state.dividends.map(getPaymentYear).filter(Boolean))]
    .sort((left, right) => right.localeCompare(left));
}

function renderYearOptions() {
  const currentValue = calendarYearFilter.value;
  calendarYearFilter.innerHTML = "";

  if (state.availableYears.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "目前沒有年份資料";
    calendarYearFilter.append(option);
    return;
  }

  for (const year of state.availableYears) {
    const option = document.createElement("option");
    option.value = year;
    option.textContent = `${year}年`;
    calendarYearFilter.append(option);
  }

  const currentYear = String(new Date().getFullYear());
  if (state.availableYears.includes(currentValue)) {
    calendarYearFilter.value = currentValue;
  } else if (state.availableYears.includes(currentYear)) {
    calendarYearFilter.value = currentYear;
  } else {
    calendarYearFilter.value = state.availableYears[0];
  }
}

function buildCalendarItems() {
  const selectedYear = calendarYearFilter.value;
  const hideZero = calendarHideZero.checked;
  const itemsMap = new Map();

  for (const item of state.dividends) {
    if (getPaymentYear(item) !== selectedYear) {
      continue;
    }

    const key = `${item.account}__${item.symbol}`;
    const month = getPaymentMonth(item);
    const current = itemsMap.get(key) || {
      account: item.account,
      symbol: item.symbol,
      name: item.name,
      monthly: Array(12).fill(0),
      total: 0,
    };

    current.name = current.name || item.name;
    if (month >= 1 && month <= 12) {
      current.monthly[month - 1] += Number(item.net_amount || 0);
    }
    current.total += Number(item.net_amount || 0);
    itemsMap.set(key, current);
  }

  let items = [...itemsMap.values()].map((item) => ({
    ...item,
    monthly: item.monthly.map((value) => Number(value.toFixed(2))),
    total: Number(item.total.toFixed(2)),
  }));

  if (hideZero) {
    items = items.filter((item) => item.total > 0);
  }

  items.sort((left, right) => {
    if (right.total !== left.total) {
      return right.total - left.total;
    }
    return left.symbol.localeCompare(right.symbol, "zh-Hant", { numeric: true });
  });

  return items;
}

function renderSummary(items, monthlyTotals) {
  const selectedYear = calendarYearFilter.value || "-";
  calendarSelectedYear.textContent = selectedYear;
  calendarStockCount.textContent = formatNumber(items.length);

  const yearTotal = monthlyTotals.reduce((sum, value) => sum + value, 0);
  calendarYearTotal.textContent = formatNumber(yearTotal);

  let peakMonthIndex = -1;
  let peakMonthValue = -1;
  monthlyTotals.forEach((value, index) => {
    if (value > peakMonthValue) {
      peakMonthValue = value;
      peakMonthIndex = index;
    }
  });

  calendarPeakMonth.textContent = peakMonthValue > 0
    ? `${peakMonthIndex + 1}月 / ${formatNumber(peakMonthValue)}`
    : "-";
}

function renderTotalRow(monthlyTotals) {
  for (let month = 1; month <= 12; month += 1) {
    const cell = calendarTotalRow.querySelector(`[data-month="${month}"]`);
    cell.textContent = formatNumber(monthlyTotals[month - 1]);
  }
  calendarTotalRow.querySelector('[data-total="year"]').textContent = formatNumber(
    monthlyTotals.reduce((sum, value) => sum + value, 0)
  );
}

function renderCalendar() {
  const selectedYear = calendarYearFilter.value;
  const items = buildCalendarItems();
  const monthlyTotals = Array(12).fill(0);
  calendarTableBody.innerHTML = "";

  if (!selectedYear) {
    const row = document.createElement("tr");
    row.className = "empty-state";
    row.innerHTML = '<td colspan="16">目前沒有可顯示的年份資料</td>';
    calendarTableBody.append(row);
    renderTotalRow(monthlyTotals);
    renderSummary([], monthlyTotals);
    return;
  }

  if (items.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-state";
    row.innerHTML = '<td colspan="16">目前沒有符合條件的股利月曆資料</td>';
    calendarTableBody.append(row);
    renderTotalRow(monthlyTotals);
    renderSummary([], monthlyTotals);
    return;
  }

  for (const item of items) {
    const fragment = calendarRowTemplate.content.cloneNode(true);
    const row = fragment.querySelector("tr");

    row.querySelector('[data-key="account"]').textContent = item.account;
    row.querySelector('[data-key="symbol"]').textContent = item.symbol;
    row.querySelector('[data-key="name"]').textContent = item.name;

    item.monthly.forEach((value, index) => {
      monthlyTotals[index] += value;
      const cell = row.querySelector(`[data-month="${index + 1}"]`);
      cell.textContent = value > 0 ? formatNumber(value) : "-";
      if (value > 0) {
        cell.classList.add("calendar-value-cell");
      }
    });

    row.querySelector('[data-key="total"]').textContent = formatNumber(item.total);
    calendarTableBody.append(fragment);
  }

  renderTotalRow(monthlyTotals.map((value) => Number(value.toFixed(2))));
  renderSummary(items, monthlyTotals);
}

async function refreshAll() {
  await Promise.all([fetchAccounts(), fetchDividends()]);
  renderAccountOptions();
  syncAvailableYears();
  renderYearOptions();
  renderCalendar();
}

calendarAccountFilter.addEventListener("change", async () => {
  await fetchDividends();
  syncAvailableYears();
  renderYearOptions();
  renderCalendar();
});

calendarYearFilter.addEventListener("change", renderCalendar);
calendarHideZero.addEventListener("change", renderCalendar);

refreshAll().catch((error) => {
  showNotice(`無法載入股利月曆頁：${error.message}`, "error");
});

hideNotice();
