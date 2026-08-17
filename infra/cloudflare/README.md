# Cloudflare Public Entry

本目錄放 `realtime_map_notice` 對外展示入口的設定骨架。目標是使用既有 Cloudflare zone `avision-gb10.org`，建立專案子網域：

```text
https://map.avision-gb10.org
```

## 對外路由

```text
https://map.avision-gb10.org/                  -> Web App static files
https://map.avision-gb10.org/api/location/...  -> Location Service
https://map.avision-gb10.org/api/events/...    -> Event Service
wss://map.avision-gb10.org/ws/{user_id}        -> Notification Service WebSocket
```

## 架構

```text
Browser
  -> Cloudflare DNS / HTTPS / WAF
  -> Cloudflare Tunnel
  -> edge-proxy nginx
      -> Web App static files
      -> location-service:8000
      -> event-service:8000
      -> notification-service:8000
```

這樣前端只需要設定單一公開網域，不需要讓使用者記住 `8001`、`8002`、`8003`。

## 檔案

| 檔案 | 用途 |
|------|------|
| `nginx.conf` | edge proxy 路由設定，負責靜態檔與 API/WebSocket 分流 |
| `cloudflared/config.example.yml` | Cloudflare Tunnel 設定範本，不包含 tunnel ID 或 credentials |
| `../../docker-compose.cloudflare.yml` | 本機展示用 compose，啟動 edge proxy 與 cloudflared |
| `../../web-app/.env.cloudflare.example` | 前端正式網域環境變數範本 |

## 前置需求

- `avision-gb10.org` 已在 Cloudflare 管理。
- 建立 Cloudflare Tunnel，並將 public hostname 指到 `map.avision-gb10.org`。
- Tunnel origin 指到 edge proxy：`http://edge-proxy:8080`（compose 內）或 `http://localhost:8080`（本機 cloudflared）。
- WebSockets 需在 Cloudflare Network settings 保持啟用。

## 本機展示流程

1. 建立 Web App production build：

```powershell
.\scripts\cloudflare-build-web.ps1
```

2. 複製 cloudflared config 範本並填入 tunnel 資訊：

```powershell
Copy-Item infra\cloudflare\cloudflared\config.example.yml infra\cloudflare\cloudflared\config.yml
```

3. 放入 Cloudflare Tunnel credentials JSON。

不要把 `config.yml` 或 credentials JSON commit 到 GitHub。

4. 啟動完整展示環境：

```powershell
docker compose -f docker-compose.yml -f docker-compose.cloudflare.yml --profile cloudflare up --build
```

5. 驗證：

```powershell
Invoke-WebRequest https://map.avision-gb10.org/ -UseBasicParsing
Invoke-RestMethod https://map.avision-gb10.org/api/location/healthz
Invoke-RestMethod https://map.avision-gb10.org/api/events/healthz
```

WebSocket 驗證：

```text
wss://map.avision-gb10.org/ws/u-demo
```

## 使用 Tunnel Token 啟動

如果 Cloudflare Dashboard 已經建立好 Tunnel 與 public hostname，可以把 tunnel token 存到本機環境變數，再用 token 啟動 `cloudflared`：

```powershell
[Environment]::SetEnvironmentVariable("CLOUDFLARE_TUNNEL_TOKEN", "<paste-token-here>", "User")
```

重新開啟 PowerShell 後執行：

```powershell
.\scripts\cloudflare-build-web.ps1
.\scripts\cloudflare-start-tunnel-token.ps1
```

這個腳本會用 Docker Compose 啟動 Redis、三個後端服務、`edge-proxy` 與 `cloudflared-token`。`cloudflared-token` 會和 `edge-proxy` 位於同一個 Docker network，因此 Tunnel 的 public hostname 服務目標可設定成：

```text
http://edge-proxy:8080
```

若 DNS 沒有自動建立，請在 `avision-gb10.org` zone 補一筆 proxied CNAME：

```text
map -> <tunnel-id>.cfargotunnel.com
```

注意：不要把 token 寫進 repo、commit、issue、文件或聊天紀錄。若 token 已經外流，測完請到 Cloudflare rotate 或 revoke。

若 `map.avision-gb10.org` 仍無法解析，代表 public hostname / DNS record 尚未在 Cloudflare 建立。Tunnel token 只能啟動既有 tunnel，不能替代 DNS/public hostname 設定。

## CORS

正式展示時，三個後端服務需允許：

```text
https://map.avision-gb10.org
```

如果前端與後端都透過同一個 hostname 進出，瀏覽器會視為同源呼叫，CORS 風險會比三個不同 port 低很多；但後端仍保留 `CORS_ALLOW_ORIGINS`，方便本機開發與正式入口並存。
