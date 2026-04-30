const LEGACY_STORAGE_KEY = "stock-trade-log-v1";
const form = document.querySelector("#trade-form");
const accountSelect = document.querySelector("#account");
const tableBody = document.querySelector("#trade-table-body");
const template = document.querySelector("#table-row-template");
const accountTableBody = document.querySelector("#account-table-body");
const accountRowTemplate = document.querySelector("#account-row-template");
const accountFilter = document.querySelector("#account-filter");
const yearFilter = document.querySelector("#year-filter");
const searchInput = document.querySelector("#search-input");
const exportButton = document.querySelector("#export-button");
const importFile = document.querySelector("#import-file");
const toggleAccountPanelButton = document.querySelector("#toggle-account-panel");
const closeAccountPanelButton = document.querySelector("#close-account-panel");
const resetButton = document.querySelector("#reset-button");
const cancelEditButton = document.querySelector("#cancel-edit-button");
const submitButton = document.querySelector("#submit-button");
const accountPanel = document.querySelector("#account-panel");
const accountForm = document.querySelector("#account-form");
const accountNameInput = document.querySelector("#account-name-input");
const accountFormLabel = document.querySelector("#account-form-label");
const accountSubmitButton = document.querySelector("#account-submit-button");
const accountResetButton = document.querySelector("#account-reset-button");
const formTitle = document.querySelector("#form-title");
const formDescription = document.querySelector("#form-description");
const editingBanner = document.querySelector("#editing-banner");
const editingBannerText = document.querySelector("#editing-banner-text");
const tradeSortHeaders = document.querySelectorAll("th[data-sort]");

const previewAmount = document.querySelector("#preview-amount");
const previewTax = document.querySelector("#preview-tax");
const previewCashflow = document.querySelector("#preview-cashflow");

const buyTotal = document.querySelector("#buy-total");
const sellTotal = document.querySelector("#sell-total");
const netTotal = document.querySelector("#net-total");
const costTotal = document.querySelector("#cost-total");
const TRADE_SORT_STORAGE_KEY = "stock-trade-sort-v1";
const DEFAULT_TRADE_SORT = { key: "date", direction: "desc" };

const state = {
  accounts: [],
  trades: [],
  editingTradeId: null,
  editingAccountId: null,
  tradeSort: loadTradeSortState(),
};

function getTodayString() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getYearFromDate(dateString) {
  return dateString ? dateString.slice(0, 4) : "";
}

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
    const errorCode = payload.error || "系統發生錯誤";

    if (response.status === 401 && errorCode === "authentication_required") {
      window.location.href = "/login.html";
    }

    throw new Error(errorCode);
  }

  return payload;
}

