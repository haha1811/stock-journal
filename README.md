# 股票交易紀錄台

這版已升級成正式的本機 web 系統，採用：

- 前端：`HTML + CSS + JavaScript`
- 後端：`Python 3.11`
- 資料庫：`SQLite`

交易資料不再只存在瀏覽器，而是寫入本機資料庫 `data/stock-records.sqlite3`。

## 執行環境

- Python：建議 `3.11+`
- 作業系統：`Windows`、`Linux`
- 主要依賴：Python 標準函式庫（目前不需額外安裝第三方套件）
- Google OAuth：SaaS 登入版需要設定 `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`REDIRECT_URI`

## 目前功能

- Google 帳號登入驗證，驗證成功後才可使用系統
- 可用 email allowlist 或 Google Workspace 網域限制使用者
- 新增 / 編輯 / 刪除買賣交易
- 多帳戶欄位與帳戶切換
- 帳戶管理頁面
- 庫存頁
- 股利頁
- 股利統計頁
- 股利月曆頁
- 自動計算成交金額
- 賣出時自動帶出交易稅（`0.3%`）
- 顯示買入總額、賣出總額、買賣差、總成本
- 依年份篩選
- 依股票代號或名稱搜尋
- 匯出 / 匯入 JSON 備份
- 透過 SQLite 永久保存資料

## 多帳戶使用方式

- 左側表單新增交易時，可直接填入 `帳戶`
- 右側總覽可用 `帳戶切換` 篩選指定帳戶的資料
- 舊資料若沒有帳戶欄位，系統會自動補成 `主帳戶`

## 帳戶管理

- 點上方 `帳戶管理` 按鈕可展開帳戶管理區
- 可新增帳戶、修改帳戶名稱、刪除未使用的帳戶
- 若帳戶底下仍有交易資料，系統會阻止刪除

## 庫存頁

- 交易頁上方可切換到 `庫存頁`
- 庫存頁會依交易資料自動計算目前仍持有的庫存
- 顯示帳戶、股號、股名、庫存數量、平均價、庫存成本、市值、未實現損益
- 可設定每檔庫存的 `可賣價` 與備註
- 可用百分比一鍵批次更新目前篩選中的 `可賣價`
- 批次更新時可選擇「只套用尚未設定可賣價的股票」
- 當最新更新價 `>=` 可賣價時，該列會以不同底色提示
- 股價欄位使用盤後公開資料，會在每天 15:00 後自動更新，也可手動更新一次

## 股利頁

- 交易頁與庫存頁上方可切換到 `股利頁`
- 目前同步來源為 TWSE 公開 ETF 配息清單
- 系統每日同步一次最新配息公告，也可手動刷新
- 若未到除息日前官方公告變更，系統下次同步時會更新資料
- 可手動輸入每筆股利的 `跨行扣款`
- `實領` 會依 `金額(合計) - 跨行扣款` 自動計算
- 可手動新增、修改、刪除歷史股利資料

## 股利統計頁

- 可依 `帳戶` 查看股利統計
- 預設顯示今年的股利統計
- 可手動多選多個年份，也可一鍵 `全選`
- 會依 `帳戶 + 個股` 彙總 `殖利率加總` 與 `股利金額加總`
- `股利金額加總` 使用股利頁中的 `實領` 金額
- 可設定高亮門檻百分比，例如 `6%`
- 當某檔股票的 `殖利率加總 >= 門檻` 時，會以不同顏色提示

## 股利月曆頁

- 可用 `年份單選` 查看單一年度每月股利分布
- 月份以 `發放日` 為準
- 金額使用股利頁中的 `實領`
- 顯示每檔個股在 `1~12 月` 的實領金額與全年總計
- 最下方會顯示 `每月總計` 與 `年度總計`
- 可切換帳戶，也可選擇 `隱藏全年為 0 的個股`

## 啟動方式

### Windows

1. 進入專案資料夾：

```powershell
cd d:\Downloads\tmp\VibeCoding\stock
```

2. 啟動後端服務：

```powershell
python server.py
```

3. 開啟瀏覽器進入：

```text
http://127.0.0.1:8000
```

### Linux

1. 進入專案資料夾：

```bash
cd /opt/stock-journal
```

2. 啟動後端服務：

```bash
python3 server.py
```

或使用內建啟動腳本：

```bash
chmod +x run.sh
./run.sh
```

3. 開啟瀏覽器進入：

```text
http://127.0.0.1:8000
```

若要讓同網段其他裝置可連線，可改用：

```bash
STOCK_APP_HOST=0.0.0.0 STOCK_APP_PORT=8000 python3 server.py
```

## 環境變數

### 服務綁定

- `STOCK_APP_HOST`
  - 預設：`127.0.0.1`
  - 範例：`0.0.0.0`
- `STOCK_APP_PORT`
  - 預設：`8000`
  - 範例：`8080`

### Firebase Auth（Google Sign-In）

可複製 `.env.example` 成 `.env`；`server.py` 會自動讀取專案根目錄的 `.env`。

前端（可公開）必填：

- `FIREBASE_API_KEY`
- `FIREBASE_AUTH_DOMAIN`
- `FIREBASE_PROJECT_ID`
- `FIREBASE_APP_ID`

前端（可公開）選填：

- `FIREBASE_STORAGE_BUCKET`
- `FIREBASE_MESSAGING_SENDER_ID`

後端（不可公開）必填其一：

- `FIREBASE_SERVICE_ACCOUNT_JSON`（Service Account JSON 檔案路徑）
- 或使用主機上的 `GOOGLE_APPLICATION_CREDENTIALS` / GCP ADC

相容保留（Phase A，舊 Google OAuth callback/session 流程）：

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `REDIRECT_URI`

其他選填：

- `STOCK_ALLOWED_GOOGLE_EMAILS`：逗號分隔 email allowlist，例如 `user1@gmail.com,user2@gmail.com`。
- `STOCK_ALLOWED_GOOGLE_DOMAIN`：限制 Google Workspace 網域，例如 `example.com`。
- `STOCK_COOKIE_SECURE`：正式 HTTPS 部署建議設為 `true`，讓 session cookie 加上 `Secure`。

## Firebase Auth 設定與測試（Phase A MVP）

1. 到 Firebase Console 啟用 Authentication → Sign-in method → Google。
2. 在 Project settings 取得 Web App config，填入 `.env` 的 `FIREBASE_*` 欄位。
3. 在後端主機配置 Admin SDK 憑證：
   - 建議使用 `FIREBASE_SERVICE_ACCOUNT_JSON=/abs/path/service-account.json`
   - 憑證檔不可 commit
4. 安裝後端驗證套件：

```bash
python3 -m pip install firebase-admin
```

5. 啟動 server：

```bash
python3 server.py
```

6. 測試流程：開啟 `http://localhost:8000/login.html` → 點 `Log in with Google` → 成功後導回 `/`。前端會將 Firebase ID Token 存到 localStorage，並由 `firebase-auth-bridge.js` 自動在 `/api/*` 請求加上 `Authorization: Bearer <token>`。

7. 完整 smoke test 檢查清單請參考：

- [`docs/oauth-smoke-test-checklist.md`](./docs/oauth-smoke-test-checklist.md)

## API 概念

- `GET /api/trades`：讀取全部交易
- `POST /api/trades`：新增交易
- `PUT /api/trades/{id}`：更新交易
- `DELETE /api/trades/{id}`：刪除交易
- `POST /api/trades/import`：整批匯入 JSON

## 資料庫位置

- SQLite 檔案：`data/stock-records.sqlite3`

## Linux 常駐執行

- 已提供 `stock-journal.service.example`
- 可放到 `/etc/systemd/system/stock-journal.service`
- 再依你的 Linux 帳號、專案路徑調整：
  - `WorkingDirectory`
  - `ExecStart`
  - `User`
  - `Group`
- 實際部署步驟可參考：
  - [docs/linux-deployment.md](./docs/linux-deployment.md)

## 後續可再擴充

- 匯入 Excel / CSV
- 每檔股票持股成本與庫存
- 已實現損益 / 未實現損益
- 配息紀錄
- 多帳戶管理
- 使用者登入與權限
- 雲端部署
