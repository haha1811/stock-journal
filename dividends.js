const dividendAccountFilter = document.querySelector("#dividend-account-filter");
const dividendTableBody = document.querySelector("#dividend-table-body");
const dividendRowTemplate = document.querySelector("#dividend-row-template");
const dividendSortHeaders = document.querySelectorAll("th[data-sort]");
const refreshDividendButton = document.querySelector("#refresh-dividend-button");
const dividendStatusText = document.querySelector("#dividend-status-text");
const dividendNotice = document.querySelector("#dividend-notice");
const manualDividendForm = document.querySelector("#manual-dividend-form");
const manualDividendTitle = document.querySelector("#manual-dividend-title");
const manualDividendSubmit = document.querySelector("#manual-dividend-submit");
const manualDividendReset = document.querySelector("#manual-dividend-reset");
const manualAccount = document.querySelector("#manual-account");
const manualSymbol = document.querySelector("#manual-symbol");
const manualName = document.querySelector("#manual-name");
const manualExDate = document.querySelector("#manual-ex-date");
const manualPaymentDate = document.querySelector("#manual-payment-date");
const manualEligibleUnits = document.querySelector("#manual-eligible-units");
const manualDividendPerUnit = document.querySelector("#manual-dividend-per-unit");
const manualAvgPrice = document.querySelector("#manual-avg-price");
const manualYieldRate = document.querySelector("#manual-yield-rate");
const DIVIDEND_SORT_STORAGE_KEY = "stock-dividend-sort-v1";
const DEFAULT_DIVIDEND_SORT = { key: "ex_dividend_date", direction: "desc" };

const state = {
  accounts: [],
  dividends: [],
  editingManualDividendId: null,
  dividendSort: loadDividendSortState(),
  noticeTimer: null,
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
  return value === null || value === undefined ? "-" : `${formatNumber(value, 2)}%`;
}

function showNotice(message, type = "info", keepVisible = false) {
  if (!dividendNotice) {
    return;
  }
  if (state.noticeTimer) {
    window.clearTimeout(state.noticeTimer);
    state.noticeTimer = null;
  }

  dividendNotice.textContent = message;
  dividendNotice.hidden = false;
  dividendNotice.className = `page-notice is-${type}`;

  if (!keepVisible) {
    state.noticeTimer = window.setTimeout(() => {
      dividendNotice.hidden = true;
      dividendNotice.className = "page-notice";
      state.noticeTimer = null;
    }, 4000);
  }
}

async function fetchAccounts() {
  const payload = await requestJson("/api/accounts");
  state.accounts = payload.items || [];
}

async function fetchDividends() {
  const account = dividendAccountFilter.value || "ALL";
  const payload = await requestJson(`/api/dividends?account=${encodeURIComponent(account)}`);
  state.dividends = payload.items || [];
}

function loadDividendSortState() {
  try {
    const raw = localStorage.getItem(DIVIDEND_SORT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed?.key && ["asc", "desc"].includes(parsed?.direction)) {
      return parsed;
    }
  } catch (error) {
    console.error("讀取股利排序設定失敗", error);
  }
  return { ...DEFAULT_DIVIDEND_SORT };
}

function saveDividendSortState() {
  localStorage.setItem(DIVIDEND_SORT_STORAGE_KEY, JSON.stringify(state.dividendSort));
}

function getDividendSortValue(item, key) {
  switch (key) {
    case "account":
      return item.account || "";
    case "ex_dividend_date":
      return item.ex_dividend_date || "";
    case "payment_date":
      return item.payment_date || "";
    case "year":
      return Number(item.year || 0);
    case "month":
      return Number(item.month || 0);
    case "symbol":
      return item.symbol || "";
    case "name":
      return item.name || "";
    case "eligible_units":
      return Number(item.eligible_units || 0);
    case "avg_price":
      return item.avg_price === null || item.avg_price === undefined ? null : Number(item.avg_price);
    case "cash_dividend_per_unit":
      return Number(item.cash_dividend_per_unit || 0);
    case "yield_rate":
      return item.yield_rate === null || item.yield_rate === undefined ? null : Number(item.yield_rate);
    case "gross_amount":
      return Number(item.gross_amount || 0);
    case "bank_fee":
      return Number(item.bank_fee || 0);
    case "net_amount":
      return Number(item.net_amount || 0);
    case "source":
      return item.is_manual ? "手動" : "官方";
    default:
      return item.ex_dividend_date || "";
  }
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

function getSortedDividends(items) {
  return items
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const compared = compareSortValues(
        getDividendSortValue(left.item, state.dividendSort.key),
        getDividendSortValue(right.item, state.dividendSort.key),
        state.dividendSort.direction,
      );
      if (compared !== 0) {
        return compared;
      }
      return left.index - right.index;
    })
    .map((entry) => entry.item);
}

