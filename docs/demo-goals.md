# 最後 Demo 目標說明

最後 Demo 的目的不是展示一個完整商業產品，而是證明 `realtime_map_notice` 這個專題具備「即時地圖應用」與「Kubernetes 高併發架構」的核心能力。Demo 應讓教授清楚看到：這不是普通 CRUD 網站，而是一個能處理大量座標更新、即時區域查詢、即時推播與容器自動擴展的系統。

## Demo 核心目標

最後 Demo 要證明五件事：

1. 使用者可以在 Web App 地圖上查看目前位置與附近事件。
2. 使用者可以發布一般事件或緊急事件。
3. 緊急事件只會推播給 500 公尺內的使用者。
4. 系統可以承受大量虛擬使用者持續上傳 GPS 座標。
5. Kubernetes 可以在流量上升或 Pod 故障時維持服務可用。

## Demo 一句話主軸

「當校園中有人發布緊急事件時，系統會即時找出 500 公尺內的使用者並推播通知；同時後端可以透過 Kubernetes 面對大量座標更新與服務故障。」

這句話可以放在簡報第一頁或 Demo 開場，讓觀眾先知道整場展示要看什麼。

## Demo 成功標準

### 產品功能成功標準

- Web App 能顯示地圖與使用者目前位置。
- Web App 能送出事件表單。
- 地圖上能看到事件標記。
- 至少兩個測試使用者可以建立 WebSocket 連線。
- 發布緊急事件後，半徑內使用者收到通知。
- 半徑外使用者不收到通知，或在展示中清楚說明為何不會收到。

### 後端功能成功標準

- Location Service 可以接收連續位置更新。
- Redis GEO 可以查詢 500 公尺內使用者。
- Event Service 可以建立事件並取得附近使用者。
- Notification Service 可以透過 WebSocket 發送通知。
- 服務健康檢查 `/healthz` 正常。

### Kubernetes 成功標準

- `kubectl get pods` 顯示服務正常運行。
- 壓測開始後，Location Service 的 HPA 有擴展跡象，或至少能展示 HPA 設定與 CPU 指標。
- 刪除一個 Notification Service Pod 後，Kubernetes 自動重建 Pod。
- 系統仍可處理新的請求或至少不中斷整個後端環境。

### 報告與展示成功標準

- Demo 能在 8 到 10 分鐘內完成。
- 每位成員都能說明自己的貢獻。
- 教授能清楚理解 Redis GEO、WebSocket、K8s HPA 的角色。
- 若現場環境出問題，仍有截圖或錄影備案可以說明成果。

## Demo 不追求的目標

以下項目不是最後 Demo 的必要成功條件：

- 不需要正式會員註冊與登入。
- 不需要正式上線給真實使用者使用。
- 不需要儲存長期歷史軌跡。
- 不需要原生手機 App。
- 不需要完整商業化 UI。
- 不需要 3,000 人壓測在每台電腦上都穩定跑滿；可用 300 到 1,000 人現場展示，再用 3,000 人設定與截圖補充。

## Demo 推薦故事線

### 第一段：日常使用情境

先展示 Web App 地圖。說明使用者在校園中可以看到附近事件，例如圖書館空位、學餐人潮或活動。

教授應該看到：

- 這是一個地圖導向的應用。
- 使用者不需要在論壇中搜尋資訊。
- 事件與位置直接綁定。

### 第二段：事件插旗

在地圖上新增一般事件，讓事件標記出現在地圖上。

教授應該看到：

- Web App 能和後端 API 溝通。
- 事件資料包含座標、標題、內容與嚴重程度。
- 系統不是靜態畫面，而是有真實資料流。

### 第三段：500 公尺內緊急推播

開啟第二個使用者視窗，建立 WebSocket 連線。發布緊急事件，讓附近使用者收到通知。

教授應該看到：

- 系統會根據座標半徑查詢使用者。
- 通知不是廣播給所有人，而是只推給附近使用者。
- WebSocket 可讓伺服器主動推送通知。

### 第四段：大量座標更新

啟動 Python simulator，模擬大量虛擬使用者持續移動與上傳座標。

教授應該看到：

