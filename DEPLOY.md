# 部署指南：讓專題上線、可以被搜尋、可以裝到手機

目標架構（全免費層即可運作）：

```
手機 / 瀏覽器
   │  HTTPS
   ▼
前端（靜態檔）→ Vercel        https://xxx.vercel.app
   │  HTTPS（VITE_* 指到下面）
   ▼
後端四服務（Docker）→ Render   https://rmn-xxx.onrender.com
   │
   └─ Redis → Render（內部連線）
```

- **HTTPS 自動配好**：瀏覽器 GPS 定位、WebSocket、Web Push、PWA 安裝都要求 HTTPS，這兩個平台預設滿足。
- **git push 即重新部署**：線上版本永遠可以持續修改，不是一次性的。

---

## 前置作業

1. 程式碼推上 GitHub（本分支合併進 dev 後推，或直接推功能分支）。
2. 用 GitHub 帳號分別登入 <https://render.com> 與 <https://vercel.com>（皆免費）。

## 步驟一：Render 部署後端（Blueprint 一鍵）

repo 根目錄的 `render.yaml` 已定義四個服務 + Redis。

1. Render Dashboard → **New +** → **Blueprint** → 選擇本 repo 與分支。
2. Render 會讀取 `render.yaml`，列出 4 個 Web Service + 1 個 Redis。
3. 頁面會要求填 4 個 `CORS_ALLOW_ORIGINS`：**先隨便填一個預留值**（例如 `https://placeholder.example`），等步驟二拿到前端網址後再回來改。
   - `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY`（手機推播用）：在任意機器執行 `npx web-push generate-vapid-keys`，把產生的兩串 key 貼上；留空則只停用 Web Push，其餘功能不受影響。
4. 按 **Apply**，等待建置（每個服務首次約 3–5 分鐘）。
5. 完成後記下四個網址：
   - `https://rmn-location.onrender.com`
   - `https://rmn-event.onrender.com`
   - `https://rmn-notification.onrender.com`
   - `https://rmn-ai.onrender.com`
6. 驗證：瀏覽器開 `https://rmn-location.onrender.com/healthz` 應回 `{"status":"ok"}`。

> 注意：服務名稱全網域共用，若 `rmn-location` 被佔用，Render 會要求改名；
> 改名後記得同步改 `render.yaml` 裡 event-service 的 `NOTIFICATION_SERVICE_URL` / `AI_SERVICE_URL`。

## 步驟二：Vercel 部署前端

1. Vercel Dashboard → **Add New...** → **Project** → Import 本 repo。
2. 設定：
   - **Root Directory**：`web-app`
   - Framework Preset：**Vite**（Build Command `npm run build`、Output Directory `dist` 會自動帶出）
3. **Environment Variables**（Build 時期變數，四個都要）：

   | Name | Value |
   |---|---|
   | `VITE_LOCATION_SERVICE_URL` | `https://rmn-location.onrender.com` |
   | `VITE_EVENT_SERVICE_URL` | `https://rmn-event.onrender.com` |
   | `VITE_NOTIFICATION_WS_URL` | `wss://rmn-notification.onrender.com` |
   | `VITE_NOTIFICATION_SERVICE_URL`* | `https://rmn-notification.onrender.com` |

   \* 若之後做 Web Push 前端訂閱才需要。
4. **Deploy** → 完成後得到 `https://xxx.vercel.app`。
5. 驗證：開啟網址 → 地圖出現 → 允許定位 → 頂部膠囊顯示「即時同步中」與「即時在線 N 人」。

## 步驟三：回 Render 補 CORS

前端網址確定後，到 Render 每個服務 → **Environment** → 把 `CORS_ALLOW_ORIGINS`
改成 `https://xxx.vercel.app`（不含結尾斜線）→ Save，會自動重新部署。
不做這步：瀏覽器會擋掉跨源請求（地圖出得來但事件/推播全掛）。

## 步驟四：手機安裝（PWA）

PWA 三件套（manifest、Service Worker、HTTPS）已內建於前端：

- **Android（Chrome）**：開啟網址 → 網址列右側出現「安裝」提示，或選單 → **加入主畫面/安裝應用程式** → 桌面出現 App 圖示，全螢幕獨立執行。
- **iOS（Safari）**：開啟網址 → **分享按鈕** → **加入主畫面** → 桌面出現圖示。
  - iOS 的限制：推播通知（Web Push）需 iOS 16.4+ 且**必須先「加入主畫面」**，從主畫面開啟才收得到。

## 步驟五：被搜尋到（可選）

1. Google Search Console（<https://search.google.com/search-console>）→ 新增資源 → 貼入 `https://xxx.vercel.app`。
2. 用建議方式驗證所有權（HTML 檔案或 DNS）。
3. 提交 sitemap 或直接「要求建立索引」，通常 2–7 天內可被搜尋。

---

## 免費層的已知限制（demo 前必讀）

| 限制 | 影響 | 對策 |
|---|---|---|
| Render 免費服務 15 分鐘無流量會**休眠** | 再次開啟要等 30–60 秒喚醒 | **報告前 10 分鐘先開一次網頁熱機**；有人使用期間有心跳流量就不會睡 |
| 免費 Redis 容量 25MB | 事件資料量小，足夠 | 定期靠事件 TTL 自動過期，不需清理 |
| 首次建置較慢 | 等 3–5 分鐘 | 耐心 |
| OSM 圖資為外部服務 | 離線時地圖空白 | Service Worker 只快取應用外殼，圖資刻意不快取 |

## 之後怎麼更新線上版本

改完程式碼 → push 到 GitHub → Render 與 Vercel **自動偵測並重新部署**（可在兩邊 Dashboard 看進度）。
不需要任何手動上傳，線上版本永遠可以持續修改。

## 進階選項（若之後想要「真的 K8s」）

想讓「部署在 Kubernetes 上」這件事成為真的，可租一台便宜 VPS（或用 GCP/Oracle 免費額度）
安裝輕量版 K8s（k3s），然後直接：

```bash
kubectl apply -f k8s/
```

本 repo 的 K8s manifests 是現成的，HPA 也是真的。上面的 Render 路線與 k3s 路線擇一即可。
