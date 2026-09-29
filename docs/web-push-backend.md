# Web Push 後端設定

Notification Service 已保留 WebSocket 通知，並新增可選的 Web Push 支援。沒有設定 VAPID 金鑰時，WebSocket 仍正常運作，手機推播會停用。

## 啟用 VAPID

先安裝 `pywebpush`（已列在 notification-service requirements）：

```powershell
pip install -r backend/notification-service/requirements.txt
```

在根目錄 `.env` 設定：

```text
VAPID_PUBLIC_KEY=<公開金鑰>
VAPID_PRIVATE_KEY=<私密金鑰>
VAPID_SUBJECT=mailto:admin@example.com
```

私密金鑰不要提交到 Git。Docker Compose 會自動把這三個環境變數傳給 notification-service。

## 後端 API

取得前端註冊 Web Push 所需的公開金鑰：

```text
GET /push/public-key
```

註冊或更新使用者的瀏覽器 subscription：

```text
POST /push-subscriptions/{user_id}
```

取消 subscription：

```text
DELETE /push-subscriptions/{user_id}
```

Request body：

```json
{
  "endpoint": "https://push.example/subscription",
  "keys": {
    "p256dh": "browser-public-key",
    "auth": "browser-auth-key"
  }
}
```

## 推播行為

- `/broadcast/nearby` 仍會照常透過 Redis Pub/Sub 傳送 WebSocket 通知。
- 若使用者有有效 subscription 且 VAPID 已設定，會另外發送 Web Push。
- Web Push 失敗不會讓事件建立失敗。
- 回應中的 `push_delivered_count` 代表成功送出的 subscription 數量。
- 收到 `404` 或 `410` 的失效 subscription 會自動從 Redis 移除。
