# Linux 部署指南

這份指南提供一個最實用的 Linux 部署方式，適合先把 `stock-journal` 穩定跑在自己的 Linux 主機或 VPS 上。

## 1. 建議環境

- Ubuntu 22.04 / 24.04
- Python `3.11+`
- `git`
- `systemd`
- HTTPS 正式部署建議使用 `caddy` 或其他反向代理

## 2. 安裝必要套件

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git caddy
```

## 3. 下載專案

```bash
cd /opt
sudo git clone https://github.com/haha1811/stock-journal.git
sudo chown -R $USER:$USER /opt/stock-journal
cd /opt/stock-journal
```

## 4. 啟動測試

### 方式 A：直接啟動

```bash
cd /opt/stock-journal
python3 server.py
```

### 方式 B：使用啟動腳本

```bash
cd /opt/stock-journal
chmod +x run.sh
./run.sh
```

預設會綁定：

- `STOCK_APP_HOST=0.0.0.0`
- `STOCK_APP_PORT=8000`

## 5. 進行本機驗證

在主機上執行：

```bash
curl http://127.0.0.1:8000/api/health
```

正常應該回傳：

```json
{"status":"ok"}
```

## 6. 使用 systemd 常駐執行

先建立執行帳號：

```bash
sudo useradd -r -s /usr/sbin/nologin stockjournal
sudo chown -R stockjournal:stockjournal /opt/stock-journal
```

複製 service 檔：

```bash
sudo cp /opt/stock-journal/stock-journal.service.example /etc/systemd/system/stock-journal.service
```

若你的實際路徑不是 `/opt/stock-journal`，請先修改：

- `WorkingDirectory`
- `ExecStart`
- `User`
- `Group`

啟用並啟動：

```bash
sudo systemctl daemon-reload
sudo systemctl enable stock-journal
sudo systemctl start stock-journal
```

查看狀態：

```bash
sudo systemctl status stock-journal
```

查看日誌：

```bash
journalctl -u stock-journal -f
```

## 7. 防火牆與連線

若要讓區網其他裝置連線：

```bash
sudo ufw allow 8000/tcp
```

然後使用：

```text
http://<你的 Linux 主機 IP>:8000
```

## 8. Caddy 反向代理與 Firebase Auth

正式 HTTPS 部署建議使用 Caddy 對外提供 `443`，並將 API 與 Firebase Auth helper 轉發到本服務。`/__/auth/*` 必須在前端 fallback 前處理，否則手機瀏覽器的 Google 登入 redirect 會無法取回 Firebase Auth 結果。

範例 `/etc/caddy/Caddyfile`：

```caddy
your-domain.example {
    encode zstd gzip

    header Cache-Control no-store
    header Pragma no-cache
    header Expires 0

    handle /__/auth/* {
        reverse_proxy 127.0.0.1:8000
    }

    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }

    handle {
        root * /opt/stock-journal
        try_files {path} {path}/ /index.html
        file_server
    }
}
```

`Cache-Control: no-store` 是為了避免瀏覽器沿用舊版 `app.js` 或 `app-helpers.js`。若前端行為已更新，但使用者重新整理後仍看到舊行為，通常要先確認 Caddy 回應前端靜態檔時是否帶有 no-cache/no-store header。

自訂網域使用 Firebase Auth 時，`.env` 建議設定：

```env
FIREBASE_AUTH_DOMAIN=your-domain.example
FIREBASE_AUTH_HELPER_PROXY_ORIGIN=https://your-project-id.firebaseapp.com
```

並在 Google Cloud OAuth Client 的 Authorized redirect URIs 加入：

```text
https://your-domain.example/__/auth/handler
```

修改 Caddyfile 後：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

## 9. 資料保存

資料庫預設位置：

```text
data/stock-records.sqlite3
```

建議定期備份：

```bash
cp /opt/stock-journal/data/stock-records.sqlite3 /opt/stock-journal/data/stock-records.sqlite3.bak
```

## 10. 更新版本

```bash
cd /opt/stock-journal
git pull
sudo systemctl restart stock-journal
```

更新後可用以下指令確認前端靜態檔不會被瀏覽器保留舊版：

```bash
curl -I https://your-domain.example/app.js
```

回應應包含：

```text
Cache-Control: no-store
Pragma: no-cache
Expires: 0
```