function renderDividendSortHeaders() {
  dividendSortHeaders.forEach((header) => {
    const direction = header.dataset.sort === state.dividendSort.key
      ? state.dividendSort.direction
      : "";
    if (direction) {
      header.dataset.sortDirection = direction;
    } else {
      delete header.dataset.sortDirection;
    }
  });
}

function cycleDividendSort(key) {
  if (state.dividendSort.key !== key) {
    state.dividendSort = { key, direction: "desc" };
  } else if (state.dividendSort.direction === "desc") {
    state.dividendSort = { key, direction: "asc" };
  } else {
    state.dividendSort = { ...DEFAULT_DIVIDEND_SORT };
  }
  saveDividendSortState();
  renderDividendSortHeaders();
  renderDividendTable();
}

function renderAccountOptions() {
  const currentValue = dividendAccountFilter.value;
  const currentManualValue = manualAccount.value;
  dividendAccountFilter.innerHTML = '<option value="ALL">全部帳戶</option>';
  manualAccount.innerHTML = "";

  for (const account of state.accounts) {
    const option = document.createElement("option");
    option.value = account.name;
    option.textContent = account.name;
    dividendAccountFilter.append(option);

    const manualOption = document.createElement("option");
    manualOption.value = account.name;
    manualOption.textContent = account.name;
    manualAccount.append(manualOption);
  }

  dividendAccountFilter.value = state.accounts.some((account) => account.name === currentValue)
    ? currentValue
    : "ALL";
  manualAccount.value = state.accounts.some((account) => account.name === currentManualValue)
    ? currentManualValue
    : (state.accounts[0]?.name || "主帳戶");
}

function resetManualDividendForm() {
  state.editingManualDividendId = null;
  manualDividendTitle.textContent = "新增歷史股利";
  manualDividendSubmit.textContent = "新增股利";
  manualDividendReset.textContent = "清空";
  manualDividendForm.reset();
  manualAccount.value = state.accounts[0]?.name || "主帳戶";
}