- 系統的核心壓力來源是高頻位置更新。
- 不需要真的找 3,000 位同學測試。
- 壓測腳本可重現高併發情境。

### 第五段：Kubernetes 自動擴展

使用 `kubectl get hpa -w` 或 `kubectl get pods -w` 展示 Location Service Pod 數量變化。

教授應該看到：

- Location Service 可水平擴展。
- K8s 可以根據資源使用情況增加 Pod。
- 微服務架構能把壓力集中在需要擴展的服務上。

### 第六段：Pod 容錯

刪除一個 Notification Service Pod，觀察 Kubernetes 自動建立新 Pod。

教授應該看到：

- 單一 Pod 故障不代表整個系統停止。
- Kubernetes Deployment / ReplicaSet 會維持期望副本數。
- Service 能提供穩定入口，讓流量導向健康 Pod。

## Demo 時間配置

| 時間 | 內容 | 目標 |
|------|------|------|
| 0:00-0:45 | 專題情境與問題說明 | 讓教授理解為何需要即時區域通知 |
| 0:45-2:00 | Web App 地圖與定位 | 展示產品入口與日常情境 |
| 2:00-3:00 | 新增一般事件 | 展示事件插旗與 API 串接 |
| 3:00-4:30 | 緊急事件 500 公尺推播 | 展示 Redis GEO + WebSocket |
| 4:30-6:00 | 啟動虛擬使用者壓測 | 展示高併發位置更新 |
| 6:00-7:30 | HPA 自動擴展 | 展示 Kubernetes 技術含量 |
| 7:30-8:30 | 刪除 Pod 容錯 | 展示 Kubernetes 自動復原 |
| 8:30-10:00 | 總結與 Q&A | 回扣架構與四人分工 |

## Demo 前必備檢查清單

產品畫面：

- Web App 可開啟。
- 地圖可顯示。
- 定位權限可用，或 fallback 座標可用。
- 事件表單可送出。
- 緊急通知 Banner 可顯示。

後端服務：

- `http://localhost:8001/healthz` 正常。
- `http://localhost:8002/healthz` 正常。
- `http://localhost:8003/healthz` 正常。
- Redis 可連線。
- WebSocket 可連線。

Kubernetes：

- `kubectl -n realtime-map-notice get pods` 正常。
- `kubectl -n realtime-map-notice get hpa` 正常。
- metrics-server 可用。
- port-forward 指令已準備。
- Pod 刪除與自動重建截圖已準備。

壓測：

- `--users 300` 已預演成功。
- `--users 3000` 參數已確認。
- 若 3,000 人跑不動，有 300 或 1,000 人備案。

報告素材：

- 架構圖。
- 資料流圖。
- K8s Pod 狀態截圖。
- HPA 截圖。
- 壓測畫面截圖。
- 四人分工頁面。

## Demo 評分亮點

教授可能會注意的亮點：

- 是否能清楚解釋為什麼使用 Redis GEO。
- 是否能清楚解釋 WebSocket 和一般 HTTP polling 的差異。
- 是否能展示 Kubernetes HPA，而不是只放 YAML。
- 是否能展示 Pod 被刪除後自動恢復。
- 是否能說明 3,000 虛擬使用者如何產生高併發流量。
- 是否能把日常校園情境和後端架構連在一起。

## Demo 失敗備案

如果 Web App 無法啟動：

- 使用 PowerShell API 指令展示 `POST /locations` 與 `POST /events`。
- 使用截圖或錄影展示 Web App 預期畫面。

如果 WebSocket 現場不穩：

- 使用 `POST /notify/{user_id}` 與伺服器 logs 說明通知流程。
- 展示事先錄好的 WebSocket 收到通知畫面。

如果 HPA 沒有擴展：

- 展示 HPA YAML、`kubectl describe hpa` 與 metrics-server 狀態。
- 展示事先截圖，說明現場環境可能因 CPU 指標或本機資源不足而未觸發。

如果 3,000 人壓測使電腦太卡：

- 改用 300 或 1,000 人現場展示。
- 說明腳本參數可調，報告中保留 3,000 人測試設定與截圖。

