# Stock Journal v0.4.0 Release Note

Release title: Mobile-first RWD redesign
Tag: v0.4.0

## 版本重點
v0.4.0 以「手機優先（Mobile-first）」為核心，完成主要前端頁面的響應式重構與 SaaS/App-like 視覺升級，提升手機操作體驗，同時維持既有 Firebase Auth / Google Sign-In 與後端 API 資料流程不變。

## 本版改動

### 1) Mobile-first 響應式重構
- 全站主要頁面改為手機優先排版。
- 平板與桌機自動擴展為多欄布局。
- 縮小手機邊距與卡片間距，提高可讀性與單手操作效率。

### 2) 導覽與操作體驗優化
- 手機版主導覽區改為可橫向滑動（sticky）導覽帶，避免按鈕擠壓。
- 按鈕統一最小可點擊高度（44px），更符合手指點擊情境。
- 維持既有功能入口與主要操作流程。

### 3) 列表/表格手機卡片化
- 交易、庫存、股利、統計與月曆列表在手機下改為卡片式顯示。
- 以 `data-label` 補足欄位語意，確保小螢幕可讀性。
- 降低在窄螢幕強制顯示寬表格所造成的橫向捲動風險。

### 4) 視覺風格升級（SaaS / App-like）
- 更新配色為更現代且乾淨的藍綠系。
- 卡片陰影、圓角、層次與資訊分區一致化。
- 主操作按鈕與次要按鈕對比更清楚。

## 影響範圍
- 主要為前端樣式與模板標記調整（HTML + CSS）。
- 未修改後端 API、資料庫結構與 Firebase 驗證邏輯。

## 相容性與 Breaking Changes
- 後端 API：無 breaking change。
- 資料庫：無 schema 變更。
- 前端：手機版列表呈現方式由傳統寬表格調整為卡片化（屬 UI 呈現升級，非資料或 API 破壞）。

## 測試摘要
- Python 單元測試：`python -m unittest -q` 通過。
- 建議手動驗證：
  - 手機寬度（390 / 430）檢查無橫向捲動。
  - 平板（768）與桌機（>=1280）檢查自動佈局切換。
  - 登入 / 登出 / 受保護 API 存取流程。

## 修改檔案
- `styles.css`
- `index.html`
- `inventory.html`
- `dividends.html`
- `dividend-stats.html`
- `dividend-calendar.html`
