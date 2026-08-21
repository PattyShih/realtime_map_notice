# Test Plan

`realtime_map_notice` 的自動化測試規劃。分為前端測試、後端測試、WebSocket 測試與 E2E 測試。

---

## 1. 測試重點（Priority）

這個專案的測試不是追求程式碼涵蓋率，而是要確保 **Demo 核心功能在展示時不會出錯**。以下按照重要性排序：

| 優先級 | 測試重點 | 原因 |
|--------|----------|------|
| P0 | **Redis GEO 附近查詢正確性** | Demo 核心：緊急事件是否正確推播給半徑內使用者。半徑內沒收到或半徑外收到都是重大失敗 |
| P0 | **WebSocket 推播正確送達** | Demo 核心：使用者發布事件後，附近使用者必須即時收到通知 |
| P0 | **位置更新即時性** | 使用者移動後，Redis GEO 與地圖 marker 必須更新，否則 500 公尺推播會用到舊位置 |
| P0 | **CORS 設定** | 前後端不同 origin，沒設 CORS 則 Web App 直接無法使用 |
| P1 | **WebSocket 斷線重連** | 現場 Demo 網路可能不穩，斷線後需自動重連 |
| P1 | **WebSocket 心跳清理** | Ghost connection 佔用資源，可能影響其他使用者的推播 |
| P1 | **API payload 邊界驗證** | latitude/longitude 超出範圍、radius 過小等，後端應正確拒絕 |
| P2 | **Event Service 多副本冪等性** | K8s 多副本時避免重複推播 |
| P2 | **前端 API 錯誤 UI** | API 失敗時前端應顯示提示，不能靜默失敗 |

---

## 2. 前後端分離測試策略

前端與後端各有獨立的測試方式，目的是讓兩個團隊可以平行開發與測試，互不阻塞。

### 2.1 後端測試（back-end）

後端測試**不依賴前端**，直接用 HTTP client 打 API 驗證行為。

**測試範圍：**
- Location Service API（位置更新、附近查詢）
- Event Service API（事件發布、通知推播呼叫）
- Notification Service API（健康檢查、通知發布）
- WebSocket 連線、推播、斷線清理

**Mock 策略：**
- 使用 `httpx.AsyncClient` 直接對 FastAPI 發 request，不需要啟動 uvicorn 程序。
- 使用 `fakeredis` 模擬 Redis，不需要啟動真實 Redis。
- Event Service 對 Notification Service 的 HTTP 呼叫，使用 `httpx.MockTransport` 攔截。

```python
# conftest.py 範例 — 使用 httpx.AsyncClient 直接測試 FastAPI app
# 注意：目前 service 資料夾使用 hyphen 命名（例如 location-service），
# 不能直接用 backend.location_service import；測試時需用 importlib 從檔案載入。
import importlib.util
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


def load_app(service_name: str):
    app_path = Path("backend") / service_name / "app" / "main.py"
    spec = importlib.util.spec_from_file_location(f"{service_name}.main", app_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.app


app = load_app("location-service")


@pytest.fixture
async def location_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

### 2.2 前端測試（front-end）

前端測試**不依賴真實後端**，所有 API 與 WebSocket 使用 mock 替代。這樣 A 成員可以獨立開發前端，不需要等 B/C 完成後端。

**測試範圍：**

| 測試層級 | 工具 | 測試內容 |
|----------|------|----------|
| Component 測試 | Vitest + React Testing Library | 地圖元件渲染、事件表單互動、通知 Banner 顯示/隱藏 |
| API 串接測試 | Vitest + MSW (Mock Service Worker) | 呼叫 Location/Event Service 的 request payload、response 處理 |
| WebSocket mock 測試 | Vitest + 自訂 WS mock | WebSocket 連線、收到通知後 UI 更新、斷線後重連 UI 狀態 |
| E2E 手動測試 | 瀏覽器 DevTools | 真實地圖顯示、瀏覽器定位、完整事件流程 |

**Mock 策略：**

```typescript
// WebSocket mock 範例 — 前端測試使用，不連真實後端
class MockWebSocket {
  private handlers: Record<string, Function[]> = {};

