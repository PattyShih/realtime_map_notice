# Test Plan

`realtime_map_notice` 的自動化測試規劃。分為單元測試、API 整合測試、WebSocket 測試與 E2E 測試四個層級。

---

## 1. 測試策略

### 測試金字塔

```text
        /\
       /  \         E2E 測試（手動 + 選項）
      /    \
     /------\
    / API    \      API 整合測試（pytest + httpx.AsyncClient）
   /----------\
  /  單元測試   \    單元測試（pytest + fakeredis）
 /--------------\
```

- **單元測試**：測試個別函式邏輯（schema validation、helper function）。不依賴外部服務。
- **API 整合測試**：測試每個服務的 HTTP endpoint。使用 fakeredis 或 docker-compose Redis。
- **WebSocket 測試**：測試 Notification Service 的 WS 連線、斷線、重連行為。
- **E2E 測試**：手動執行，涵蓋完整資料流（Web App → Location Service → Event Service → Notification Service → WebSocket）。

### 測試環境

| 環境 | Redis | 執行方式 | 用途 |
|------|-------|----------|------|
| 單元測試 | fakeredis | `pytest tests/unit/` | CI / 本機快速驗證 |
| 整合測試 | docker-compose Redis | `pytest tests/integration/` | 本機開發驗證 |
| E2E 測試 | docker-compose Redis | 手動執行 | Demo 前完整驗證 |

---

## 2. 目錄結構

```text
realtime_map_notice/
├── tests/
│   ├── conftest.py              # 共用 fixture（async client, redis）
│   ├── requirements-test.txt    # 測試依賴
│   ├── unit/
│   │   ├── test_schemas.py      # schema validation
│   │   └── test_config.py       # 設定讀取
│   ├── integration/
│   │   ├── test_location_service.py
│   │   ├── test_event_service.py
│   │   └── test_notification_service.py
│   └── e2e/
│       └── test_full_flow.py    # 完整資料流（選項）
└── pytest.ini                   # pytest 設定
```

---

## 3. 測試案例詳情

### 3.1 單元測試

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

### 3.2 API 整合測試

#### 共用 fixture（`tests/conftest.py`）

- `redis_client`：建立 fakeredis 或連線到 docker-compose Redis 的 async client。
- `location_client`：httpx.AsyncClient 指向 location-service（base_url = "http://localhost:8001"）。
- `event_client`：httpx.AsyncClient 指向 event-service（base_url = "http://localhost:8002"）。

#### `tests/integration/test_location_service.py`

| 測試名稱 | 測試內容 | 驗收條件 |
|----------|----------|----------|
| `test_healthz` | GET /healthz | status 200，回傳 `{"status": "ok"}` |
| `test_update_location` | POST /locations 合法座標 | status 200，Redis GEO 有該筆資料 |
| `test_update_location_twice` | 同一 user_id 更新兩次 | status 200，Redis 只保留最新座標 |
| `test_get_nearby_users` | 在範圍內放入使用者後查詢 nearby | 回傳結果包含該使用者 |
| `test_get_nearby_users_no_result` | 查詢遠距離座標 | 回傳空陣列 |
| `test_get_nearby_default_radius` | 不指定 radius_meters | 使用預設 500m |
| `test_get_nearby_invalid_params` | latitude 超出範圍 | status 422 |

#### `tests/integration/test_event_service.py`

| 測試名稱 | 測試內容 | 驗收條件 |
|----------|----------|----------|
| `test_healthz` | GET /healthz | status 200 |
| `test_create_event_with_nearby_users` | 附近有使用者時發布事件 | status 200，delivered_count > 0 |
| `test_create_event_no_nearby_users` | 附近無使用者時發布事件 | status 200，delivered_count = 0 |
| `test_create_event_urgent_severity` | 發布 severity="urgent" 事件 | status 200，事件可建立 |
| `test_create_event_info_severity` | 發布 severity="info" 事件 | status 200，事件可建立 |
| `test_create_event_invalid_severity` | severity 不在允許清單 | status 422（若有 enum 驗證） |

#### `tests/integration/test_notification_service.py`

| 測試名稱 | 測試內容 | 驗收條件 |
|----------|----------|----------|
| `test_healthz` | GET /healthz | status 200 |
| `test_notify_user` | POST /notify/{user_id} 發送通知 | status 200，subscriber_count >= 0 |

### 3.3 WebSocket 測試

#### `tests/integration/test_notification_service.py`（延續）

| 測試名稱 | 測試內容 | 驗收條件 |
|----------|----------|----------|
| `test_websocket_connect` | 連線到 /ws/{user_id} | 連線成功，accept |
| `test_websocket_receive_notification` | WS 連線後，透過 notify API 推播 | WS 端收到對應的通知 JSON |
| `test_websocket_disconnect` | WS 斷線後，後端清理 pubsub | 無殘留 subscription |
| `test_websocket_multiple_users` | 兩個 user_id 各開 WS，各自推播 | user A 只收到 A 的通知，user B 只收到 B 的 |
| `test_websocket_no_cross_talk` | 通知 user A，user B 的 WS 不應收到 | B 的 WS 無訊息 |

### 3.4 E2E 測試（選項）

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

---

## 4. 測試執行

### 安裝測試依賴

```powershell
pip install -r tests/requirements-test.txt
```

### 執行單元測試

```powershell
pytest tests/unit/ -v
```

### 執行整合測試（需先啟動 docker-compose）

```powershell
docker compose up -d
pytest tests/integration/ -v
```

### 執行所有測試

```powershell
pytest -v
```

### 測試涵蓋率報告（選擇性）

```powershell
pytest --cov=backend --cov-report=term-missing
```

---

## 5. 測試依賴

`tests/requirements-test.txt` 內容建議：

```text
pytest==8.3.4
pytest-asyncio==0.25.0
pytest-cov==6.0.0
httpx==0.28.1
fakeredis[lua]==2.26.1
```

---

## 6. 撰寫規範

- 所有測試檔案以 `test_` 開頭。
- 測試函式名稱使用 `snake_case`，以 `test_` 開頭，名稱應描述測試情境（如 `test_update_location_twice`）。
- 每個測試只測試一個行為，使用 `assert` 驗證結果。
- 非同步測試使用 `async def`，並標註 `@pytest.mark.asyncio`。
- 整合測試需處理 fixture 的生命週期（setup / teardown）。

