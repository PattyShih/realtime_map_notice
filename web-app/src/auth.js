// Google 登入與 JWT 身分管理
// 流程：Google 按鈕回傳 credential（ID token）→ 後端 /auth/google 驗證
// → 換發系統 JWT → 存 localStorage，之後每個寫入 API 都帶 Authorization
import { EVENT_SERVICE_URL } from './config.js'

const AUTH_KEY = 'rmn_auth'

// Client ID 由 .env.local 的 VITE_GOOGLE_CLIENT_ID 提供（見 web-app/.env.example）
export const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || ''

export function getSavedAuth() {
  try {
    const raw = localStorage.getItem(AUTH_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function saveAuth(auth) {
  localStorage.setItem(AUTH_KEY, JSON.stringify(auth))
}

export function clearAuth() {
  localStorage.removeItem(AUTH_KEY)
}

// 之後的寫入請求（發布/編輯/刪除）都要帶上這組 header
export function authHeaders() {
  const token = getSavedAuth()?.token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// Google Identity Services 回呼：拿 credential 換系統 JWT
export async function loginWithGoogle(credential) {
  const res = await fetch(`${EVENT_SERVICE_URL}/auth/google`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential })
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Google 登入失敗，請再試一次')
  const auth = { token: body.token, user: body.user }
  saveAuth(auth)
  return auth
}