  constructor(url: string) {}

  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;

  send(data: string) {}

  close() {
    this.onclose?.();
  }

  // 測試輔助：模擬伺服器推送通知
  mockReceiveNotification(payload: object) {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }

  // 測試輔助：模擬斷線
  mockDisconnect() {
    this.onclose?.();
  }
}
```

**前端測試目錄結構（建議）：**

```text
web-app/
├── src/
│   ├── components/
│   │   ├── MapView.tsx
│   │   ├── EventForm.tsx
│   │   ├── NotificationBanner.tsx
│   │   └── __tests__/
│   │       ├── MapView.test.tsx
│   │       ├── EventForm.test.tsx
│   │       └── NotificationBanner.test.tsx
│   ├── hooks/
│   │   ├── useWebSocket.ts
│   │   ├── useGeolocation.ts
│   │   └── __tests__/
│   │       ├── useWebSocket.test.ts
│   │       └── useGeolocation.test.ts
│   └── services/
│       ├── api.ts              # HTTP client (Location + Event Service)
│       ├── websocket.ts        # WebSocket client
│       └── __tests__/
│           ├── api.test.ts
│           └── websocket.test.ts
```

### 2.3 前後端對接測試（Integration）

當前後端各自獨立測試通過後，才需要進行對接測試。

**對接測試方式：**
1. 啟動完整 docker-compose（後端三個服務 + Redis）
2. 用瀏覽器或 Postman 手動測試完整資料流
3. 使用瀏覽器 DevTools → Network tab 確認 API request/response
4. 使用瀏覽器 DevTools → Console tab 確認 WebSocket 訊息

**對接測試檢查清單：**

| 檢查項目 | 驗證方式 |
|----------|----------|
| CORS header 正確 | DevTools Network tab 看 Response Headers 有 `Access-Control-Allow-Origin` |
| POST /locations 成功 | DevTools Console 無 CORS error，API 回傳 200 |
| WebSocket 握手成功 | DevTools Network → WS → 狀態是 101 |
| WebSocket 收到通知 | DevTools Network → WS → Messages 有通知 JSON |
| 斷線重連 | 關閉 Wi-Fi 後重新開啟，確認 WS 自動重連 |

---

## 3. 測試案例詳情

### 3.1 後端單元測試

#### `tests/unit/test_schemas.py`

| 測試名稱 | 測試內容 | 預期結果 |
|----------|----------|----------|
| `test_location_update_valid` | 建立合法的 LocationUpdate | 通過 validation |
| `test_location_update_invalid_latitude` | latitude > 90 | 拋出 ValidationError |
| `test_location_update_invalid_longitude` | longitude < -180 | 拋出 ValidationError |
| `test_event_create_valid` | 建立合法的 EventCreate | 通過 validation |
| `test_event_create_minimal` | 只給必填欄位（title, message, lat, lng） | 通過 validation，severity 預設 "info" |
| `test_event_create_invalid_radius` | radius_meters < 50 | 拋出 ValidationError |
| `test_event_notification_all_fields` | 完整 EventNotification | 通過 validation |
| `test_event_notification_no_distance` | distance_meters=None | 通過 validation |

#### `tests/unit/test_config.py`

| 測試名稱 | 測試內容 | 預期結果 |
|----------|----------|----------|
| `test_default_redis_url` | 未設定環境變數時 | 回傳預設值 "redis://localhost:6379/0" |
| `test_custom_redis_url` | 設定 REDIS_URL 環境變數 | 回傳自訂值 |

### 3.2 後端 API 整合測試

#### `tests/integration/test_location_service.py`

| 測試名稱 | 測試內容 | 驗收條件 | 對應重點 |
|----------|----------|----------|----------|
| `test_healthz` | GET /healthz | status 200，回傳 `{"status": "ok"}` | — |
| `test_update_location` | POST /locations 合法座標 | status 200，Redis GEO 有該筆資料 | P0 |
| `test_update_location_twice` | 同一 user_id 更新兩次 | status 200，Redis 只保留最新座標 | P0 |
| `test_update_location_sequence_newer_wins` | 同一 user_id 傳入新舊 sequence | 新位置不被舊 sequence 覆蓋 | P1 |
| `test_last_seen_ttl_created` | POST /locations 後檢查 last_seen | last_seen key 存在且有 TTL | **P0** |
| `test_get_nearby_users` | 在範圍內放入使用者後查詢 nearby | 回傳結果包含該使用者 | **P0** |
| `test_get_nearby_users_no_result` | 查詢遠距離座標 | 回傳空陣列 | P0 |
| `test_get_nearby_default_radius` | 不指定 radius_meters | 使用預設 500m | P1 |
| `test_get_nearby_invalid_params` | latitude 超出範圍 | status 422 | P1 |

#### `tests/integration/test_event_service.py`

| 測試名稱 | 測試內容 | 驗收條件 | 對應重點 |
|----------|----------|----------|----------|
| `test_healthz` | GET /healthz | status 200 | — |
| `test_create_event_with_nearby_users` | 附近有使用者時發布事件 | status 200，delivered_count > 0 | **P0** |
| `test_create_event_no_nearby_users` | 附近無使用者時發布事件 | status 200，delivered_count = 0 | P0 |
| `test_create_event_urgent_severity` | 發布 severity="urgent" 事件 | status 200，事件可建立 | P1 |
| `test_create_event_info_severity` | 發布 severity="info" 事件 | status 200，事件可建立 | P1 |

#### `tests/integration/test_notification_service.py`（REST API）

| 測試名稱 | 測試內容 | 驗收條件 | 對應重點 |
|----------|----------|----------|----------|
| `test_healthz` | GET /healthz | status 200 | — |
| `test_notify_user` | POST /notify/{user_id} 發送通知 | status 200，subscriber_count >= 0 | P0 |

### 3.3 WebSocket 測試（後端）

使用 `httpx.AsyncClient` 搭配 FastAPI 的 WebSocket test session 進行測試，不需真實瀏覽器。

| 測試名稱 | 測試內容 | 驗收條件 | 對應重點 |
|----------|----------|----------|----------|
| `test_websocket_connect` | 連線到 /ws/{user_id} | 連線成功，accept | P0 |
| `test_websocket_receive_notification` | WS 連線後，透過 notify API 推播 | WS 端收到對應的通知 JSON | **P0** |
| `test_websocket_disconnect` | WS 斷線後，後端清理 pubsub | 無殘留 subscription | P1 |
| `test_websocket_multiple_users` | 兩個 user_id 各開 WS，各自推播 | user A 只收到 A 的通知，user B 只收到 B 的 | **P0** |
| `test_websocket_no_cross_talk` | 通知 user A，user B 的 WS 不應收到 | B 的 WS 無訊息 | **P0** |

### 3.4 前端元件測試（建議）

#### `web-app/src/components/__tests__/MapView.test.tsx`

| 測試名稱 | 測試內容 | 驗收條件 |
|----------|----------|----------|
| `renders map container` | 渲染 MapView | 地圖 DOM 元素存在 |
| `shows user marker when location provided` | 傳入座標給 MapView | 地圖上有使用者標記 |
| `updates user marker when location changes` | 傳入新座標 | 使用者 marker 移動到新位置 |
| `shows event markers` | 傳入事件列表 | 每個事件對應一個標記 |
| `moves map to notification event` | 點擊通知的查看位置 | 地圖中心移動到事件座標 |

#### `web-app/src/components/__tests__/NotificationBanner.test.tsx`

| 測試名稱 | 測試內容 | 驗收條件 |
|----------|----------|----------|
| `renders notification content` | 收到通知後渲染 | Banner 顯示事件標題與距離 |
| `dismisses on close` | 點擊關閉按鈕 | Banner 消失 |
| `shows different colors by severity` | urgent vs info | 不同嚴重程度有不同顏色 |

#### `web-app/src/hooks/__tests__/useWebSocket.test.ts`

| 測試名稱 | 測試內容 | 驗收條件 |
|----------|----------|----------|
| `connects on mount` | 元件掛載後建立 WS 連線 | 呼叫 onopen |
| `reconnects on disconnect` | WS 斷線後自動重連 | 重連次數 > 0，間隔遞增 |
| `calls onNotification when message received` | WS 收到通知 JSON | 回呼函式被呼叫，參數為 parsed JSON |

### 3.5 E2E 測試（選項）

#### `tests/e2e/test_full_flow.py`

| 步驟 | 操作 | 驗證 |
|------|------|------|
| 1 | 上傳 user_A 與 user_B 的座標（距離 < 500m） | 兩筆成功 |
| 2 | 發布緊急事件在兩者之間 | status 200 |
| 3 | user_A 的 WebSocket 收到通知 | 通知包含正確 event_id |
| 4 | user_B 的 WebSocket 收到通知 | 通知包含正確 event_id |
| 5 | 上傳 user_C 的座標（距離 > 500m） | 成功 |
| 6 | 發布另一個緊急事件 | status 200 |
| 7 | user_C 的 WebSocket 不應收到通知 | 逾時無訊息 |
| 8 | 更新 user_C 到事件附近，再次發布事件 | user_C 這次收到通知 |

### 3.6 跨服務整合測試（Cross-Service）

前幾節的測試都是單一服務的 API 測試（location-service 單獨測、event-service 單獨測）。但這個專案的 Demo 核心是「三個服務串起來的完整資料流」，跨服務整合測試就是用來驗證這條鏈。

**目標：** 確認 Location Service → Redis → Event Service → Notification Service → WebSocket 這條鏈在真實環境中正確運作。

**運作方式：**

```text
docker compose up -d（啟動真實 Redis + 三個服務）
       │
       ▼
