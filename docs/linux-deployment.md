# Linux 部署指南

這份指南提供一個最實用的 Linux 部署方式，適合先把 `stock-journal` 穩定跑在自己的 Linux 主機或 VPS 上。

## 1. 建議環境

- Ubuntu 22.04 / 24.04
- Python `3.11+`
- `git`
- `systemd`

## 2. 安裝必要套件

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git
```

## 3. 下載專案

```bash
cd /opt
sudo git clone https://github.com/haha1811/stock-journal.git
sudo chown -R $USER:$USER /opt/stock-journal
cd /opt/stock-journal
```

若你要測試 Linux 支援分支：

```bash
git checkout feature/linux-support
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

## 8. 反向代理建議

若未來要長期使用，建議前面加一層 `nginx`：

- 可改走 `80` / `443`
- 可加上基本驗證
- 可讓服務管理更穩定

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
