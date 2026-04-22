const statsAccountFilter = document.querySelector("#stats-account-filter");
const statsYearOptions = document.querySelector("#stats-year-options");
const statsYearSelectAll = document.querySelector("#stats-year-select-all");
const yieldThresholdInput = document.querySelector("#yield-threshold-input");
const statsNotice = document.querySelector("#stats-notice");
const statsTableBody = document.querySelector("#stats-table-body");
const statsRowTemplate = document.querySelector("#stats-row-template");
const statsSortHeaders = document.querySelectorAll("th[data-sort]");
const selectedYearsText = document.querySelector("#stats-selected-years");
const stockCountText = document.querySelector("#stats-stock-count");
const netTotalText = document.querySelector("#stats-net-total");
const aboveThresholdText = document.querySelector("#stats-above-threshold");

const YIELD_THRESHOLD_STORAGE_KEY = "stock-dividend-stats-threshold-v1";
const STATS_SORT_STORAGE_KEY = "stock-dividend-stats-sort-v1";
const DEFAULT_STATS_SORT = { key: "yield_total", direction: "desc" };

const state = {
  accounts: [],
  dividends: [],
  availableYears: [],
  selectedYears: new Set(),
  statsSort: loadStatsSortState(),
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

function formatPercent(value) {
  return `${formatNumber(value, 2)}%`;
}

function getCurrentYear() {
  return String(new Date().getFullYear());
}

function showNotice(message, type = "info") {
  statsNotice.textContent = message;
  statsNotice.hidden = false;
  statsNotice.className = `page-notice is-${type}`;
}

function hideNotice() {
  statsNotice.hidden = true;
  statsNotice.className = "page-notice";
  statsNotice.textContent = "";
}

function loadStatsSortState() {
  try {
    const raw = localStorage.getItem(STATS_SORT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed?.key && ["asc", "desc"].includes(parsed?.direction)) {
      return parsed;
    }
  } catch (error) {
    console.error("讀取股利統計排序設定失敗", error);
  }
  return { ...DEFAULT_STATS_SORT };
}

function saveStatsSortState() {
  localStorage.setItem(STATS_SORT_STORAGE_KEY, JSON.stringify(state.statsSort));
}

function compareSortValues(leftValue, rightValue, direction) {
  const multiplier = direction === "asc" ? 1 : -1;
  const leftMissing = leftValue === null || leftValue === undefined || leftValue === "";
  const rightMissing = rightValue === null || rightValue === undefined || rightValue === "";

  if (leftMissing && rightMissing) {
    return 0;
  }
  if (leftMissing) {
    return 1;
  }
  if (rightMissing) {
    return -1;
  }

  if (typeof leftValue === "number" && typeof rightValue === "number") {
    if (leftValue === rightValue) {
      return 0;
    }
    return leftValue > rightValue ? multiplier : -multiplier;
  }

  return String(leftValue).localeCompare(String(rightValue), "zh-Hant", {
    numeric: true,
    sensitivity: "base",
  }) * multiplier;
}

async function fetchAccounts() {
  const payload = await requestJson("/api/accounts");
  state.accounts = payload.items || [];
}

async function fetchDividends() {
  const account = statsAccountFilter.value || "ALL";
  const payload = await requestJson(`/api/dividends?account=${encodeURIComponent(account)}`);
  state.dividends = payload.items || [];
}

function renderAccountOptions() {
  const currentValue = statsAccountFilter.value;
  statsAccountFilter.innerHTML = '<option value="ALL">全部帳戶</option>';
  for (const account of state.accounts) {
    const option = document.createElement("option");
    option.value = account.name;
    option.textContent = account.name;
    statsAccountFilter.append(option);
  }
  statsAccountFilter.value = state.accounts.some((account) => account.name === currentValue)
    ? currentValue
    : "ALL";
}

function syncAvailableYears() {
  state.availableYears = [...new Set(state.dividends.map((item) => String(item.year)).filter(Boolean))]
    .sort((left, right) => right.localeCompare(left));

  const available = new Set(state.availableYears);
  state.selectedYears = new Set(
    [...state.selectedYears].filter((year) => available.has(year))
  );

  if (state.selectedYears.size === 0 && state.availableYears.length > 0) {
    const currentYear = getCurrentYear();
    if (available.has(currentYear)) {
      state.selectedYears.add(currentYear);
    } else {
      state.selectedYears.add(state.availableYears[0]);
    }
  }
}

function renderYearOptions() {
  statsYearOptions.innerHTML = "";

  if (state.availableYears.length === 0) {
    const empty = document.createElement("div");
    empty.className = "year-option-empty";
    empty.textContent = "目前沒有可選年份";
    statsYearOptions.append(empty);
    statsYearSelectAll.checked = false;
    return;
  }

  for (const year of state.availableYears) {
    const label = document.createElement("label");
    label.className = "year-option-chip";

    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = year;
    input.checked = state.selectedYears.has(year);
    input.addEventListener("change", () => {
      if (input.checked) {
        state.selectedYears.add(year);
      } else {
        state.selectedYears.delete(year);
      }
      syncSelectAllState();
      renderStats();
    });

    const text = document.createElement("span");
    text.textContent = `${year}年`;

    label.append(input, text);
    statsYearOptions.append(label);
  }

  syncSelectAllState();
}

function syncSelectAllState() {
  statsYearSelectAll.checked = (
    state.availableYears.length > 0 &&
    state.selectedYears.size === state.availableYears.length
  );
}

function getSelectedThreshold() {
  const value = Number(yieldThresholdInput.value || 0);
  return value >= 0 ? value : 0;
}

function getFilteredDividends() {
  return state.dividends.filter((item) => state.selectedYears.has(String(item.year)));
}

function buildStatsItems() {
  const map = new Map();
  for (const item of getFilteredDividends()) {
    const key = `${item.account}__${item.symbol}`;
    const current = map.get(key) || {
      account: item.account,
      symbol: item.symbol,
      name: item.name,
      years: new Set(),
      record_count: 0,
      yield_total: 0,
      net_total: 0,
    };
    current.name = current.name || item.name;
    current.years.add(String(item.year));
    current.record_count += 1;
    current.yield_total += Number(item.yield_rate || 0);
    current.net_total += Number(item.net_amount || 0);
    map.set(key, current);
  }

  return [...map.values()]
    .map((item) => ({
      account: item.account,
      symbol: item.symbol,
      name: item.name,
      year_count: item.years.size,
      record_count: item.record_count,
      yield_total: Number(item.yield_total.toFixed(2)),
      net_total: Number(item.net_total.toFixed(2)),
    }));
}

function getStatsSortValue(item, key) {
  switch (key) {
    case "account":
      return item.account;
    case "symbol":
      return item.symbol;
    case "name":
      return item.name;
    case "year_count":
      return item.year_count;
    case "record_count":
      return item.record_count;
    case "yield_total":
      return item.yield_total;
    case "net_total":
      return item.net_total;
    default:
      return item.yield_total;
  }
}

function getSortedStatsItems(items) {
  return items
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const compared = compareSortValues(
        getStatsSortValue(left.item, state.statsSort.key),
        getStatsSortValue(right.item, state.statsSort.key),
        state.statsSort.direction,
      );
      if (compared !== 0) {
        return compared;
      }
      return left.index - right.index;
    })
    .map((entry) => entry.item);
}