pytest tests/integration/cross_service/（對真實容器發 request）
       │
       ▼
      確認完整資料流正確
```

與 3.2 節「個別 API 測試」的差別：

| | 個別 API 測試（3.2） | 跨服務整合測試（3.6） |
|--|----------------------|----------------------|
| Redis | fakeredis 模擬 | docker-compose 真實 Redis |
| 通知發送 | httpx.MockTransport 攔截 | 真實發送 HTTP POST 到 notification-service |
| WebSocket | ASGITransport 直接測 FastAPI app | 連線到真實 uvicorn 容器 |
| 測試速度 | 快（毫秒級） | 慢（秒級，需等待 docker） |
| 執行時機 | 每次 commit / 開發中頻繁執行 | 合併 PR 前 / Demo 前 |

---

#### 3.6.1 目錄結構

```text
tests/
└── integration/
    └── cross_service/
        ├── conftest.py                    # 跨服務 fixture
        ├── test_location_to_redis.py       # Location → Redis
        ├── test_event_to_notification.py   # Event → Notification (HTTP)
        ├── test_notification_to_websocket.py # Notification → WS
        └── test_full_chain.py              # 完整資料流
```

#### 3.6.2 共用 fixture（`tests/integration/cross_service/conftest.py`）

```python
import pytest
import httpx


