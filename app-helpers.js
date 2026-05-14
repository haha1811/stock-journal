(function (root, factory) {
  const helpers = factory();

  if (typeof module === "object" && module.exports) {
    module.exports = helpers;
  }

  root.StockJournalHelpers = helpers;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function findKnownStockName(trades, symbol) {
    const normalizedSymbol = String(symbol || "").trim();
    if (!normalizedSymbol || !Array.isArray(trades)) return "";

    const match = trades.find((trade) => {
      const tradeSymbol = String(trade?.symbol || "").trim();
      const tradeName = String(trade?.name || "").trim();
      return tradeSymbol === normalizedSymbol && Boolean(tradeName);
    });

    return match ? String(match.name).trim() : "";
  }

  return { findKnownStockName };
});
