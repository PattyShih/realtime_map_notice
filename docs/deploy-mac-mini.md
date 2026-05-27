# Mac mini 2014 部署指南

## 環境需求

- macOS 10.15+（建議 macOS 11 Big Sur）
- 8GB RAM + SSD ✅
- Docker Desktop for Mac（Intel 版）

## 安裝步驟

### 1. 安裝 Docker Desktop

下載 Intel 版本：https://docs.docker.com/desktop/setup/install/mac-install/

安裝後開啟 Docker Desktop → Settings → Resources：
- **Memory**: 3 GB（夠用了）
- **CPUs**: 2（Mac mini 2014 雙核/四核都可）

### 2. Clone 專案

```bash
git clone -b dev_hermes https://github.com/brianshih04/realtime_map_notice.git
cd realtime_map_notice
```

### 3. 啟動所有服務

```bash
docker compose up --build -d
```

首次 build 約 3–5 分鐘（SSD 會快很多），之後啟動只需幾秒。

### 4. 驗證服務

```bash
# 檢查所有容器狀態
docker compose ps

# 健康檢查
curl http://localhost:8001/healthz
curl http://localhost:8002/healthz
curl http://localhost:8003/healthz

# 查詢事件列表
curl http://localhost:8002/api/event/events
```

### 5. 開啟網頁

瀏覽器打開：

```
http://localhost:8095
```

即可使用。

## Mac mini 效能建議

docker-compose.yml 不需修改，預設配置即可：

- Location Service: 4 workers（Mac mini 能吃滿雙核）
- Event Service: 4 workers
- Notification Service: 1 worker
- 總記憶體佔用 ~470MB

如果覺得風扇太吵（Mac mini 2014 散熱偏弱），可以把 workers 降到 2：

```yaml
# docker-compose.yml 中修改
location-service:
  environment:
    WORKERS: "2"
event-service:
  environment:
    WORKERS: "2"
```

## 常用指令

```bash
# 啟動
docker compose up -d

# 停止
docker compose down

# 查看日誌
docker compose logs -f

# 重新 build（改過程式碼後）
docker compose up --build -d

# 壓力測試（200人）
python3 stress_test.py --users 200
```

## 注意事項

- Docker Desktop for Mac 用的是 Linux VM，效能比原生 Linux 稍慢（約打 7–8 折）
- 200 人壓測沒問題，500 人可能開始吃緊
- 不需要 Cloudflare Tunnel（本機測試用 localhost 即可）
- 瀏覽器 Geolocation API 在 localhost 下需要 HTTPS 才能使用，可改用手動選點