@pytest.fixture(scope="session")
def location_url() -> str:
    return "http://localhost:8001"


@pytest.fixture(scope="session")
def event_url() -> str:
    return "http://localhost:8002"


@pytest.fixture(scope="session")
def notification_url() -> str:
    return "http://localhost:8003"


@pytest.fixture
async def location_client(location_url):
    async with httpx.AsyncClient(base_url=location_url) as client:
        yield client


@pytest.fixture
async def event_client(event_url):
    async with httpx.AsyncClient(base_url=event_url) as client:
        yield client
```

> 注意：跨服務測試**不使用** `ASGITransport`，而是透過 HTTP 連到真實的 docker-compose 容器。這樣才能驗證網路層、容器路由、PORT binding 等真實部署行為。

---

#### 3.6.3 `test_location_to_redis.py` — Location Service → Redis 寫入驗證

| 測試名稱 | 操作 | 預期結果 | 對應重點 |
|----------|------|----------|----------|
| `test_write_and_readback` | POST /locations → GET /locations/nearby | 剛寫入的使用者出現在 nearby 結果中 | **P0** |
| `test_write_multiple_users` | 寫入 5 個不同 user_id，範圍內查詢 | 回傳全部 5 個 | P1 |
| `test_write_then_move` | user_id A 從座標 (a) 移動到座標 (b) far away | nearby(a) 不再包含 A；nearby(b) 包含 A | **P0** |
| `test_last_seen_expires` | 寫入 user_id 後等待 TTL 過期 | Event Service 不再推播給該 user_id | P1 |
| `test_concurrent_writes` | 同時寫入 10 個 user_id（asyncio.gather） | 全部成功，nearby 回傳 10 個 | P1 |

**為什麼要測這個：** 這是整個系統的基礎。如果 Location Service 寫入 Redis 有問題，後面 Event Service 的附近查詢必定失敗。

---

#### 3.6.4 `test_event_to_notification.py` — Event Service → Notification Service HTTP 呼叫

| 測試名稱 | 操作 | 預期結果 | 對應重點 |
|----------|------|----------|----------|
| `test_event_triggers_notification` | 先寫入使用者在 Redis，發布事件在附近 | Notification Service 收到 HTTP POST /notify | **P0** |
| `test_event_no_nearby_users` | 發布事件在無人的座標 | Event Service 回傳 delivered_count = 0 | P0 |
| `test_event_multiple_recipients` | 寫入 10 個使用者在附近，發布事件 | delivered_count = 10 | **P0** |
| `test_event_notification_payload` | 檢查通知 payload 內容 | payload 包含 event_id、title、lat、lng、distance | P1 |

**為什麼要測這個：** Event Service 是業務邏輯的核心。它的附近查詢結果是否正確，以及它是否正確呼叫 Notification Service，直接決定推播能不能送到。

---

#### 3.6.5 `test_notification_to_websocket.py` — Notification → WS 推播驗證

| 測試名稱 | 操作 | 預期結果 | 對應重點 |
|----------|------|----------|----------|
| `test_notify_connected_client` | WS 連線後，POST /notify/{user_id} | WS 收到通知 JSON | **P0** |
| `test_notify_unconnected_client` | 無 WS 連線時 POST /notify/{user_id} | subscriber_count = 0，API 仍回 200 | P1 |
| `test_websocket_echo_notification_id` | WS 收到通知後回傳 event_id | 比對前後一致 | P2 |
| `test_multi_websocket_receive` | 兩個 WS 各連不同 user_id，各自推播 | 各自只收到自己的通知 | **P0** |

**為什麼要測這個：** Notification Service 是推播的最後一哩路。WebSocket 連線是否正常、pub/sub 是否正確路由，直接決定使用者能不能收到通知。

---

#### 3.6.6 `test_full_chain.py` — 完整鏈路整合測試

這是最重要的測試：模擬 Demo 的完整流程，從上傳座標到發布事件到 WebSocket 接收通知。

**測試流程：**

```
Step 1: 上傳 user_A 和 user_B 的座標到 Location Service
              │