function renderStatsSortHeaders() {
  statsSortHeaders.forEach((header) => {
    const direction = header.dataset.sort === state.statsSort.key
      ? state.statsSort.direction
      : "";
    if (direction) {
      header.dataset.sortDirection = direction;
    } else {
      delete header.dataset.sortDirection;
    }
  });
}

function cycleStatsSort(key) {
  if (state.statsSort.key !== key) {
    state.statsSort = { key, direction: "desc" };
  } else if (state.statsSort.direction === "desc") {
    state.statsSort = { key, direction: "asc" };
  } else {
    state.statsSort = { ...DEFAULT_STATS_SORT };
  }
  saveStatsSortState();
  renderStatsSortHeaders();
  renderStats();
}

function renderSummary(items) {
  selectedYearsText.textContent = state.selectedYears.size > 0
    ? [...state.selectedYears].sort().join("、")
    : "-";
  stockCountText.textContent = formatNumber(items.length);
  netTotalText.textContent = formatNumber(
    items.reduce((sum, item) => sum + item.net_total, 0)
  );
  aboveThresholdText.textContent = formatNumber(
    items.filter((item) => item.yield_total >= getSelectedThreshold()).length
  );
}

function renderStats() {
  const items = getSortedStatsItems(buildStatsItems());
  const threshold = getSelectedThreshold();
  statsTableBody.innerHTML = "";

  if (state.selectedYears.size === 0) {
    const row = document.createElement("tr");
    row.className = "empty-state";
    row.innerHTML = '<td colspan="7">請至少勾選一個年份</td>';
    statsTableBody.append(row);
    renderSummary([]);
    return;
  }

  if (items.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-state";
    row.innerHTML = '<td colspan="7">目前沒有符合條件的股利統計資料</td>';
    statsTableBody.append(row);
    renderSummary([]);
    return;
  }

  for (const item of items) {
    const fragment = statsRowTemplate.content.cloneNode(true);
    const row = fragment.querySelector("tr");
    const isHighlighted = item.yield_total >= threshold;

    if (isHighlighted) {
      row.classList.add("stats-highlight-row");
    }

    row.querySelector('[data-key="account"]').textContent = item.account;
    row.querySelector('[data-key="symbol"]').textContent = item.symbol;
    row.querySelector('[data-key="name"]').textContent = item.name;
    row.querySelector('[data-key="year_count"]').textContent = formatNumber(item.year_count);
    row.querySelector('[data-key="record_count"]').textContent = formatNumber(item.record_count);

    const yieldCell = row.querySelector('[data-key="yield_total"]');
    yieldCell.textContent = formatPercent(item.yield_total);
    if (isHighlighted) {
      yieldCell.classList.add("stats-highlight-value");
    }

    const netCell = row.querySelector('[data-key="net_total"]');
    netCell.textContent = formatNumber(item.net_total);
    if (isHighlighted) {
      netCell.classList.add("stats-highlight-value");
    }
    statsTableBody.append(fragment);
  }

  renderSummary(items);
}

