# Changelog

本檔案用來記錄 `stock-journal` 每個版本的重要變更。

格式參考：
- 版本放在最上面
- 尚未發版的內容先寫在 `Unreleased`
- 每次發版時，把 `Unreleased` 內容整理到正式版號底下
- 建議分類使用：`Added`、`Changed`、`Fixed`

## [Unreleased]

### Added
- 待補充

### Changed
- 待補充

### Fixed
- 待補充

## [v0.3.1] - 2026-04-30

### Added
- Firebase Auth MVP：新增 Google 登入頁、前端 token bridge、後端 API 驗證守門與登出流程。
- 新增多使用者隔離資料模型：`accounts`、`trades`、`holding_targets`、`dividend_manual_events`、`dividend_adjustments` 全面加入 `owner_uid`。
- 新增協作權限資料表與 API：`user_permissions`、`POST /api/permissions`、`GET /api/permissions`。
- 新增操作稽核與交易事件帳：`audit_logs`、`trade_events`，涵蓋交易/帳戶增修刪與匯入覆蓋等操作。
- 新增高風險操作確認機制：刪除交易/帳戶需 `X-Confirm: YES`；`/api/trades/import` 覆蓋匯入需 `confirm=YES`。
- 新增備份還原腳本：`scripts/backup_restore.sh`（backup/list/restore）。
- 新增驗收操作手冊：`reports/操作測試手冊_明早執行.md`。
- 新增隔離測試案例：`tests/test_auth.py` 驗證不同 Firebase UID 之資料互相隔離。

### Changed
- 前端頁首 UI 重構為 `hero-controls` / `hero-session-actions`，新增固定顯示的目前登入者 badge。
- `auth.js` 改善 redirect guard 過期與殘留處理，降低登入導向循環。
- 靜態資源回應加上 `Cache-Control: no-store` 等 header，避免舊 JS/CSS 快取造成登入異常。
- Linux 啟動腳本 `run.sh` 改為優先使用專案 `.venv/bin/python` 啟動。
- `accounts` 與多項資料表加入 migration 與唯一鍵重建邏輯，兼容既有資料升級。

### Fixed
- 修正未帶授權或 token 失效時前端導向行為，避免卡在非登入頁。
- 修正刪除高風險動作缺乏二次確認的風險。

## [v0.2.0] - 2026-04-22

### Added
- 支援 Linux 啟動腳本 `run.sh`。
- 新增 `systemd` 範例檔 `stock-journal.service.example`。
- 新增 Linux 實際部署指南 `docs/linux-deployment.md`。

### Changed
- `server.py` 支援以環境變數設定 `STOCK_APP_HOST` 與 `STOCK_APP_PORT`。
- README 補充 Windows / Linux 雙平台啟動說明與 Linux 常駐執行說明。

### Fixed
- 修正 WSL / 舊版 Python 環境缺少 `zoneinfo` 模組時無法啟動的問題。
- 移除 `str.removeprefix()` 依賴，提升較舊 Python 版本相容性。

## [v0.1.0] - 2026-04-22

### Added
- 建立交易頁，支援股票買賣紀錄的新增、編輯、刪除。
- 支援多帳戶欄位、帳戶切換與帳戶管理。
- 建立庫存頁，顯示庫存數量、平均價、庫存成本、市值、未實現損益與可賣價。
- 支援批次設定可賣價，並可只套用尚未設定可賣價的股票。
- 建立股利頁，支援官方 ETF 股利同步、跨行扣款、實領計算。
- 支援手動新增、編輯、刪除歷史股利資料，並可指定帳戶、單位數、股價、殖利率。
- 建立股利統計頁，可依帳戶與多年份查看個股殖利率加總與實領股利加總。
- 建立股利月曆頁，可依單一年份查看每檔個股的每月實領股利分布。
- 支援交易頁、股利頁、股利統計頁的表頭排序。
- 建立 Python + SQLite 正式版本機 web 系統架構。
- 加入 JSON 匯入 / 匯出。
- 建立公開 GitHub repo 與版本標籤 `v0.1.0`。

### Changed
- 將原本以前端 `localStorage` 為主的版本升級為後端 API + SQLite 儲存。
- 股利頁改為頁面訊息條提示，不再使用瀏覽器原生 alert。
- 官方股利同步邏輯改為保留既有中文股名顯示，避免列表被英文名稱覆蓋。
- 當同帳戶、同股號、同除息日 / 發放日已有手動股利時，手動紀錄優先顯示。

### Fixed
- 修正交易編輯後 `取消編輯` 提示未消失的問題。
- 修正 `/favicon.ico` 缺失造成的錯誤記錄。
- 修正手動股利未綁定帳戶，導致新增 / 刪除會影響多帳戶的問題。
- 修正股利同步可能因官方重複資料造成 SQLite 唯一鍵衝突的問題。
- 修正錯誤股利重複列與名稱覆蓋問題。