Step 2: 確認 Redis 可查到兩人在 nearby 500m
              │
Step 3: user_A 和 user_B 各自連線 WebSocket
              │
Step 4: 發布緊急事件在兩人的中間點
              │
Step 5: user_A 和 user_B 的 WebSocket 都收到通知
              │
Step 6: 上傳 user_C 在距離 1000m 外的座標
              │
Step 7: user_C 連線 WebSocket
              │
Step 8: 發布另一個緊急事件
              │
Step 9: user_C 的 WebSocket 不應收到通知（逾時檢查）
```

| 測試名稱 | 測試內容 | 驗收條件 | 對應重點 |
|----------|----------|----------|----------|
| `test_demo_full_flow` | 完整 9 步驟資料流 | 所有步驟通過，P0 功能全部正常 | **P0** |

**程式碼概念：**

```python
import asyncio
import httpx
import pytest


@pytest.mark.asyncio
async def test_demo_full_flow(location_client, event_client):
    # Step 1: 上傳 user_A 與 user_B 座標（距離約 200m）
    user_a = {"user_id": "integ-a", "latitude": 25.0173, "longitude": 121.5397}
    user_b = {"user_id": "integ-b", "latitude": 25.0185, "longitude": 121.5405}
    user_c = {"user_id": "integ-c", "latitude": 25.0500, "longitude": 121.5600}  # 很遠

    for u in [user_a, user_b, user_c]:
        r = await location_client.post("/locations", json=u)
        assert r.status_code == 200

    # Step 2: 確認 nearby 查詢
    r = await location_client.get(
        "/locations/nearby",
        params={"latitude": 25.0179, "longitude": 121.5400, "radius_meters": 500},
    )
    nearby = r.json()["users"]
    assert "integ-a" in nearby
    assert "integ-b" in nearby
    assert "integ-c" not in nearby  # 距離太遠

    # Step 3-5: WebSocket 驗證需另外處理（見下方說明）
    # ...

    # Step 6-9: user_C 不應收到通知
    # ...
