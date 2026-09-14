// 服務位址設定：優先使用 .env 的 VITE_* 變數，未設定時依當前頁面 origin 推導。
// 本機 Vite dev server、K8s port-forward、反向代理部署都不必改程式碼。
const httpProtocol = window.location.protocol === 'https:' ? 'https:' : 'http:'
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
const host = window.location.hostname

export const LOCATION_SERVICE_URL =
  import.meta.env.VITE_LOCATION_SERVICE_URL || `${httpProtocol}//${host}:8001`

export const EVENT_SERVICE_URL =
  import.meta.env.VITE_EVENT_SERVICE_URL || `${httpProtocol}//${host}:8002`

export const NOTIFICATION_WS_URL =
  import.meta.env.VITE_NOTIFICATION_WS_URL || `${wsProtocol}//${host}:8003`
