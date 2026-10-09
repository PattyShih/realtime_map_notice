// Web Push 訂閱：把手機訂閱送給 notification-service，事件發布時收到系統推播
// iOS 限制：需 iOS 16.4+、必須先「加入主畫面」從桌面開啟才可訂閱
import { NOTIFICATION_SERVICE_URL } from './config.js'

export const PUSH_SUPPORTED =
  typeof window !== 'undefined' &&
  'serviceWorker' in navigator &&
  'PushManager' in window &&
  'Notification' in window

export const isStandalone = () =>
  window.matchMedia('(display-mode: standalone)').matches ||
  navigator.standalone === true

export function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  const arr = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i)
  return arr
}

// 目前推播狀態：支援與否、是否已訂閱
export async function getPushState() {
  if (!PUSH_SUPPORTED) return { supported: false, subscribed: false }
  const reg = await navigator.serviceWorker.getRegistration()
  if (!reg) return { supported: true, subscribed: false }
  const sub = await reg.pushManager.getSubscription()
  return { supported: true, subscribed: !!sub }
}

// 完整訂閱流程：權限 → 取公鑰 → 訂閱 → 送後端儲存
export async function enablePush(userId) {
  if (!PUSH_SUPPORTED) throw new Error('此瀏覽器不支援推播')
  if (/iPhone|iPad|iPod/.test(navigator.userAgent) && !isStandalone()) {
    throw new Error('iOS 請先用 Safari「分享 → 加入主畫面」，再從主畫面圖示開啟並啟用推播')
  }
  const perm = await Notification.requestPermission()
  if (perm !== 'granted') throw new Error('尚未允許通知權限')

  const keyRes = await fetch(`${NOTIFICATION_SERVICE_URL}/push/public-key`)
  if (!keyRes.ok) throw new Error('無法取得推播設定')
  const { public_key, configured } = await keyRes.json()
  if (!configured || !public_key) throw new Error('伺服器尚未設定推播金鑰')

  const reg = await navigator.serviceWorker.ready
  let sub = await reg.pushManager.getSubscription()
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(public_key),
    })
  }

  const save = await fetch(
    `${NOTIFICATION_SERVICE_URL}/push-subscriptions/${encodeURIComponent(userId)}`,
    { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(sub.toJSON()) }
  )
  if (!save.ok) throw new Error('訂閱儲存失敗，請稍後再試')
  return true
}

// 取消訂閱：刪除後端紀錄並解除瀏覽器推播訂閱
export async function disablePush(userId) {
  if (!PUSH_SUPPORTED) return false
  const reg = await navigator.serviceWorker.getRegistration()
  const sub = reg && await reg.pushManager.getSubscription()
  if (!sub) return false
  await fetch(
    `${NOTIFICATION_SERVICE_URL}/push-subscriptions/${encodeURIComponent(userId)}`,
    { method: 'DELETE', headers: { 'content-type': 'application/json' }, body: JSON.stringify(sub.toJSON()) }
  ).catch(() => {})
  await sub.unsubscribe()
  return true
}
