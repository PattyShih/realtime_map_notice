import { createApp } from 'vue'
import './style.css'
import App from './App.vue'

createApp(App).mount('#app')

// PWA＋推播：都要有 Service Worker。開發版也註冊——sw.js 在 localhost
// 會跳過快取與請求攔截，只提供推播需要的最小註冊，不干擾 Vite HMR
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  })
}
