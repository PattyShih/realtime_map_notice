# 文件導覽

這個資料夾放 `realtime_map_notice` 的補充文件。建議依照下列順序閱讀，會比較容易從專題動機一路理解到實作、測試與 Demo。

## 建議閱讀順序

1. [../readme.md](../readme.md)

   先看專案總覽、使用情境、技術選型與目前狀態。

2. [../system.md](../system.md)

   理解系統元件、API contract、Redis 資料設計、非功能需求與目前限制。

3. [architecture.md](./architecture.md)

   看 Mermaid 架構圖、服務邊界與 Demo 時可說明的技術點。

4. [demo-goals.md](./demo-goals.md)

   看最後 Demo 要證明什麼、成功標準、展示故事線與失敗備案。

5. [realtime-location-requirements.md](./realtime-location-requirements.md)

   看即時性定義、位置更新資料欄位、Redis GEO/last_seen 設計與地圖更新驗收標準。

6. [external-services-and-secrets.md](./external-services-and-secrets.md)

   看地圖服務選型、Google Maps API key、環境變數、CORS 與 secret 管理。

7. [project-plan.md](./project-plan.md)

   看十週計畫、每階段交付物、Demo 腳本、風險與備案。

8. [team-plan.md](./team-plan.md)

   看四位組員的職責、交付內容與 Demo 分工。

9. [ui-ux-guidelines.md](./ui-ux-guidelines.md)

   看 Web App 設計注意事項，包含地圖、插旗、通知、定位與響應式設計。

10. [test-plan.md](./test-plan.md)

   看後端、前端、WebSocket、跨服務整合與 E2E 測試規劃。

11. [../development.md](../development.md)

   看本機開發、API 測試、壓測與 K8s Demo 操作流程。

12. [../k8s/README.md](../k8s/README.md)

   看 Kubernetes 部署、HPA、Pod 容錯與常見問題。

13. [../web-app/README.md](../web-app/README.md)

    看前端專案建議結構、核心元件職責與環境變數。

## 文件用途對照

| 文件 | 適合誰看 | 主要用途 |
|------|----------|----------|
| `readme.md` | 全員、教授 | 快速理解專題做什麼 |
| `system.md` | 後端、資料庫、DevOps | 理解系統元件與 API |
| `docs/architecture.md` | 全員 | 報告與簡報架構圖 |
| `docs/demo-goals.md` | 全員、報告負責人 | 最後 Demo 目標與成功標準 |
| `docs/realtime-location-requirements.md` | 前端、後端、資料庫 | 即時位置更新與地圖資料需求 |
| `docs/external-services-and-secrets.md` | 前端、DevOps | 地圖 API key 與環境變數管理 |
| `docs/project-plan.md` | 全員 | 十週進度與 Demo 管理 |
| `docs/team-plan.md` | 全員 | 四人分工與交付物 |
| `docs/ui-ux-guidelines.md` | 前端 | Web App 設計規格 |
| `docs/test-plan.md` | 前端、後端 | 測試策略與案例 |
| `development.md` | 開發者 | 本機啟動與測試指令 |
| `k8s/README.md` | DevOps | Kubernetes 操作 |
| `web-app/README.md` | 前端 | 前端實作方向 |

## 維護規則

- 文件檔名維持小寫，除子資料夾的 `README.md` 外，根目錄使用 `readme.md`、`development.md`、`system.md`。
- 新增文件時，請同步更新本檔與根目錄 [../readme.md](../readme.md) 的相關文件列表。
- 如果架構、API 或位置資料欄位改動，請同步更新 [../system.md](../system.md)、[architecture.md](./architecture.md)、[realtime-location-requirements.md](./realtime-location-requirements.md) 與 [test-plan.md](./test-plan.md)。
- 如果 Demo 目標或流程改動，請同步更新 [demo-goals.md](./demo-goals.md)、[project-plan.md](./project-plan.md) 與 [../development.md](../development.md)。