function renderDividendTable() {
  const items = getSortedDividends(state.dividends);
  dividendTableBody.innerHTML = "";

  if (items.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-state";
    row.innerHTML = '<td colspan="16">目前沒有可顯示的股利資料</td>';
    dividendTableBody.append(row);
    return;
  }

  for (const item of items) {
    const fragment = dividendRowTemplate.content.cloneNode(true);
    const row = fragment.querySelector("tr");

    row.querySelector('[data-key="account"]').textContent = item.account;
    row.querySelector('[data-key="ex_dividend_date"]').textContent = item.ex_dividend_date;
    row.querySelector('[data-key="payment_date"]').textContent = item.payment_date;
    row.querySelector('[data-key="year"]').textContent = item.year;
    row.querySelector('[data-key="month"]').textContent = item.month;
    row.querySelector('[data-key="symbol"]').textContent = item.symbol;
    row.querySelector('[data-key="name"]').textContent = item.name;
    row.querySelector('[data-key="eligible_units"]').textContent = formatNumber(item.eligible_units);
    row.querySelector('[data-key="avg_price"]').textContent = formatNumber(item.avg_price, 2);
    row.querySelector('[data-key="cash_dividend_per_unit"]').textContent = formatNumber(item.cash_dividend_per_unit, 3);
    row.querySelector('[data-key="yield_rate"]').textContent = formatPercent(item.yield_rate);
    row.querySelector('[data-key="gross_amount"]').textContent = formatNumber(item.gross_amount);
    row.querySelector('[data-key="net_amount"]').textContent = formatNumber(item.net_amount);
    row.querySelector('[data-key="source"]').textContent = item.is_manual ? "手動" : "官方";

    const bankFeeInput = row.querySelector(".bank-fee-input");
    bankFeeInput.value = item.bank_fee ?? 0;

    row.querySelector(".dividend-save").addEventListener("click", async () => {
      try {
        await requestJson("/api/dividends/adjustment", {
          method: "POST",
          body: JSON.stringify({
            account: item.account,
            symbol: item.symbol,
            ex_dividend_date: item.ex_dividend_date,
            payment_date: item.payment_date,
            bank_fee: bankFeeInput.value.trim(),
          }),
        });
        await fetchDividends();
        renderDividendTable();
        showNotice("跨行扣款已儲存", "success");
      } catch (error) {
        showNotice(error.message, "error", true);
      }
    });

    if (item.is_manual) {
      const editButton = row.querySelector(".dividend-edit");
      const deleteButton = row.querySelector(".dividend-delete");
      editButton.hidden = false;
      deleteButton.hidden = false;

      editButton.addEventListener("click", () => {
        state.editingManualDividendId = item.manual_event_id;
        manualDividendTitle.textContent = "編輯手動股利";
        manualDividendSubmit.textContent = "更新股利";
        manualDividendReset.textContent = "取消";
        manualAccount.value = item.account;
        manualSymbol.value = item.symbol;
        manualName.value = item.name;
        manualExDate.value = item.ex_dividend_date;
        manualPaymentDate.value = item.payment_date;
        manualEligibleUnits.value = item.eligible_units ?? "";
        manualDividendPerUnit.value = item.cash_dividend_per_unit;
        manualAvgPrice.value = item.avg_price ?? "";
        manualYieldRate.value = item.yield_rate ?? "";
        manualSymbol.focus();
      });

      deleteButton.addEventListener("click", async () => {
        if (!window.confirm("確定要刪除這筆手動股利資料嗎？")) {
          return;
        }

        try {
          await requestJson(`/api/dividends/manual/${item.manual_event_id}`, { method: "DELETE" });
          if (state.editingManualDividendId === item.manual_event_id) {
            resetManualDividendForm();
          }
          await fetchDividends();
          renderDividendTable();
          showNotice("手動股利已刪除", "success");
        } catch (error) {
          showNotice(error.message, "error", true);
        }
      });
    }

    dividendTableBody.append(fragment);
  }
}

dividendSortHeaders.forEach((header) => {
  header.addEventListener("click", () => {
    cycleDividendSort(header.dataset.sort);
  });
});

async function refreshAll() {
  await Promise.all([fetchAccounts(), fetchDividends()]);
  renderAccountOptions();
  renderDividendSortHeaders();
  renderDividendTable();
}

dividendAccountFilter.addEventListener("change", async () => {
  await fetchDividends();
  renderDividendTable();
});

refreshDividendButton.addEventListener("click", async () => {
  try {
    refreshDividendButton.disabled = true;
    await requestJson("/api/dividends/refresh", { method: "POST", body: "{}" });
    dividendStatusText.textContent = "已手動刷新一次";
    await fetchDividends();
    renderDividendTable();
    showNotice("股利資料已更新", "success");
  } catch (error) {
    showNotice(error.message, "error", true);
  } finally {
    refreshDividendButton.disabled = false;
  }
});

manualDividendForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const payload = {
    account: manualAccount.value,
    symbol: manualSymbol.value.trim(),
    name: manualName.value.trim(),
    ex_dividend_date: manualExDate.value,
    payment_date: manualPaymentDate.value,
    eligible_units: manualEligibleUnits.value.trim(),
    cash_dividend_per_unit: manualDividendPerUnit.value,
    avg_price: manualAvgPrice.value.trim(),
    yield_rate: manualYieldRate.value.trim(),
  };

  const isEditing = Boolean(state.editingManualDividendId);
  const url = isEditing
    ? `/api/dividends/manual/${state.editingManualDividendId}`
    : "/api/dividends/manual";
  const method = isEditing ? "PUT" : "POST";

  try {
    await requestJson(url, {
      method,
      body: JSON.stringify(payload),
    });
    resetManualDividendForm();
    await fetchDividends();
    renderDividendTable();
    showNotice(isEditing ? "手動股利已更新" : "手動股利已新增", "success");
  } catch (error) {
    showNotice(error.message, "error", true);
  }
});

manualDividendReset.addEventListener("click", resetManualDividendForm);

refreshAll().catch((error) => {
  showNotice(`無法載入股利頁：${error.message}`, "error", true);
});