async function refreshAll() {
  await Promise.all([fetchAccounts(), fetchDividends()]);
  renderAccountOptions();
  syncAvailableYears();
  renderYearOptions();
  renderStatsSortHeaders();
  renderStats();
}

statsAccountFilter.addEventListener("change", async () => {
  await fetchDividends();
  syncAvailableYears();
  renderYearOptions();
  renderStats();
});

statsYearSelectAll.addEventListener("change", () => {
  if (statsYearSelectAll.checked) {
    state.selectedYears = new Set(state.availableYears);
  } else {
    state.selectedYears = new Set();
  }
  renderYearOptions();
  renderStats();
});

statsSortHeaders.forEach((header) => {
  header.addEventListener("click", () => {
    cycleStatsSort(header.dataset.sort);
  });
});

yieldThresholdInput.addEventListener("input", () => {
  localStorage.setItem(YIELD_THRESHOLD_STORAGE_KEY, String(getSelectedThreshold()));
  renderStats();
});

function restoreSavedThreshold() {
  const saved = localStorage.getItem(YIELD_THRESHOLD_STORAGE_KEY);
  if (!saved) {
    return;
  }
  const value = Number(saved);
  if (!Number.isNaN(value) && value >= 0) {
    yieldThresholdInput.value = String(value);
  }
}

restoreSavedThreshold();

refreshAll().catch((error) => {
  showNotice(`無法載入股利統計頁：${error.message}`, "error");
});

hideNotice();
