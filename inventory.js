const inventoryAccountFilter = document.querySelector("#inventory-account-filter");
const inventoryTableBody = document.querySelector("#inventory-table-body");
const inventoryRowTemplate = document.querySelector("#inventory-row-template");
const refreshPriceButton = document.querySelector("#refresh-price-button");
const bulkTargetPercentage = document.querySelector("#bulk-target-percentage");
const bulkTargetEmptyOnly = document.querySelector("#bulk-target-empty-only");
const applyBulkTargetButton = document.querySelector("#apply-bulk-target-button");
const inventoryCostTotal = document.querySelector("#inventory-cost-total");
const marketValueTotal = document.querySelector("#market-value-total");
const unrealizedProfitTotal = document.querySelector("#unrealized-profit-total");
const readySellCount = document.querySelector("#ready-sell-count");
const quoteStatusText = document.querySelector("#quote-status-text");

const state = {
  accounts: [],
  inventory: [],
  summary: {
    inventory_cost: 0,
    market_value: 0,
    unrealized_profit: 0,
    ready_to_sell_count: 0,
  },
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

function formatDateTime(value) {
  if (!value) {
    return "尚未更新";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-TW", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

async function fetchAccounts() {
  const payload = await requestJson("/api/accounts");
  state.accounts = payload.items || [];
}

async function fetchInventory() {
  const account = inventoryAccountFilter.value || "ALL";
  const payload = await requestJson(`/api/inventory?account=${encodeURIComponent(account)}`);
  state.inventory = payload.items || [];
  state.summary = payload.summary || state.summary;
}

function renderAccountOptions() {
  const currentValue = inventoryAccountFilter.value;
  inventoryAccountFilter.innerHTML = '<option value="ALL">全部帳戶</option>';

  for (const account of state.accounts) {
    const option = document.createElement("option");
    option.value = account.name;
    option.textContent = account.name;
    inventoryAccountFilter.append(option);
  }

  inventoryAccountFilter.value = state.accounts.some((account) => account.name === currentValue)
    ? currentValue
    : "ALL";
}

function renderSummary() {
  inventoryCostTotal.textContent = formatNumber(state.summary.inventory_cost);
  marketValueTotal.textContent = formatNumber(state.summary.market_value);
  unrealizedProfitTotal.textContent = formatNumber(state.summary.unrealized_profit);
  readySellCount.textContent = formatNumber(state.summary.ready_to_sell_count);

  const latestUpdatedAt = state.inventory
    .map((item) => item.price_updated_at)
    .filter(Boolean)
    .sort()
    .at(-1);
  quoteStatusText.textContent = formatDateTime(latestUpdatedAt);
}

function renderInventoryTable() {
  inventoryTableBody.innerHTML = "";

  if (state.inventory.length === 0) {
    const row = document.createElement("tr");
    row.className = "empty-state";
    row.innerHTML = '<td colspan="13">目前沒有庫存資料</td>';
    inventoryTableBody.append(row);
    renderSummary();
    return;
  }

  state.inventory.forEach((item) => {
    const fragment = inventoryRowTemplate.content.cloneNode(true);
    const row = fragment.querySelector("tr");
    if (item.target_hit) {
      row.classList.add("target-hit");
    }

    row.querySelector('[data-key="account"]').textContent = item.account;
    row.querySelector('[data-key="symbol"]').textContent = item.symbol;
    row.querySelector('[data-key="name"]').textContent = item.name;
    row.querySelector('[data-key="quantity"]').textContent = formatNumber(item.quantity);
    row.querySelector('[data-key="avg_price"]').textContent = formatNumber(item.avg_price, 2);
    row.querySelector('[data-key="inventory_cost"]').textContent = formatNumber(item.inventory_cost);
    row.querySelector('[data-key="latest_price"]').textContent = item.latest_price === null
      ? "待更新"
      : formatNumber(item.latest_price, 2);
    row.querySelector('[data-key="market_value"]').textContent = formatNumber(item.market_value);
    row.querySelector('[data-key="unrealized_profit"]').textContent = formatNumber(item.unrealized_profit);
    row.querySelector('[data-key="unrealized_profit_pct"]').textContent = formatPercent(item.unrealized_profit_pct);

    const targetInput = row.querySelector(".target-input");
    const noteInput = row.querySelector(".note-input");
    targetInput.value = item.target_sell_price ?? "";
    noteInput.value = item.note || "";

    row.querySelector(".inventory-save").addEventListener("click", async () => {
      try {
        await requestJson("/api/inventory/target", {
          method: "POST",
          body: JSON.stringify({
            account: item.account,
            symbol: item.symbol,
            target_sell_price: targetInput.value.trim(),
            note: noteInput.value.trim(),
          }),
        });
        await fetchInventory();
        renderInventoryTable();
      } catch (error) {
        alert(error.message);
      }
    });

    inventoryTableBody.append(fragment);
  });

  renderSummary();
}

async function refreshAll() {
  await Promise.all([fetchAccounts(), fetchInventory()]);
  renderAccountOptions();
  renderInventoryTable();
}

inventoryAccountFilter.addEventListener("change", async () => {
  await fetchInventory();
  renderInventoryTable();
});

refreshPriceButton.addEventListener("click", async () => {
  try {
    refreshPriceButton.disabled = true;
    await requestJson("/api/prices/refresh", { method: "POST", body: "{}" });
    await fetchInventory();
    renderInventoryTable();
  } catch (error) {
    alert(error.message);
  } finally {
    refreshPriceButton.disabled = false;
  }
});

applyBulkTargetButton.addEventListener("click", async () => {
  const percentage = Number(bulkTargetPercentage.value);
  if (!percentage || percentage <= 0) {
    alert("請輸入大於 0 的百分比");
    return;
  }

  try {
    applyBulkTargetButton.disabled = true;
    await requestJson("/api/inventory/target/bulk", {
      method: "POST",
      body: JSON.stringify({
        percentage,
        account: inventoryAccountFilter.value || "ALL",
        only_empty_targets: bulkTargetEmptyOnly.checked,
      }),
    });
    await fetchInventory();
    renderInventoryTable();
  } catch (error) {
    alert(error.message);
  } finally {
    applyBulkTargetButton.disabled = false;
  }
});

refreshAll().catch((error) => {
  alert(`無法載入庫存頁：${error.message}`);
});
