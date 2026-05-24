# 外部服務與 API Key 規劃

這份文件整理 `realtime_map_notice` 可能需要的外部服務、API key、環境變數與安全注意事項。初期開發建議優先降低外部依賴，避免 Demo 當天因額度、網路或金鑰問題失敗。

## 地圖服務選項

Web App 需要地圖底圖與 marker 顯示。可選方案如下：

| 方案 | 是否需要 API key | 優點 | 注意事項 |
|------|------------------|------|----------|
| Leaflet + OpenStreetMap tiles | 通常不需要 key | 快速、免費、適合專題初期 | 公開 tile server 有使用限制，不適合大量正式流量 |
| MapLibre GL JS + 自架或公開 style | 視 tile/style provider 而定 | 開源、可客製、效能好 | 若使用第三方 tiles 仍可能需要 key |
| Google Maps JavaScript API | 需要 Google Maps API key | 穩定、功能完整、教授熟悉 | 需要 Google Cloud billing、API key 限制與額度控管 |

建議：

- 初期開發：使用 Leaflet + OpenStreetMap，降低 API key 風險。
- 若要展示更完整地圖體驗：改用 Google Maps JavaScript API 或 MapLibre + provider key。
- Demo 前務必確認 API key、網路連線、額度與 domain restriction。

## 可能需要的 API Key

### Google Maps JavaScript API

若前端選用 Google Maps，需要：

```text
VITE_GOOGLE_MAPS_API_KEY=your-google-maps-api-key
```

需要在 Google Cloud Console 啟用：

- Maps JavaScript API
- 可能需要 Geocoding API，若要把地址轉成座標
- 可能需要 Places API，若要搜尋地點

安全設定建議：

- 將 key 限制在特定 HTTP referrers，例如 `localhost:5173`、正式部署網域。
- 只允許專案需要的 API，不要開啟所有 Google Maps APIs。
- 設定 quota 或 budget alert，避免意外費用。
- 不要把真實 key commit 到 GitHub。

### Map provider token

若使用 MapLibre 搭配第三方 tile provider，可能需要：

```text
VITE_MAP_STYLE_URL=https://example.com/style.json
VITE_MAP_PROVIDER_TOKEN=your-provider-token
```

### 後端服務 URL

前端需要知道三個服務的位置：

```text
VITE_LOCATION_SERVICE_URL=http://localhost:8001
VITE_EVENT_SERVICE_URL=http://localhost:8002
VITE_NOTIFICATION_WS_URL=ws://localhost:8003
```

### CORS 設定

後端需要允許前端 dev server origin：

```text
CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:3000
```

正式部署時，必須改成正式網域，不建議長期使用 `*`。

## 建議 `.env` 檔案

前端 `.env.local`：

```text
VITE_LOCATION_SERVICE_URL=http://localhost:8001
VITE_EVENT_SERVICE_URL=http://localhost:8002
VITE_NOTIFICATION_WS_URL=ws://localhost:8003

# Only needed if choosing Google Maps.
VITE_GOOGLE_MAPS_API_KEY=

# Only needed if choosing MapLibre with external provider.
VITE_MAP_STYLE_URL=
VITE_MAP_PROVIDER_TOKEN=
```

後端 `.env`：

```text
REDIS_URL=redis://localhost:6379/0
USER_LOCATION_KEY=realtime_map_notice:user:locations
USER_LAST_SEEN_PREFIX=realtime_map_notice:user:last_seen
DEFAULT_ALERT_RADIUS_METERS=500
CORS_ALLOW_ORIGINS=http://localhost:5173,http://localhost:3000
```

Kubernetes Secret 範例：

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: frontend-map-secrets
  namespace: realtime-map-notice
type: Opaque
stringData:
  VITE_GOOGLE_MAPS_API_KEY: replace-me
```

注意：Vite 的 `VITE_` 變數會被打包到前端，不能放真正需要保密的 server-side secret。Google Maps browser key 本來就是前端會看到的 key，所以必須靠 API restriction 保護。

## Git 安全規則

必須加入 `.gitignore`：

```text
.env
.env.local
.env.*.local
```

本 repo 提供下列範例檔：

```text
.env.example
web-app/.env.example
```

範例檔只放變數名稱與本機預設值，不放真實 key。

## Demo 建議

為了降低 Demo 風險：

- 優先使用不需要 key 的 Leaflet + OpenStreetMap。
- 如果使用 Google Maps，Demo 前一天確認 key 可用。
- 準備一張地圖畫面截圖作為網路或 key 失效備案。
- 不把 API key 寫在簡報截圖、GitHub commit 或公開影片中。