function formatNumber(value, fractionDigits = 0) {
  return new Intl.NumberFormat("zh-TW", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

function calculateAmount(quantity, price) {
  return Number(quantity) * Number(price);
}

function calculateTax(side, amount) {
  if (side !== "賣出") {
    return 0;
  }

  return Math.round(amount * 0.003);
}

function getTradeFromForm() {
  const formData = new FormData(form);
  const quantity = Number(formData.get("quantity"));
  const price = Number(formData.get("price"));
  const amount = calculateAmount(quantity, price);
  const side = formData.get("side");
  const enteredTax = Number(formData.get("tax"));
  const autoTax = calculateTax(side, amount);
  const tradeDate = formData.get("date");

  return {
    id: state.editingTradeId || crypto.randomUUID(),
    account: String(formData.get("account")).trim() || "主帳戶",
    settlement: formData.get("settlement"),
    side,
    date: tradeDate,
    year: getYearFromDate(tradeDate),
    symbol: String(formData.get("symbol")).trim(),
    name: String(formData.get("name")).trim(),
    quantity,
    price,
    amount,
    fee: Number(formData.get("fee")),
    tax: enteredTax || autoTax,
    note: String(formData.get("note")).trim(),
  };
}

async function fetchTrades() {
  const payload = await requestJson("/api/trades");
  state.trades = payload.items || [];
}

async function fetchAccounts() {
  const payload = await requestJson("/api/accounts");
  state.accounts = payload.items || [];
}

function getLegacyTrades() {
  try {
    const raw = localStorage.getItem(LEGACY_STORAGE_KEY);
    const items = raw ? JSON.parse(raw) : [];
    return Array.isArray(items)
      ? items.map((item) => ({ ...item, account: item.account || "主帳戶" }))
      : [];
  } catch (error) {
    console.error("讀取舊版瀏覽器資料失敗", error);
    return [];
  }
}

function populateForm(trade) {
  form.settlement.value = trade.settlement;
  form.side.value = trade.side;
  form.date.value = trade.date;
  form.account.value = trade.account || "主帳戶";
  form.symbol.value = trade.symbol;
  form.name.value = trade.name;
  form.quantity.value = trade.quantity;
  form.price.value = trade.price;
  form.fee.value = trade.fee;
  form.tax.value = trade.tax;
  form.note.value = trade.note || "";
  renderPreview();
}

function openAccountPanel() {
  accountPanel.hidden = false;
}

function closeAccountPanel() {
  accountPanel.hidden = true;
  resetAccountForm();
}

function setEditingState(trade) {
  state.editingTradeId = trade.id;
  formTitle.textContent = "編輯交易";
  formDescription.textContent = "修改完成後按下儲存，系統會直接更新原本那一筆資料。";
  submitButton.textContent = "更新交易";
  resetButton.textContent = "還原";
  editingBanner.hidden = false;
  editingBanner.classList.remove("is-hidden");
  editingBannerText.textContent = `正在編輯 ${trade.date} ${trade.symbol} ${trade.name}`;
  populateForm(trade);
}

function clearEditingState() {
  state.editingTradeId = null;
  formTitle.textContent = "新增交易";
  formDescription.textContent = "輸入一次後會自動儲存在瀏覽器。";
  submitButton.textContent = "儲存交易";
  resetButton.textContent = "清空";
  editingBanner.hidden = true;
  editingBanner.classList.add("is-hidden");
}

function getEditingTrade() {
  return state.trades.find((trade) => trade.id === state.editingTradeId) || null;
}

function getEditingAccount() {
  return state.accounts.find((account) => account.id === state.editingAccountId) || null;
}

function renderPreview() {
  const quantity = Number(form.quantity.value || 0);
  const price = Number(form.price.value || 0);
  const amount = calculateAmount(quantity, price);
  const tax = calculateTax(form.side.value, amount);
  const fee = Number(form.fee.value || 0);
  const cashflow = form.side.value === "買入"
    ? -(amount + fee + tax)
    : amount - fee - tax;

  previewAmount.textContent = formatNumber(amount);
  previewTax.textContent = formatNumber(tax);
  previewCashflow.textContent = formatNumber(cashflow);

  if (!form.tax.value || Number(form.tax.value) === 0) {
    form.tax.value = tax;
  }
}

function getFilteredTrades() {
  const selectedAccount = accountFilter.value;
  const selectedYear = yearFilter.value;
  const keyword = searchInput.value.trim().toLowerCase();

  return state.trades.filter((trade) => {
    const matchesAccount = selectedAccount === "ALL" || (trade.account || "主帳戶") === selectedAccount;
    const matchesYear = selectedYear === "ALL" || String(trade.year) === selectedYear;
    const haystack = `${trade.symbol} ${trade.name}`.toLowerCase();
    const matchesSearch = !keyword || haystack.includes(keyword);
    return matchesAccount && matchesYear && matchesSearch;
  });
}

function loadTradeSortState() {
  try {
    const raw = localStorage.getItem(TRADE_SORT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (parsed?.key && ["asc", "desc"].includes(parsed?.direction)) {
      return parsed;
    }
  } catch (error) {
    console.error("讀取交易排序設定失敗", error);
  }
  return { ...DEFAULT_TRADE_SORT };
}

function saveTradeSortState() {
  localStorage.setItem(TRADE_SORT_STORAGE_KEY, JSON.stringify(state.tradeSort));
}

function getTradeSortValue(trade, key) {
  switch (key) {
    case "settlement":
      return trade.settlement || "";
    case "side":
      return trade.side || "";
    case "date":
      return trade.date || "";
    case "year":
      return Number(trade.year || 0);
    case "account":
      return trade.account || "主帳戶";
    case "symbol":
      return trade.symbol || "";
    case "name":
      return trade.name || "";
    case "quantity":
      return Number(trade.quantity || 0);
    case "price":
      return Number(trade.price || 0);
    case "amount":
      return Number(trade.amount || 0);
    case "fee":
      return Number(trade.fee || 0);
    case "tax":
      return Number(trade.tax || 0);
    case "note":
      return trade.note || "";
    default:
      return trade.date || "";
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

function getSortedTrades(items) {
  return items
    .map((trade, index) => ({ trade, index }))
    .sort((left, right) => {
      const compared = compareSortValues(
        getTradeSortValue(left.trade, state.tradeSort.key),
        getTradeSortValue(right.trade, state.tradeSort.key),
        state.tradeSort.direction,
      );
      if (compared !== 0) {
        return compared;
      }
      return left.index - right.index;
    })
    .map((item) => item.trade);
}

function renderTradeSortHeaders() {
  tradeSortHeaders.forEach((header) => {
    const direction = header.dataset.sort === state.tradeSort.key
      ? state.tradeSort.direction
      : "";
    if (direction) {
      header.dataset.sortDirection = direction;
    } else {
      delete header.dataset.sortDirection;
    }
  });
}

function cycleTradeSort(key) {
  if (state.tradeSort.key !== key) {
    state.tradeSort = { key, direction: "desc" };
  } else if (state.tradeSort.direction === "desc") {
    state.tradeSort = { key, direction: "asc" };
  } else {
    state.tradeSort = { ...DEFAULT_TRADE_SORT };
  }
  saveTradeSortState();
  renderTradeSortHeaders();
  renderTable();
}

function renderAccountOptions() {
  const accounts = state.accounts.map((account) => account.name);
  const currentValue = accountFilter.value;
  accountFilter.innerHTML = '<option value="ALL">全部帳戶</option>';
  accountSelect.innerHTML = "";

  for (const account of accounts) {
    const option = document.createElement("option");
    option.value = account;
    option.textContent = account;
    accountFilter.append(option);
    accountSelect.append(option.cloneNode(true));
  }

  accountFilter.value = accounts.includes(currentValue) ? currentValue : "ALL";

  const currentFormValue = accountSelect.value;
  if (state.editingTradeId) {
    const editingTrade = getEditingTrade();
    accountSelect.value = accounts.includes(editingTrade?.account) ? editingTrade.account : accounts[0] || "主帳戶";
  } else {
    accountSelect.value = accounts.includes(currentFormValue) ? currentFormValue : accounts[0] || "主帳戶";
  }
}

function getTradesForYearOptions() {
  const selectedAccount = accountFilter.value;

  return state.trades.filter((trade) => (
    selectedAccount === "ALL" || (trade.account || "主帳戶") === selectedAccount
  ));
}

function renderYearOptions() {
  const years = [...new Set(getTradesForYearOptions().map((trade) => String(trade.year)).filter(Boolean))].sort();
  const currentValue = yearFilter.value;
  yearFilter.innerHTML = '<option value="ALL">全部</option>';

  for (const year of years) {
    const option = document.createElement("option");
    option.value = year;
    option.textContent = year;
    yearFilter.append(option);
  }

  yearFilter.value = years.includes(currentValue) ? currentValue : "ALL";
}

function renderSummary() {
  const trades = getFilteredTrades();

  const totals = trades.reduce((accumulator, trade) => {
    if (trade.side === "買入") {
      accumulator.buy += trade.amount;
    } else {
      accumulator.sell += trade.amount;
    }

    accumulator.cost += trade.fee + trade.tax;
    return accumulator;
  }, { buy: 0, sell: 0, cost: 0 });

  buyTotal.textContent = formatNumber(totals.buy);
  sellTotal.textContent = formatNumber(totals.sell);
  netTotal.textContent = formatNumber(totals.sell - totals.buy);
  costTotal.textContent = formatNumber(totals.cost);
}

function renderTable() {
  const trades = getSortedTrades(getFilteredTrades());
  tableBody.innerHTML = "";

  if (trades.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-state";
    row.innerHTML = '<td colspan="15">目前沒有符合條件的交易紀錄</td>';
    tableBody.append(row);
    renderSummary();
    return;
  }

  trades.forEach((trade, index) => {
    const fragment = template.content.cloneNode(true);
    const row = fragment.querySelector("tr");

    row.querySelector('[data-key="index"]').textContent = index + 1;
    row.querySelector('[data-key="settlement"]').textContent = trade.settlement;
    row.querySelector('[data-key="side"]').textContent = trade.side;
    row.querySelector('[data-key="date"]').textContent = trade.date;
    row.querySelector('[data-key="year"]').textContent = trade.year;
    row.querySelector('[data-key="account"]').textContent = trade.account || "主帳戶";
    row.querySelector('[data-key="symbol"]').textContent = trade.symbol;
    row.querySelector('[data-key="name"]').textContent = trade.name;
    row.querySelector('[data-key="quantity"]').textContent = formatNumber(trade.quantity);
    row.querySelector('[data-key="price"]').textContent = formatNumber(trade.price, 2);
    row.querySelector('[data-key="amount"]').textContent = formatNumber(trade.amount);
    row.querySelector('[data-key="fee"]').textContent = formatNumber(trade.fee);
    row.querySelector('[data-key="tax"]').textContent = formatNumber(trade.tax);
    row.querySelector('[data-key="note"]').textContent = trade.note || "-";

    row.querySelector(".row-edit").addEventListener("click", () => {
      setEditingState(trade);
    });

    row.querySelector(".row-delete").addEventListener("click", () => {
      handleDeleteTrade(trade.id);
    });

    tableBody.append(fragment);
  });

  renderSummary();
}

tradeSortHeaders.forEach((header) => {
  header.addEventListener("click", () => {
    cycleTradeSort(header.dataset.sort);
  });
});

function renderAccountTable() {
  accountTableBody.innerHTML = "";

  if (state.accounts.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-state";
    row.innerHTML = '<td colspan="2">目前沒有帳戶資料</td>';
    accountTableBody.append(row);
    return;
  }

  state.accounts.forEach((account) => {
    const fragment = accountRowTemplate.content.cloneNode(true);
    const row = fragment.querySelector("tr");
    row.querySelector('[data-key="name"]').textContent = account.name;

    row.querySelector(".account-edit").addEventListener("click", () => {
      state.editingAccountId = account.id;
      accountFormLabel.textContent = "編輯帳戶";
      accountSubmitButton.textContent = "更新帳戶";
      accountResetButton.textContent = "取消";
      accountNameInput.value = account.name;
      openAccountPanel();
      accountNameInput.focus();
    });

    row.querySelector(".account-delete").addEventListener("click", async () => {
      if (!window.confirm(`確定要刪除帳戶「${account.name}」嗎？`)) {
        return;
      }

      try {
        await requestJson(`/api/accounts/${account.id}`, {
          method: "DELETE",
          headers: { "X-Confirm": "YES" },
        });
        if (state.editingAccountId === account.id) {
          resetAccountForm();
        }
        await refreshAccountsAndTrades();
      } catch (error) {
        alert(error.message);
      }
    });

    accountTableBody.append(fragment);
  });
}

function resetAccountForm() {
  state.editingAccountId = null;
  accountFormLabel.textContent = "新增帳戶";
  accountSubmitButton.textContent = "新增帳戶";
  accountResetButton.textContent = "清空";
  accountNameInput.value = "";
}

function resetForm() {
  clearEditingState();
  form.reset();
  form.quantity.value = 1000;
  form.fee.value = 0;
  form.tax.value = 0;
  form.account.value = "主帳戶";
  form.settlement.value = "Y";
  form.side.value = "買入";
  form.date.value = getTodayString();
  renderPreview();
}

function exportTrades() {
  const blob = new Blob([JSON.stringify(state.trades, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "stock-trades.json";
  anchor.click();
  URL.revokeObjectURL(url);
}

function importTrades(event) {
  const [file] = event.target.files;
  if (!file) {
    return;
  }

  const reader = new FileReader();
  reader.onload = () => {
    try {
      const imported = JSON.parse(String(reader.result));
      if (!Array.isArray(imported)) {
        throw new Error("格式錯誤");
      }
      syncImportedTrades(imported).catch((error) => {
        alert(error.message);
      });
    } catch (error) {
      alert("匯入失敗，請確認 JSON 格式正確。");
    } finally {
      importFile.value = "";
    }
  };
  reader.readAsText(file);
}

async function syncImportedTrades(items) {
  const payload = await requestJson("/api/trades/import", {
    method: "POST",
    body: JSON.stringify({ items }),
  });
  state.trades = payload.items || [];
  clearEditingState();
  await fetchAccounts();
  renderAccountOptions();
  renderAccountTable();
  renderYearOptions();
  renderTable();
}

async function handleDeleteTrade(tradeId) {
  if (!window.confirm("確定要刪除這筆交易嗎？")) {
    return;
  }

  try {
    await requestJson(`/api/trades/${tradeId}`, {
      method: "DELETE",
      headers: { "X-Confirm": "YES" },
    });
    state.trades = state.trades.filter((item) => item.id !== tradeId);

    if (state.editingTradeId === tradeId) {
      resetForm();
    }

    await fetchAccounts();
    renderAccountOptions();
    renderAccountTable();
    renderYearOptions();
    renderTable();
  } catch (error) {
    alert(error.message);
  }
}

async function refreshAccountsAndTrades() {
  await Promise.all([fetchAccounts(), fetchTrades()]);
  renderAccountOptions();
  renderAccountTable();
  renderYearOptions();
  renderTradeSortHeaders();
  renderTable();
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  submitTrade();
});

form.addEventListener("input", renderPreview);
yearFilter.addEventListener("change", renderTable);
accountFilter.addEventListener("change", () => {
  renderYearOptions();
  renderTable();
});
searchInput.addEventListener("input", renderTable);
exportButton.addEventListener("click", exportTrades);
importFile.addEventListener("change", importTrades);
resetButton.addEventListener("click", () => {
  const editingTrade = getEditingTrade();
  if (editingTrade) {
    populateForm(editingTrade);
    return;
  }

  resetForm();
});
cancelEditButton.addEventListener("click", resetForm);
toggleAccountPanelButton.addEventListener("click", openAccountPanel);
closeAccountPanelButton.addEventListener("click", closeAccountPanel);
accountResetButton.addEventListener("click", () => {
  if (state.editingAccountId) {
    resetAccountForm();
    return;
  }

  accountNameInput.value = "";
});

async function submitTrade() {
  const trade = getTradeFromForm();
  const isEditing = Boolean(state.editingTradeId);
  const url = isEditing ? `/api/trades/${trade.id}` : "/api/trades";
  const method = isEditing ? "PUT" : "POST";

  try {
    const payload = await requestJson(url, {
      method,
      body: JSON.stringify(trade),
    });

    const savedTrade = payload.item;
    const existingIndex = state.trades.findIndex((item) => item.id === savedTrade.id);

    if (existingIndex >= 0) {
      state.trades[existingIndex] = savedTrade;
    } else {
      state.trades.unshift(savedTrade);
    }

    await fetchAccounts();
    renderAccountOptions();
    renderAccountTable();
    renderYearOptions();
    renderTable();
    resetForm();
  } catch (error) {
    alert(error.message);
  }
}

accountForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const name = accountNameInput.value.trim();
  if (!name) {
    alert("請輸入帳戶名稱");
    return;
  }

  const isEditing = Boolean(state.editingAccountId);
  const url = isEditing ? `/api/accounts/${state.editingAccountId}` : "/api/accounts";
  const method = isEditing ? "PUT" : "POST";

  try {
    await requestJson(url, {
      method,
      body: JSON.stringify({ name }),
    });
    resetAccountForm();
    await refreshAccountsAndTrades();
  } catch (error) {
    alert(error.message);
  }
});

async function bootstrap() {
  resetForm();

  try {
    await Promise.all([fetchAccounts(), fetchTrades()]);

    if (state.trades.length === 0) {
      const legacyTrades = getLegacyTrades();
      if (legacyTrades.length > 0) {
        await syncImportedTrades(legacyTrades);
      }
    }

    renderAccountOptions();
    renderAccountTable();
    renderYearOptions();
    renderTradeSortHeaders();
    renderTable();
  } catch (error) {
    alert(`無法連線到後端：${error.message}`);
  }
}

bootstrap();
