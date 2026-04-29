# Google OAuth Smoke Test Checklist (MVP)

本清單用於驗證 `feat/google-auth-mvp` 的最小可用登入版本。

## 0) 前置設定

- [ ] 已複製設定檔：`cp .env.example .env`
- [ ] `.env` 已填入：
  - [ ] `GOOGLE_CLIENT_ID`
  - [ ] `GOOGLE_CLIENT_SECRET`
  - [ ] `REDIRECT_URI`
- [ ] Google Cloud Console 已設定 `Authorized redirect URI`，且與 `REDIRECT_URI` **完全一致**
- [ ] `.env` 未被加入 Git（`git status` 不應出現 `.env` staged）

## 1) 啟動檢查

- [ ] 啟動服務：`python3 server.py`
- [ ] `GET /api/health` 回傳 200
- [ ] 開啟 `/login.html` 可看到「Log in with Google」按鈕

## 2) 未登入保護檢查

- [ ] 未登入呼叫 `GET /api/trades` 回傳 401
- [ ] 未登入開啟 `/` 會被導向 `/login.html`

## 3) OAuth 流程檢查

- [ ] 點擊「Log in with Google」後導向 Google 同意頁
- [ ] 同意登入後回到 `/api/auth/google/callback`
- [ ] 成功後導回 `/`（首頁）
- [ ] 回應包含 `Set-Cookie: stock_journal_session=...`

## 4) 使用者資訊檢查

- [ ] `GET /api/auth/me` 回傳 200
- [ ] 回傳內容包含：
  - [ ] `email`
  - [ ] `name`
  - [ ] `picture`

## 5) Session / 登出檢查

- [ ] 呼叫 `POST /api/auth/logout` 回傳 200
- [ ] 回應包含過期 session cookie（清除 cookie）
- [ ] 登出後再次呼叫受保護 API 會回到 401

## 6) 允許名單（選配）

- [ ] 設定 `STOCK_ALLOWED_GOOGLE_EMAILS` 後，未列入名單帳號會被拒絕
- [ ]（或）設定 `STOCK_ALLOWED_GOOGLE_DOMAIN` 後，非指定網域帳號會被拒絕

## 7) 安全檢查

- [ ] 程式碼中沒有寫死 `GOOGLE_CLIENT_SECRET`
- [ ] Git commit 中沒有 `.env` 或任何密鑰
- [ ] 正式 HTTPS 環境已設定 `STOCK_COOKIE_SECURE=true`