```

**WebSocket 測試的特殊處理：**

WebSocket 測試與一般 HTTP API 測試不同，因為：
1. WebSocket 是 persistent connection，需要保持連線一段時間等待推播
2. 需要同時管理 HTTP client 和 WebSocket connection
3. 需要處理 timeout（確認「不該收到通知」的使用者確實沒收到）

```python
async def _connect_ws(user_id: str) -> tuple:
    """連線到 notification-service 的 WebSocket，回傳 (reader, writer)"""
    # 使用 websockets 套件；httpx 本身不支援 WebSocket client。
    pass


async def _wait_for_notification(ws, timeout: float = 5.0) -> dict | None:
    """等待 WS 訊息，timeout 後回傳 None"""
    try:
        data = await asyncio.wait_for(ws.receive(), timeout=timeout)
        return json.loads(data)
    except asyncio.TimeoutError:
        return None
```

---

#### 3.6.7 跨服務整合測試執行方式

跨服務測試需要先啟動 docker-compose，然後對真實容器執行測試。

```powershell
# Step 1: 啟動所有服務
docker compose up -d --build

# Step 2: 等待服務就緒（healthz 檢查）
echo "Waiting for services..."
$ready = $false
while (-not $ready) {
    try {
        $r = Invoke-RestMethod http://localhost:8001/healthz
        $r = Invoke-RestMethod http://localhost:8002/healthz
        $r = Invoke-RestMethod http://localhost:8003/healthz
        $ready = $true
    } catch {
        Start-Sleep -Seconds 2
    }
}
echo "All services ready."

# Step 3: 執行跨服務整合測試
pytest tests/integration/cross_service/ -v --timeout=30

# Step 4: 清理
docker compose down
```

也可以使用 `pytest-docker` 套件自動管理 docker-compose 生命週期：

```python
# conftest.py（使用 pytest-docker）
import pytest


@pytest.fixture(scope="session")
def docker_compose_files(pytestconfig):
    return ["docker-compose.yml"]


@pytest.fixture(scope="session")
def docker_services(docker_compose_files):
    """啟動 docker-compose，等待服務就緒後執行測試，結束後自動 down"""
    pass
```

**執行腳本建議儲存在 `scripts/run-integration-tests.ps1`：**

```powershell
# scripts/run-integration-tests.ps1
Write-Host "=== Starting integration test environment ==="
docker compose up -d --build

