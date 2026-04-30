# v0.3.1 部署升級注意事項（DB migration / owner_uid）

本文提供 `stock-journal` 升級到 `v0.3.1` 的重點檢查清單，特別針對資料庫 migration 與 `owner_uid` 隔離機制。

## 1. 升級前準備

1. 停止服務（systemd 或手動執行中的 `server.py`）。
2. 備份資料庫：

```bash
cd /path/to/stock-journal
./scripts/backup_restore.sh backup
```

3. 確認備份檔與校驗檔已產生於 `backups/`。

## 2. 程式版本升級

```bash
git fetch --tags origin
git checkout main
git pull --ff-only origin main
git checkout v0.3.1
```

若正式環境以 `main` 跑服務，也可直接 `git pull --ff-only origin main` 後重啟。

## 3. 啟動方式（建議）

`v0.3.1` 的 `run.sh` 已改為使用專案虛擬環境 Python：

```bash
./run.sh
```

請先確認 `.venv` 已存在且含必要套件（如 `firebase-admin`）。

## 4. migration 內容（自動執行）

服務啟動時 `ensure_database()` 會自動做以下動作：

- 在核心表加入 `owner_uid`（含舊資料相容預設 `__legacy__`）
  - `accounts`
  - `trades`
  - `holding_targets`
  - `dividend_manual_events`
  - `dividend_adjustments`
- 重建 `accounts` 唯一鍵邏輯為 `UNIQUE(owner_uid, name)`。
- 清理可能重複資料並建立唯一索引：
  - `holding_targets(owner_uid, account, symbol)`
  - `dividend_adjustments(owner_uid, account, symbol, ex_dividend_date, payment_date)`
- 新增稽核/協作資料表：
  - `user_permissions`
  - `audit_logs`
  - `trade_events`

> 注意：migration 在啟動時執行，首次升級可能比平常啟動稍慢。

## 5. 升級後驗證

### 5.1 基本健康檢查

- 可開啟登入頁並完成 Google 登入。
- 交易頁、庫存頁、股利頁可正常載入。

### 5.2 多使用者隔離檢查（owner_uid）

- A 帳號新增帳戶/交易。
- 切換 B 帳號後確認看不到 A 的帳戶/交易。
- B 新增資料後，回 A 帳號確認也看不到 B 的資料。

### 5.3 高風險防呆

- 刪除交易/帳戶若未帶 `X-Confirm: YES` 應失敗。
- `/api/trades/import` 若未帶 `confirm=YES` 應失敗。

### 5.4 稽核與事件

- 執行新增/修改/刪除交易後，確認 `audit_logs` 與 `trade_events` 有紀錄。

## 6. 回滾方式

若升級後需回滾：

1. 停止服務。
2. 還原 DB：

```bash
./scripts/backup_restore.sh restore backups/stock_journal_YYYYMMDD_HHMMSS.sqlite3
```

3. 切回舊版程式碼並重啟。

## 7. 備註

- 建議先在 staging 或本機副本演練一次 migration。
- 若正式環境資料量大，請安排低流量時段執行升級。
