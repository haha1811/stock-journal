# v0.4.1 Release Note (Draft)

Release title: Fix Firebase redirect login and signed-in UI state
Version: v0.4.1

## 摘要
此版本為 v0.4.0 後的 patch 修正，聚焦在 Firebase 登入流程穩定性與登入狀態顯示 UX。

## 內容
- 修正 Firebase redirect login 流程
  - 強化 redirect result / auth state 的處理與驗證流程
  - 改善 token 驗證與跳轉時機，降低登入後卡住或重複跳轉問題

- 修正 HTTPS 443 + 自訂網域下登入設定讀取
  - 修正登入設定讀取與初始化流程，避免 config 讀取異常造成登入失敗

- 修正登入後 UI 顯示「已登入 email」
  - 登入成功並通過 `/api/auth/me` 後，前端狀態明確顯示已登入帳號

- 修正 reload 後不再停在 loading 狀態
  - 有效 token 存在時，頁面重整後不再卡在「登入中」loading 文案
  - 提升已登入使用者的頁面可用性與一致性

## 相容性與資料
- 不含後端 API schema 變更
- 不含資料庫變更

## 建議驗證
1. 在 `https://<custom-domain>/login.html` 執行 Google Sign-In redirect 登入
2. 登入成功後確認可回到主頁且功能正常
3. 確認登入狀態顯示為「已登入：<email>」
4. 重新整理頁面，確認不再顯示卡住的 loading 狀態
5. 登出後再次登入，確認流程穩定
