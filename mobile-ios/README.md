# iOS App 初始雛形

這個資料夾提供 SwiftUI / MapKit 的概念雛形，方便成員 A 開始建立 Xcode 專案。

建議畫面：

- 全螢幕 MapKit 地圖
- 底部 Frosted Glass 事件卡片
- 右上角新增插旗按鈕
- WebSocket 收到 urgent 事件時顯示通知 Banner

API 對接：

- `POST /locations` 每 1 秒上傳目前位置
- `POST /events` 新增校園事件
- `ws://notification-service/ws/{user_id}` 接收附近事件通知