Write-Host "=== Waiting for services ==="
do {
    $r1 = try { (Invoke-WebRequest -Uri http://localhost:8001/healthz -TimeoutSec 2).StatusCode } catch { 0 }
    $r2 = try { (Invoke-WebRequest -Uri http://localhost:8002/healthz -TimeoutSec 2).StatusCode } catch { 0 }
    $r3 = try { (Invoke-WebRequest -Uri http://localhost:8003/healthz -TimeoutSec 2).StatusCode } catch { 0 }
} while ($r1 -ne 200 -or $r2 -ne 200 -or $r3 -ne 200)

Write-Host "=== Running cross-service integration tests ==="
pytest tests/integration/cross_service/ -v --timeout=30
$exitCode = $LASTEXITCODE

Write-Host "=== Cleaning up ==="
docker compose down

exit $exitCode
```

---

#### 3.6.8 跨服務測試 vs 個別 API 測試 — 何時用哪個？

| 情境 | 用哪個 | 原因 |
|------|--------|------|
| 開發中頻繁修改 API | 個別 API 測試（3.2） | 快速反饋，毫秒級 |
| 修改 Redis key 格式 | 個別 + 跨服務 | 個別快速驗證語法，跨服務確認真實 Redis 行為 |
| 修改 Event Service 通知邏輯 | 跨服務 | 需要驗證跟 Notification Service 的 HTTP 溝通 |
| 調整 docker-compose 或 Dockerfile | 跨服務 | 跨服務測試用真實容器，可抓到 Docker 層問題 |
| Demo 前一天 | **跨服務 + E2E** | 確認所有容器、API、WebSocket 在真實環境正常 |
| CI pipeline | 個別（無 docker） | CI 不一定有 docker 環境 |

---

## 4. 測試執行

### 安裝測試依賴

```powershell
pip install -r tests/requirements-test.txt
```

### 執行後端測試

```powershell
# 單元測試（快速，不需 docker）
pytest tests/unit/ -v

# 個別 API 整合測試（需 fakeredis，不需 docker）
pytest tests/integration/ -v

# 跨服務整合測試（需要 docker-compose）
.\scripts\run-integration-tests.ps1

# 全部後端測試
pytest tests/unit/ tests/integration/ -v
```

### 執行前端測試

```powershell
cd web-app
npm install
npm test          # Vitest
npm run test:ui   # Vitest UI mode（選擇性）
```

### 測試涵蓋率報告

```powershell
# 後端
pytest --cov=backend --cov-report=term-missing

# 前端
cd web-app && npm run test -- --coverage
```

---

## 5. 測試依賴

### 後端（`tests/requirements-test.txt`）

```text
pytest==8.3.4
pytest-asyncio==0.25.0
pytest-cov==6.0.0
pytest-timeout==2.3.1
httpx==0.28.1
fakeredis[lua]==2.26.1
websockets==14.1
```

### 前端（`web-app/package.json` devDependencies）

```json
{
  "devDependencies": {
    "vitest": "^3.0.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "jsdom": "^25.0.0",
    "msw": "^2.0.0"
  }
}
```

---

## 6. 撰寫規範

- 所有測試檔案以 `test_` 開頭（後端）或 `.test.tsx` 結尾（前端）。
- 測試函式名稱使用 `snake_case`（後端）或 `camelCase`（前端），名稱應描述測試情境（如 `test_get_nearby_users`、`reconnectsOnDisconnect`）。
- 每個測試只測試一個行為，一個 `it` / `test` 只做一個 assertion。
- 後端非同步測試使用 `async def`，並標註 `@pytest.mark.asyncio`。
- 前端測試使用 `describe` + `it` 結構，每個情境一個 `describe`。

---

## 7. 常見問題

### Q: 前端開發時後端還沒好怎麼辦？

A: 前端使用 MSW (Mock Service Worker) 攔截所有 API 請求，回傳假資料。WebSocket 使用自訂 mock class（見 2.2 節）。前端開發完全不需要後端啟動。

### Q: 後端測試時需要啟動所有服務嗎？

A: 不需要。使用 FastAPI 的 `ASGITransport` 可以直接測試 app 物件（見 2.1 節），不需要啟動 uvicorn。Redis 使用 fakeredis 模擬。

### Q: E2E 測試一定要寫嗎？

A: 不一定。E2E 測試是選項，時間不夠可以只做手動測試。重點是把 P0 的後端 API 測試和 WebSocket 測試先寫好。
