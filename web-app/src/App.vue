<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { EVENT_SERVICE_URL, LOCATION_SERVICE_URL, NOTIFICATION_SERVICE_URL, NOTIFICATION_WS_URL } from './config.js'
import { PUSH_SUPPORTED, getPushState, enablePush, disablePush, isStandalone } from './push.js'

// ==========================================
// 地圖核心與狀態
// ==========================================
const DEFAULT_COORDS = { lat: 25.0366, lng: 121.4323 } // 預設座標（輔仁大學）
const map = ref(null)
const radarCircle = ref(null)
const userMarker = ref(null)
const currentCoords = ref({ ...DEFAULT_COORDS })
const locationText = ref('正在取得真實 GPS 座標...')
const eventsList = ref([])
const markerMap = ref(new Map())
// === 事件分類定義（通用版：涵蓋校園日常與街區突發） ===
const CATEGORIES = [
  {
    group: '日常動態 / 活動',
    severity: 'info',
    color: '#34c759',
    tags: ['圖書館空位', '學餐/餐廳空位', '活動/市集/擺攤', '校園/社區宣傳', '二手交流/借用']
  },
  {
    group: '生活即時 / 擁擠',
    severity: 'warning',
    color: '#ff9500',
    tags: ['失物招領', '排隊人潮長', '設施維修/故障', '交通延誤/擁塞', '空間吵鬧/違規']
  },
  {
    group: '緊急突發 / 障礙 (500m推播)',
    severity: 'danger',
    color: '#ff3b30',
    tags: ['道路/通道封閉', '車禍/交通意外', '走失動物/寵物', '天候危害/積水', '突發治安/可疑人士', '火警/瓦斯外洩']
  }
]

// 目前選中的細項標籤（預設選圖書館空位）
const selectedSubCategory = ref('圖書館空位')

// 點選標籤切換
const selectCategoryTag = (tag, severity) => {
  selectedSubCategory.value = tag
  formData.value.category = severity
}
let expirationTimer = null
let locationReportTimer = null
let eventsRefreshTimer = null
let countdownTimer = null
// 剛發布成功的事件 ID：WS 廣播會把自己發的事件再推回來，用來避免重複加入列表與重複跳通知
let lastPublishedEventId = null

const fetchAddress = async (lat, lng) => {
  try {
    const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=18&addressdetails=1`)
    const data = await res.json()
    const readableName = data.address.road || data.address.building || data.address.suburb || data.display_name.split(',')[0]
    locationText.value = readableName ? `目前位置：${readableName}` : `座標：${lat.toFixed(4)}, ${lng.toFixed(4)}`
  } catch (error) {
    locationText.value = `座標：${lat.toFixed(4)}, ${lng.toFixed(4)}`
  }
}

const getDistance = (lat1, lon1, lat2, lon2) => {
  const R = 6371e3
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLon = (lon2 - lon1) * Math.PI / 180
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) + Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.sin(dLon/2) * Math.sin(dLon/2)
  return Math.round(R * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a))))
}

// 使用者定位藍點圖標
const createUserPin = () => {
  return L.divIcon({
    className: 'custom-user-pin',
    html: `
      <div style="
        width: 16px;
        height: 16px;
        background-color: #007aff;
        border: 3px solid #ffffff;
        border-radius: 50%;
        box-shadow: 0 0 8px rgba(0,122,255,0.6);
      "></div>
    `,
    iconSize: [16, 16],
    iconAnchor: [8, 8]
  })
}

const createColoredPin = (category) => {
  const colorMap = { info: '#34c759', warning: '#ffcc00', danger: '#ff3b30' }
  return L.divIcon({
    className: 'custom-pin-container',
    html: `<div class="pin-body" style="background-color: ${colorMap[category] || '#ff7f50'};"></div>`,
    iconSize: [28, 28], iconAnchor: [14, 28], popupAnchor: [0, -24]
  })
}

const getOrCreateUserId = () => {
  let userId = localStorage.getItem('app_user_id')
  if (!userId) {
    userId = 'user_' + Math.random().toString(36).substring(2, 9)
    localStorage.setItem('app_user_id', userId)
  }
  return userId
}

// 本機使用者的身份：列表中 userId 相同的事件顯示編輯/刪除按鈕
const myUserId = getOrCreateUserId()

// ==========================
// 手機推播（Web Push）
// ==========================
const pushState = ref({ supported: PUSH_SUPPORTED, subscribed: false })
const showPushPrompt = ref(false)
const refreshPushState = async () => { pushState.value = await getPushState() }
refreshPushState()

// 從主畫面圖示（standalone）開啟 App 時：若未訂閱且之前沒拒絕過，主動詢問要不要開通知
if (PUSH_SUPPORTED && isStandalone() && !localStorage.getItem('push_prompt_dismissed')) {
  setTimeout(async () => {
    const st = await getPushState()
    pushState.value = st
    if (!st.subscribed) showPushPrompt.value = true
  }, 1500)
}

const onEnablePush = async () => {
  try {
    await enablePush(myUserId)
    await refreshPushState()
    showPushPrompt.value = false
    localStorage.setItem('push_prompt_dismissed', 'enabled')
    triggerToast('🔔 手機推播已啟用')
  } catch (err) {
    triggerToast(err?.message || '推播啟用失敗')
  }
}
const onDisablePush = async () => {
  try {
    await disablePush(myUserId)
    await refreshPushState()
    triggerToast('🔕 手機推播已關閉')
  } catch (err) {
    triggerToast(err?.message || '推播關閉失敗')
  }
}
const dismissPushPrompt = () => {
  showPushPrompt.value = false
  localStorage.setItem('push_prompt_dismissed', 'dismissed')
}

// ==========================================
// 三分頁導覽：戰情摘要（左）／地圖（中）／我的發布（右）
// 底部 tab bar 切換，頁面間支援左右滑動（地圖頁僅接受邊緣滑動，
// 避免與地圖平移手勢衝突）
// ==========================================
const TABS = [
  { id: 'ops', label: '事件', icon: '📊' },
  { id: 'map', label: '地圖', icon: '🗺️' },
  { id: 'mine', label: '我的', icon: '📋' },
]
const TAB_INDEX = { ops: 0, map: 1, mine: 2 }
const activeTab = ref('map')
const trackStyle = computed(() => ({
  transform: `translateX(-${TAB_INDEX[activeTab.value] * 100}vw)`
}))
const switchTab = (id) => {
  if (!TABS.some(t => t.id === id)) return
  activeTab.value = id
}

let touchStart = null
const EDGE_ZONE = 36 // 地圖頁只接受從左右邊緣開始的滑動
const onTouchStart = (e) => {
  const t = e.changedTouches[0]
  touchStart = {
    x: t.clientX,
    y: t.clientY,
    fromEdge: t.clientX < EDGE_ZONE || t.clientX > window.innerWidth - EDGE_ZONE
  }
}
const onTouchEnd = (e) => {
  if (!touchStart) return
  const t = e.changedTouches[0]
  const dx = t.clientX - touchStart.x
  const dy = t.clientY - touchStart.y
  const fromEdge = touchStart.fromEdge
  touchStart = null

  if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return
  // 地圖頁：橫向滑動是平移地圖的主要手勢，僅邊緣起始的滑動才切換分頁
  if (activeTab.value === 'map' && !fromEdge) return

  const idx = TAB_INDEX[activeTab.value]
  if (dx < 0 && idx < TABS.length - 1) switchTab(TABS[idx + 1].id)
  if (dx > 0 && idx > 0) switchTab(TABS[idx - 1].id)
}

// ==========================================
// 戰情摘要頁：統計卡與 AI 事件分析
// ==========================================
const nowTick = ref(Date.now())
const formatCountdown = (expiresAt) => {
  const total = Math.max(0, Math.floor((expiresAt - nowTick.value) / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const sec = total % 60
  const parts = []
  if (h) parts.push(`${h} 時`)
  if (h || m) parts.push(`${m} 分`)
  parts.push(`${sec} 秒`)
  return parts.join(' ')
}

const myEvents = computed(() => eventsList.value
  .filter(e => e.userId === myUserId)
  .sort((a, b) => (b.createdAt || b.expiresAt) - (a.createdAt || a.expiresAt)))

// 相對時間顯示：剛剛 / N 分鐘前 / N 小時前
const timeAgo = (createdAt) => {
  if (!createdAt) return ''
  const mins = Math.floor((Date.now() - createdAt) / 60000)
  if (mins < 1) return '剛剛'
  if (mins < 60) return `${mins} 分鐘前`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs} 小時前`
  return `${Math.floor(hrs / 24)} 天前`
}
// 事件剩餘壽命（分鐘）與生命週期百分比
const remainingMinutes = (expiresAt) => Math.max(0, Math.ceil((expiresAt - Date.now()) / 60000))
const lifePercent = (item) => {
  if (!item.createdAt || !item.expiresAt) return 100
  const total = item.expiresAt - item.createdAt
  if (total <= 0) return 0
  return Math.max(0, Math.min(100, Math.round(((item.expiresAt - Date.now()) / total) * 100)))
}
const categoryMeta = (cat) => ({
  info:    { label: '空位/活動', color: '#34c759', icon: '🟢' },
  warning: { label: '遺失/擁擠', color: '#ff9500', icon: '🟡' },
  danger:  { label: '緊急突發', color: '#ff3b30', icon: '🔴' },
}[cat] || { label: '其他', color: '#ff7f50', icon: '📍' })

// 從「我的發布」直接發布：切回地圖頁並打開表單
const publishFromMine = () => {
  switchTab('map')
  showModal.value = true
}
const dangerEventCount = computed(() =>
  eventsList.value.filter(e => e.category === 'danger').length)

// AI 事件分析：此區塊由組員負責開發中
// 後端端點已就緒：POST {AI_SERVICE_URL}/analyze-event
// 請求／回應格式見 backend/shared/schemas.py 的
// EventAnalysisRequest 與 EventAnalysisResponse

// ==========================================
// 座標上報 Location Service
// 沒上報就不會進 GEO 索引，附近有事件時永遠收不到推播
// ==========================================
const reportLocation = async (lat, lng) => {
  try {
    await fetch(`${LOCATION_SERVICE_URL}/locations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: getOrCreateUserId(), latitude: lat, longitude: lng })
    })
  } catch (err) {
    console.log('座標上報失敗:', err)
  }
}

// ==========================================
// 定位成功/失敗防呆處理
// ==========================================
const handleLocationSuccess = async (position) => {
  const { latitude, longitude } = position.coords
  currentCoords.value = { lat: latitude, lng: longitude }
  fetchAddress(latitude, longitude)
  reportLocation(latitude, longitude)

  if (!map.value) return

  // === 500 公尺半透明藍色雷達圈 ===
  if (!radarCircle.value) {
    radarCircle.value = L.circle([latitude, longitude], {
      radius: 500,
      color: '#007aff',       // 外框藍色
      weight: 1.5,            // 外框線寬
      fillColor: '#007aff',   // 填充藍色
      fillOpacity: 0.12,      // 柔和半透明
      interactive: false      // 不阻擋地圖底層點擊事件
    }).addTo(map.value)
  } else {
    radarCircle.value.setLatLng([latitude, longitude])
  }
  // ==============================

  // 鏡頭自動平滑飛向真實 GPS 座標
  map.value.flyTo([latitude, longitude], 16, {
    animate: true,
    duration: 1.2
  })

  // 確保地圖上永遠只有一個藍色定位點
  if (userMarker.value) {
    userMarker.value.setLatLng([latitude, longitude])
  } else {
    userMarker.value = L.marker([latitude, longitude], { icon: createUserPin() })
      .addTo(map.value)
      .bindPopup('<b>📍 您的真實位置</b>')
  }

  await fetchNearbyEvents(latitude, longitude)
}

const handleLocationError = async (error, isManual = false) => {
  let errorMsg = '無法取得精確定位，已切換至預設位置'
  
  if (error && error.code) {
    switch (error.code) {
      case error.PERMISSION_DENIED:
        errorMsg = '已拒絕定位權限，使用預設位置瀏覽'
        break
      case error.POSITION_UNAVAILABLE:
        errorMsg = '定位訊號不可用，使用預設位置'
        break
      case error.TIMEOUT:
        errorMsg = '定位請求逾時，使用預設位置'
        break
    }
  }

  currentCoords.value = { ...DEFAULT_COORDS }
  locationText.value = `預設位置 (輔大校園)`
  reportLocation(DEFAULT_COORDS.lat, DEFAULT_COORDS.lng)

  if (map.value) {
    if (userMarker.value) {
      userMarker.value.setLatLng([DEFAULT_COORDS.lat, DEFAULT_COORDS.lng])
    } else {
      userMarker.value = L.marker([DEFAULT_COORDS.lat, DEFAULT_COORDS.lng], { icon: createUserPin() })
        .addTo(map.value)
        .bindPopup('<b>📍 預設位置</b>')
    }
  }

  triggerToast(`⚠️ ${errorMsg}`)
  await fetchNearbyEvents(DEFAULT_COORDS.lat, DEFAULT_COORDS.lng)
}

const requestUserLocation = (isManual = false) => {
  if (!navigator.geolocation) {
    handleLocationError({ code: 0 }, isManual)
    return
  }

  navigator.geolocation.getCurrentPosition(
    (position) => {
      handleLocationSuccess(position)
      if (isManual) triggerToast('📍 已成功更新您的位置')
    },
    (error) => {
      handleLocationError(error, isManual)
    },
    {
      enableHighAccuracy: true,
      timeout: 8000,
      maximumAge: 10000
    }
  )
}

// ==========================
// 事件過期檢查與清理邏輯 (Timer)
// ==========================
const checkAndCleanExpiredEvents = () => {
  const now = Date.now()
  const activeEvents = []

  eventsList.value.forEach(item => {
    if (item.expiresAt) {
      if (now >= item.expiresAt) {
        const marker = markerMap.value.get(item.id)
        if (marker && map.value) {
          map.value.removeLayer(marker)
        }
        markerMap.value.delete(item.id)
        console.log(`⏳ 事件已過期並自動清除: ${item.title} (ID: ${item.id})`)
        return
      }
    }
    activeEvents.push(item)
  })

  eventsList.value = activeEvents
}

// ==========================
// 列表新增（統一去重入口）
// 同一事件可能同時從「發布後立即加入」與「WebSocket 廣播」兩條路進來，
// 一律先檢查 ID 與內容，避免列表出現重複卡片——重複 key 也會讓
// v-for 渲染錯亂，連帶造成左下角列表按鈕等畫面元素異常消失。
// ==========================
const addEventUnique = (newEvent, { notify = true } = {}) => {
  if (!newEvent.id || markerMap.value.has(newEvent.id)) return false

  // 內容層級防禦：ID 不同但標題與描述完全相同者視為同一則
  const isContentDuplicate = eventsList.value.some(
    e => e.title === newEvent.title && e.description === newEvent.description
  )
  if (isContentDuplicate) return false

  eventsList.value.unshift(newEvent)

  const marker = L.marker([newEvent.location.lat, newEvent.location.lng], {
    icon: createColoredPin(newEvent.category)
  })
  marker.bindPopup(createPopupContent(newEvent))

  if (selectedFilters.value[newEvent.category]) {
    marker.addTo(map.value)
  }

  markerMap.value.set(newEvent.id, marker)

  if (notify) {
    triggerToast(`🔔 收到周遭即時通報：「${newEvent.title}」`)
  }
  return true
}

// ==========================
// WebSocket 連線與即時推播
// ==========================
const wsStatus = ref('connecting')
let reconnectAttempts = 0
let reconnectTimeout = null

const setupWebSocket = () => {
  if (reconnectTimeout) clearTimeout(reconnectTimeout)
  
  const userId = getOrCreateUserId()
  const ws = new WebSocket(`${NOTIFICATION_WS_URL}/ws/${userId}`)

  ws.onopen = () => {
    console.log('✅ WebSocket 即時廣播頻道連線成功！')
    wsStatus.value = 'connected'
    reconnectAttempts = 0
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'hello') return
      // 心跳：收到 ping 必須回 pong，否則伺服器會判定連線死亡並關閉
      if (data.type === 'ping') {
        ws.send(JSON.stringify({ type: 'pong' }))
        return
      }

      const eventData = data.event || data.payload || data

      if (eventData.latitude && eventData.longitude) {
        const eventLat = eventData.latitude
        const eventLng = eventData.longitude
        const dist = getDistance(currentCoords.value.lat, currentCoords.value.lng, eventLat, eventLng)
        const walkTime = Math.max(1, Math.round(dist / 80))
        const durationMinutes = parseFloat(eventData.duration_minutes ?? eventData.duration) || 60
        const expiresAt = eventData.expires_at ? new Date(eventData.expires_at).getTime() : (Date.now() + durationMinutes * 60 * 1000)

        if (Date.now() >= expiresAt) return

        const newEvent = {
          id: eventData.event_id || eventData.id || Date.now(),
          userId: eventData.user_id || '',
          createdAt: Date.now(),
          title: eventData.title || '即時新通知',
          category: eventData.severity === 'urgent' ? 'danger' : (eventData.severity || 'info'),
          description: eventData.message || eventData.description || '周遭有新動態發布',
          imageUrl: eventData.image_url || eventData.image || '',
          location: { lat: eventLat, lng: eventLng },
          distance: dist,
          walkTime: walkTime,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          expiresAt: expiresAt
        }

        // 自己剛發布的事件會從 WS 廣播回來，不再跳「收到通報」
        addEventUnique(newEvent, { notify: newEvent.id !== lastPublishedEventId })
      }
    } catch (err) {
      console.log('解析推播訊息失敗:', err)
    }
  }

  ws.onerror = () => {
    wsStatus.value = 'disconnected'
  }

  ws.onclose = () => {
    wsStatus.value = 'reconnecting'
    reconnectAttempts++
    const delay = Math.min(10000, Math.pow(2, reconnectAttempts) * 1000)
    reconnectTimeout = setTimeout(() => {
      setupWebSocket()
    }, delay)
  }
}

// ==========================
// 生命週期管理
// ==========================
// 即時在線人數：每 3 秒查詢 location-service 的 GEO 索引成員數
const onlineCount = ref(0)
let onlinePollTimer = null
const fetchOnlineCount = async () => {
  try {
    const res = await fetch(`${LOCATION_SERVICE_URL}/locations/online`)
    if (res.ok) onlineCount.value = (await res.json()).online
  } catch {
    // 服務未就緒時沿用上一次數值
  }
}

onMounted(() => {
  map.value = L.map('map').setView([currentCoords.value.lat, currentCoords.value.lng], 16)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(map.value)

  setupWebSocket()
  requestUserLocation() // 統一由此函式初始化定位與單一標記

  fetchOnlineCount()
  onlinePollTimer = setInterval(fetchOnlineCount, 3000)
  expirationTimer = setInterval(checkAndCleanExpiredEvents, 10000)
  // 每 30 秒重報座標：last_seen TTL 60 秒，定期上報維持「在線」狀態
  locationReportTimer = setInterval(() => {
    reportLocation(currentCoords.value.lat, currentCoords.value.lng)
  }, 30000)
  // 每 15 秒重抓附近事件：讓別人編輯/刪除的事件在本地列表同步（v1 無即時編輯推播）
  eventsRefreshTimer = setInterval(() => {
    fetchNearbyEvents(currentCoords.value.lat, currentCoords.value.lng)
  }, 15000)
  // 每秒更新倒數計時
  countdownTimer = setInterval(() => { nowTick.value = Date.now() }, 1000)
})

onUnmounted(() => {
  if (expirationTimer) clearInterval(expirationTimer)
  if (locationReportTimer) clearInterval(locationReportTimer)
  if (eventsRefreshTimer) clearInterval(eventsRefreshTimer)
  if (countdownTimer) clearInterval(countdownTimer)
  if (onlinePollTimer) clearInterval(onlinePollTimer)
  if (reconnectTimeout) clearTimeout(reconnectTimeout)
})

// ==========================
// 視圖與列表控制
// ==========================
const recenterMap = () => {
  if (!map.value) return

  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        handleLocationSuccess(position)
        map.value.flyTo([position.coords.latitude, position.coords.longitude], 16, {
          animate: true,
          duration: 1.2
        })
        triggerToast('📍 已回到您的當前位置')
      },
      (error) => {
        handleLocationError(error, true)
        map.value.flyTo([currentCoords.value.lat, currentCoords.value.lng], 16)
      },
      { timeout: 5000 }
    )
  } else {
    map.value.flyTo([currentCoords.value.lat, currentCoords.value.lng], 16)
  }
}

const selectedFilters = ref({ info: true, warning: true, danger: true })

const toggleFilter = (cat) => {
  selectedFilters.value[cat] = !selectedFilters.value[cat]
  eventsList.value.forEach(item => {
    const marker = markerMap.value.get(item.id)
    if (marker) {
      if (selectedFilters.value[item.category]) {
        if (!map.value.hasLayer(marker)) map.value.addLayer(marker)
      } else {
        if (map.value.hasLayer(marker)) map.value.removeLayer(marker)
      }
    }
  })
}

const showListModal = ref(false)

const filteredSortedEvents = computed(() => {
  return eventsList.value
    .filter(item => selectedFilters.value[item.category])
    .sort((a, b) => a.distance - b.distance)
})

const flyToEvent = (item) => {
  showListModal.value = false
  map.value.flyTo([item.location.lat, item.location.lng], 18)
  const marker = markerMap.value.get(item.id)
  if (marker) {
    setTimeout(() => { marker.openPopup() }, 400)
  }
}

// ==========================
// 發布表單與後端 API 對接
// ==========================
const showModal = ref(false)
const toastMessage = ref('')
const showToast = ref(false)
const formData = ref({ title: '', category: 'info', duration: '60', description: '', imageFile: null, imagePreview: '' })

// 照片上傳前壓縮：手機原圖動輒 3-5MB，base64 後會超過後端上限，
// 也會撐爆 Redis。最長邊縮到 1600px、轉 JPEG（品質 0.85），畫質肉眼幾乎無差。
const compressImage = (file, maxSide = 1600, quality = 0.85) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('讀取照片失敗'))
    reader.onload = () => {
      const img = new Image()
      img.onerror = () => reject(new Error('照片格式無法解析'))
      img.onload = () => {
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height))
        const canvas = document.createElement('canvas')
        canvas.width = Math.max(1, Math.round(img.width * scale))
        canvas.height = Math.max(1, Math.round(img.height * scale))
        const ctx = canvas.getContext('2d')
        ctx.fillStyle = '#ffffff' // PNG 透明背景轉 JPEG 時鋪白底
        ctx.fillRect(0, 0, canvas.width, canvas.height)
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
        resolve(canvas.toDataURL('image/jpeg', quality))
      }
      img.src = reader.result
    }
    reader.readAsDataURL(file)
  })

const readFileAsDataURL = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('讀取照片失敗'))
    reader.onload = (event) => resolve(event.target.result)
    reader.readAsDataURL(file)
  })

const handleImageUpload = async (e) => {
  const file = e.target.files[0]
  if (!file) return
  try {
    // 小於 200KB 的圖直接用原圖（維持原始格式與透明度）
    if (file.size <= 200 * 1024) {
      formData.value.imageFile = file
      formData.value.imagePreview = await readFileAsDataURL(file)
      return
    }
    const compressed = await compressImage(file)
    // 壓縮後仍超過後端上限（罕見），再壓一次更狠的參數
    const finalPreview = compressed.length > 2_000_000
      ? await compressImage(file, 1080, 0.7)
      : compressed
    formData.value.imageFile = file
    formData.value.imagePreview = finalPreview
  } catch (err) {
    console.error('照片處理失敗:', err)
    triggerToast(`⚠️ ${err?.message || '照片處理失敗，請換一張試試'}`)
  }
}

const removeImage = () => { 
  formData.value.imageFile = null
  formData.value.imagePreview = '' 
}

// FastAPI 驗證錯誤的 detail 可能是字串或物件陣列，統一轉成可讀字串
const formatApiDetail = (detail) => {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map(d => {
      const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : ''
      return field ? `${field}：${d.msg}` : (d.msg || JSON.stringify(d))
    }).join('；')
  }
  return JSON.stringify(detail)
}

const triggerToast = (msg) => { 
  toastMessage.value = msg
  showToast.value = true
  setTimeout(() => { showToast.value = false }, 3500) 
}

const handleSubmit = async () => {
  const durationMinutes = parseFloat(formData.value.duration) || 60
  const expiresAt = Date.now() + durationMinutes * 60 * 1000

  // 1. 自動為標題附帶選中的分類標籤（例如：[圖書館空位] 文理大道有位子）
  const finalTitle = formData.value.title.startsWith(`[${selectedSubCategory.value}]`)
    ? formData.value.title
    : `[${selectedSubCategory.value}] ${formData.value.title}`

  const apiPayload = {
    title: finalTitle,
    message: formData.value.description || '無詳細描述',
    latitude: currentCoords.value.lat,
    longitude: currentCoords.value.lng,
    severity: formData.value.category === 'danger' ? 'urgent' : formData.value.category,
    radius_meters: 500,
    duration_minutes: durationMinutes,
    image_url: formData.value.imagePreview || '',
    user_id: getOrCreateUserId() // 補上後端要求的發布者身份驗證
  }

  try {
    const response = await fetch(`${EVENT_SERVICE_URL}/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(apiPayload)
    })

    if (response.ok) {
      // 用後端回傳的正式 event_id 當列表 ID，WebSocket 廣播回來時才能對應到同一筆、不會重複
      const body = await response.json()
      lastPublishedEventId = body.event_id || null
      const dist = getDistance(currentCoords.value.lat, currentCoords.value.lng, currentCoords.value.lat, currentCoords.value.lng)
      const walkTime = Math.max(1, Math.round(dist / 80))

      const newEvent = {
        id: body.event_id || Date.now(),
        userId: myUserId,
        createdAt: Date.now(),
        title: finalTitle,
        category: formData.value.category,
        description: formData.value.description || '無詳細描述',
        imageUrl: formData.value.imagePreview || '',
        location: { ...currentCoords.value },
        distance: dist,
        walkTime: walkTime,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        expiresAt: expiresAt
      }

      addEventUnique(newEvent, { notify: false })
      const marker = markerMap.value.get(newEvent.id)
      if (marker && selectedFilters.value[newEvent.category]) {
        marker.openPopup()
      }

      showModal.value = false
      triggerToast(`成功發布「${newEvent.title}」！已同步新增至地圖與清單。`)

      // 重置表單與預設標籤
      formData.value = { title: '', category: 'info', duration: '60', description: '', imageFile: null, imagePreview: '' }
      selectedSubCategory.value = '圖書館空位'
    } else {
      // 後端反垃圾機制（429 頻率限制 / 409 重複內容 / 422 未過 AI 審核）顯示具體原因
      let errorMsg = '發布失敗，請確認 API 欄位格式！'
      try {
        const err = await response.json()
        if (err && err.detail) errorMsg = `⚠️ ${formatApiDetail(err.detail)}`
      } catch (_) { /* 回應非 JSON 時維持預設訊息 */ }
      triggerToast(errorMsg)
    }
  } catch (error) {
    console.error('網路連線失敗:', error)
    triggerToast('網路請求失敗，請確認後端服務是否正常！')
  }
}

// ==========================
// 編輯 / 刪除自己的事件
// ==========================
const showEditModal = ref(false)
const editingEventId = ref(null)
const editForm = ref({ title: '', category: 'info', description: '' })
const deletingId = ref(null)

const startEditEvent = (item) => {
  editingEventId.value = item.id
  editForm.value = {
    title: item.title,
    category: item.category, // 前端類別：info / warning / danger
    description: item.description
  }
  showEditModal.value = true
}

const submitEdit = async () => {
  const severity = editForm.value.category === 'danger' ? 'urgent' : editForm.value.category
  try {
    const response = await fetch(`${EVENT_SERVICE_URL}/events/${editingEventId.value}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: myUserId,
        title: editForm.value.title,
        message: editForm.value.description || '無詳細描述',
        severity
      })
    })

    if (response.ok) {
      const item = eventsList.value.find(e => e.id === editingEventId.value)
      if (item) {
        item.title = editForm.value.title
        item.description = editForm.value.description || '無詳細描述'
        item.category = editForm.value.category
        const marker = markerMap.value.get(item.id)
        if (marker) marker.bindPopup(createPopupContent(item))
      }
      showEditModal.value = false
      triggerToast('✅ 事件已更新')
    } else {
      let errorMsg = '更新失敗，請稍後再試！'
      try {
        const err = await response.json()
        if (err && err.detail) errorMsg = `⚠️ ${err.detail}`
      } catch (_) { /* 回應非 JSON 時維持預設訊息 */ }
      triggerToast(errorMsg)
    }
  } catch (error) {
    console.error('更新事件失敗:', error)
    triggerToast('網路請求失敗，請確認後端服務是否正常！')
  }
}

const deleteEvent = async (item) => {
  if (!confirm(`確定要刪除「${item.title}」嗎？`)) return
  deletingId.value = item.id
  try {
    const response = await fetch(
      `${EVENT_SERVICE_URL}/events/${item.id}?user_id=${encodeURIComponent(myUserId)}`,
      { method: 'DELETE' }
    )

    if (response.ok) {
      const marker = markerMap.value.get(item.id)
      if (marker && map.value) map.value.removeLayer(marker)
      markerMap.value.delete(item.id)
      eventsList.value = eventsList.value.filter(e => e.id !== item.id)
      triggerToast('🗑️ 事件已刪除')
    } else {
      let errorMsg = '刪除失敗，請稍後再試！'
      try {
        const err = await response.json()
        if (err && err.detail) errorMsg = `⚠️ ${err.detail}`
      } catch (_) { /* 回應非 JSON 時維持預設訊息 */ }
      triggerToast(errorMsg)
    }
  } catch (error) {
    console.error('刪除事件失敗:', error)
    triggerToast('網路請求失敗，請確認後端服務是否正常！')
  } finally {
    deletingId.value = null
  }
}

// 取得周遭事件 (GET API)
const fetchNearbyEvents = async (lat, lng) => {
  try {
    const response = await fetch(`${EVENT_SERVICE_URL}/events?latitude=${lat}&longitude=${lng}&radius=3000`)
    if (response.ok) {
      const data = await response.json()
      console.log('GET /events 回傳資料：', data)

      markerMap.value.forEach(marker => marker.remove())
      markerMap.value.clear()
      eventsList.value = []

      const rawEvents = Array.isArray(data) ? data : (data.events || [])
      const seenIds = new Set()

      rawEvents.forEach(event => {
        if (typeof event === 'string') return

        const eventId = event.event_id || event.id
        // 回應本身可能帶重複，先按 ID 去重
        if (!eventId || seenIds.has(eventId)) return
        seenIds.add(eventId)

        const eventLat = event.latitude || lat
        const eventLng = event.longitude || lng
        const dist = getDistance(lat, lng, eventLat, eventLng)
        const walkTime = Math.max(1, Math.round(dist / 80))

        const createdAtMs = event.created_at ? new Date(event.created_at).getTime() : Date.now()
        const durationMs = (event.duration_minutes || 60) * 60 * 1000
        const expiresAt = event.expires_at ? new Date(event.expires_at).getTime() : (createdAtMs + durationMs)

        if (Date.now() >= expiresAt) return

        const newEvent = {
          id: eventId,
          userId: event.user_id || '',
          createdAt: createdAtMs,
          title: event.title || '周遭動態',
          category: event.severity === 'urgent' ? 'danger' : (event.severity || 'info'),
          description: event.message || event.description || '附近有動態發布',
          imageUrl: event.image_url || event.image || event.imageUrl || '',
          location: { lat: eventLat, lng: eventLng },
          distance: dist,
          walkTime: walkTime,
          timestamp: new Date(createdAtMs).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          expiresAt: expiresAt
        }

        eventsList.value.push(newEvent)

        const marker = L.marker([newEvent.location.lat, newEvent.location.lng], {
          icon: createColoredPin(newEvent.category)
        })
        marker.bindPopup(createPopupContent(newEvent))

        if (selectedFilters.value[newEvent.category]) {
          marker.addTo(map.value)
        }

        markerMap.value.set(newEvent.id, marker)
      })
    }
  } catch (error) {
    console.error('拉取事件時發生網路錯誤:', error)
  }
}

const createPopupContent = (event) => {
  const categoryLabels = { info: '🟢 空位/活動', warning: '🟡 遺失/擁擠', danger: '🔴 緊急突發' }
  const imageHtml = event.imageUrl 
    ? `<div style="margin: 8px 0; border-radius: 6px; overflow: hidden; max-height: 140px; background: #eee; cursor: pointer;" onclick="window.openImageLightbox('${event.imageUrl}')" title="點擊查看大圖">
         <img src="${event.imageUrl}" style="width: 100%; height: 100%; object-fit: cover; display: block;" />
       </div>` 
    : ''

  return `
    <div style="font-family: sans-serif; min-width: 180px; max-width: 220px;">
      <span style="font-size: 0.75rem; color: #666; font-weight: bold;">${categoryLabels[event.category]}</span>
      <h4 style="margin: 4px 0 6px 0; font-size: 1rem; color: #222;">${event.title}</h4>
      ${imageHtml}
      <p style="margin: 0 0 8px 0; font-size: 0.85rem; color: #444; word-break: break-word;">${event.description}</p>
      <div style="background: #f5f5f5; padding: 6px 8px; border-radius: 6px; font-size: 0.8rem; color: #333;">
        🚶 距離約 <b>${event.distance}m</b>｜步行約 <b>${event.walkTime} 分鐘</b>
      </div>
    </div>
  `
}

// ==========================================
// 圖片燈箱 (Lightbox) 放大檢視控制
// ==========================================
const lightboxImage = ref('')
const showLightbox = ref(false)

const openLightbox = (url) => {
  if (url) {
    lightboxImage.value = url
    showLightbox.value = true
  }
}

const closeLightbox = () => {
  showLightbox.value = false
  lightboxImage.value = ''
}

window.openImageLightbox = openLightbox
</script>

<template>
  <div class="app-container">
    <!-- 連線狀態指示膠囊 -->
  <div v-show="activeTab !== 'mine'" class="connection-pill" :class="wsStatus">
    <span class="status-indicator-dot"></span>
    <span v-if="wsStatus === 'connected'">即時同步中</span>
    <span v-else-if="wsStatus === 'reconnecting'">連線中斷，重試中...</span>
    <span v-else>伺服器未連線</span>
  </div>
    <!-- 即時在線人數膠囊（GEO 索引成員數，含模擬壓測使用者） -->
  <div v-show="activeTab !== 'mine'" class="connection-pill online-pill">
    <span>👥 即時在線 {{ onlineCount }} 人</span>
  </div>
    <!-- Toast 通知 -->
    <transition name="toast">
      <div v-if="showToast" class="toast-card">
        <span class="toast-icon">✨</span>
        <span class="toast-text">{{ toastMessage }}</span>
      </div>
    </transition>

    <!-- 三分頁視窗：戰情摘要（左）／地圖（中）／我的發布（右） -->
    <div class="tab-viewport" @touchstart.passive="onTouchStart" @touchend.passive="onTouchEnd">
      <div class="tab-track" :style="trackStyle">

        <!-- 頁面 1：戰情摘要 -->
        <section class="tab-panel ops-panel">
          <div class="ops-header">📊 事件摘要</div>

          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ onlineCount }}</span>
              <span class="stat-label">線上人數</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ eventsList.length }}</span>
              <span class="stat-label">進行中事件</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ dangerEventCount }}</span>
              <span class="stat-label">緊急事件</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ myEvents.length }}</span>
              <span class="stat-label">我的發布</span>
            </div>
          </div>

          <div class="ops-ai-card">
            <div class="ops-ai-header">🤖 AI 事件分析</div>
            <p class="ops-ai-hint">待開發</p>
          </div>
        </section>

        <!-- 頁面 2：地圖（主畫面） -->
        <section class="tab-panel map-panel">
          <div id="map"></div>
        </section>

        <!-- 頁面 3：我的發布 -->
        <section class="tab-panel mine-panel">
          <div class="mine-header">
            <span class="mine-header-title">📋 我的發布</span>
            <span v-if="myEvents.length" class="mine-count">{{ myEvents.length }} 則進行中</span>
          </div>

          <div v-if="pushState.supported" class="mine-push-card">
            <div class="mine-push-info">
              <span class="mine-push-icon">🔔</span>
              <div>
                <div class="mine-push-title">推播通知</div>
                <div class="mine-push-status">
                  {{ pushState.subscribed ? '已啟用——緊急事件會推播到這台裝置' : '未啟用——啟用後沒開 App 也能收到事件通知' }}
                </div>
              </div>
            </div>
            <button
              type="button"
              class="mine-push-btn"
              :class="{ off: pushState.subscribed }"
              @click="pushState.subscribed ? onDisablePush() : onEnablePush()"
            >
              {{ pushState.subscribed ? '關閉' : '開啟' }}
            </button>
          </div>

          <div v-if="myEvents.length === 0" class="mine-empty">
            <div class="mine-empty-icon">📍</div>
            <div class="mine-empty-title">還沒有發布過事件</div>
            <div class="mine-empty-desc">發布的內容會出現在這裡，<br />可以隨時編輯或刪除。</div>
            <button type="button" class="mine-cta" @click="publishFromMine">＋ 發布第一則事件</button>
          </div>

          <div v-else class="mine-list">
            <div
              v-for="item in myEvents"
              :key="item.id"
              class="mine-card"
              :style="{ borderLeftColor: categoryMeta(item.category).color }"
            >
              <div class="mine-card-top">
                <span
                  class="mine-chip"
                  :style="{ backgroundColor: categoryMeta(item.category).color + '1a', color: categoryMeta(item.category).color }"
                >
                  {{ categoryMeta(item.category).icon }} {{ categoryMeta(item.category).label }}
                </span>
                <span class="mine-timeago">{{ timeAgo(item.createdAt) }}</span>
              </div>

              <div class="mine-card-title">{{ item.title }}</div>
              <p class="mine-card-desc">{{ item.description }}</p>

              <div class="mine-life">
                <div class="mine-life-bar">
                  <div
                    class="mine-life-fill"
                    :style="{ width: lifePercent(item) + '%', backgroundColor: categoryMeta(item.category).color }"
                  ></div>
                </div>
                <span class="mine-life-text">⏳ 剩餘 {{ formatCountdown(item.expiresAt) }}</span>
              </div>

              <div class="mine-card-footer">
                <span class="mine-meta">📍 距離 {{ item.distance }} 公尺</span>
                <span class="card-actions">
                  <button type="button" class="card-action-btn" title="編輯事件" @click="startEditEvent(item)">✏️</button>
                  <button type="button" class="card-action-btn" title="刪除事件" :disabled="deletingId === item.id" @click="deleteEvent(item)">🗑️</button>
                </span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <!-- 左下角：「📋 查看附近清單」按鈕（僅地圖頁顯示） -->
    <button v-show="activeTab === 'map'" class="list-fab-btn" @click="showListModal = true">
      📋 列表 <span v-if="filteredSortedEvents.length > 0" class="badge">{{ filteredSortedEvents.length }}</span>
    </button>

    <!-- 右下方「定位回正」按鈕（僅地圖頁顯示） -->
    <button v-show="activeTab === 'map'" class="recenter-btn" @click="recenterMap" title="回到我的位置">
      <svg viewBox="0 0 24 24" width="20" height="20" stroke="#555555" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="8"></circle>
        <line x1="12" y1="2" x2="12" y2="4"></line>
        <line x1="12" y1="20" x2="12" y2="22"></line>
        <line x1="2" y1="12" x2="4" y2="12"></line>
        <line x1="20" y1="12" x2="22" y2="12"></line>
      </svg>
    </button>

    <!-- 右下角懸浮按鈕 FAB（僅地圖頁顯示） -->
    <button v-show="activeTab === 'map'" class="fab-btn" @click="showModal = true">＋</button>

    <!-- 底部 tab bar -->
    <nav class="tab-bar">
      <button
        v-for="t in TABS"
        :key="t.id"
        type="button"
        :class="['tab-btn', { active: activeTab === t.id }]"
        @click="switchTab(t.id)"
      >
        <span class="tab-icon">{{ t.icon }}</span>
        <span class="tab-label">{{ t.label }}</span>
      </button>
    </nav>

    <!-- 周遭事件清單抽屜 -->
    <div v-if="showListModal" class="modal-overlay" @click.self="showListModal = false">
      <div class="modal-card list-card-container">
        <header class="modal-header">
          <button class="close-btn" @click="showListModal = false">⊗</button>
          <h3>附近事件清單 (由近到遠)</h3>
          <div style="width: 24px;"></div>
        </header>

        <div class="list-filter-bar">
          <button type="button" :class="['chip chip-green', { active: selectedFilters.info }]" @click="toggleFilter('info')">
            🟢 空位/活動
          </button>
          <button type="button" :class="['chip chip-yellow', { active: selectedFilters.warning }]" @click="toggleFilter('warning')">
            🟡 遺失/擁擠
          </button>
          <button type="button" :class="['chip chip-red', { active: selectedFilters.danger }]" @click="toggleFilter('danger')">
            🔴 緊急突發
          </button>
        </div>

        <div v-if="filteredSortedEvents.length === 0" class="empty-state">
          目前勾選的類別中，附近暫無發布的事件。
        </div>

        <div v-else class="event-list">
          <div 
            v-for="item in filteredSortedEvents" 
            :key="item.id" 
            class="event-card"
            @click="flyToEvent(item)"
          >
            <!-- 若有圖片則顯示縮圖，點擊只放大圖片，不觸發外層卡片的飛越 -->
            <div 
              v-if="item.imageUrl" 
              class="card-thumb" 
              @click.stop="openLightbox(item.imageUrl)" 
              title="點擊查看大圖"
              >
              <img :src="item.imageUrl" alt="event-pic" />
            </div>

            <div class="card-content">
              <div class="card-header">
                <span class="card-title">{{ item.title }}</span>
                <!-- 加上圖示與「分」字，語意更直觀 -->
                <span class="card-badge" :class="item.category">
                  步行時間約 {{ item.walkTime }} 分鐘
                </span>
              </div>
              <p class="card-desc">{{ item.description }}</p>
              <div class="card-meta">
                <span>距離 {{ item.distance }}公尺</span>
                <span>發布時間  {{ item.timestamp }}</span>
                <span v-if="item.userId === myUserId" class="card-actions">
                  <button type="button" class="card-action-btn" title="編輯事件" @click.stop="startEditEvent(item)">✏️</button>
                  <button type="button" class="card-action-btn" title="刪除事件" :disabled="deletingId === item.id" @click.stop="deleteEvent(item)">🗑️</button>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 發布事件表單 -->
    <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
      <div class="modal-card">
        <header class="modal-header">
          <button class="close-btn" @click="showModal = false">⊗</button>
          <h3>發布事件</h3>
          <div style="width: 24px;"></div>
        </header>

        <form @submit.prevent="handleSubmit" class="modal-form">
          <div class="location-badge">📍 {{ locationText }}</div>
          <div class="form-group">
            <input type="text" v-model="formData.title" placeholder="請輸入事件名稱..." required class="input-light" />
          </div>

          <!-- 事件分類選擇器 -->
          <div class="category-selector-container">
            <label class="category-label">事件分類與危害程度：</label>
            <div class="category-groups">
              <div v-for="cat in CATEGORIES" :key="cat.group" class="category-group-card">
                <div class="category-group-header">
                  <span class="category-dot" :style="{ backgroundColor: cat.color }"></span>
                  <span class="category-group-title" :style="{ color: cat.color }">{{ cat.group }}</span>
                </div>
                <div class="category-tags">
                  <button
                    type="button"
                    v-for="tag in cat.tags"
                    :key="tag"
                    class="category-tag-btn"
                    :class="{ active: selectedSubCategory === tag }"
                    :style="selectedSubCategory === tag ? { borderColor: cat.color, color: cat.color, backgroundColor: cat.color + '18' } : {}"
                    @click="selectCategoryTag(tag, cat.severity)"
                  >
                    {{ tag }}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div class="form-group">
            <label class="group-label">⏳ 事件時效：</label>
            <select v-model="formData.duration" class="select-light">
              <option value="30">保留 30 分鐘 (即時狀況)</option>
              <option value="60">保留 1 小時</option>
              <option value="120">保留 2 小時</option>
              <option value="1440">保留 24 小時 (全天活動)</option>
            </select>
          </div>

          <div class="form-group">
            <label class="group-label">📷 現場照片 (選填)：</label>
            <div v-if="!formData.imagePreview" class="upload-box">
              <input type="file" accept="image/*" @change="handleImageUpload" id="file-input" />
              <label for="file-input" class="upload-label">點擊上傳或拍攝照片</label>
            </div>
            <div v-else class="image-preview-container">
              <img :src="formData.imagePreview" alt="預覽圖" class="preview-img" />
              <button type="button" class="remove-img-btn" @click="removeImage">✕ 移除照片</button>
            </div>
          </div>

          <div class="form-group">
            <textarea v-model="formData.description" rows="3" placeholder="詳細描述：補充說明具體位置、特徵或狀況..." class="input-light"></textarea>
          </div>

          <button type="submit" class="submit-btn">確認發布</button>
        </form>
      </div>
    </div>
    <!-- 編輯事件表單 -->
    <div v-if="showEditModal" class="modal-overlay" @click.self="showEditModal = false">
      <div class="modal-card">
        <header class="modal-header">
          <button class="close-btn" @click="showEditModal = false">⊗</button>
          <h3>編輯事件</h3>
          <div style="width: 24px;"></div>
        </header>

        <form @submit.prevent="submitEdit" class="modal-form">
          <div class="form-group">
            <input type="text" v-model="editForm.title" placeholder="事件名稱" required maxlength="100" class="input-light" />
          </div>

          <div class="form-group category-group">
            <label class="group-label">事件類別：</label>
            <div class="radio-options">
              <label class="radio-item">
                <input type="radio" v-model="editForm.category" value="info" />
                <span class="dot dot-green"></span>
                <span>空位 / 活動</span>
              </label>
              <label class="radio-item">
                <input type="radio" v-model="editForm.category" value="warning" />
                <span class="dot dot-yellow"></span>
                <span>遺失 / 擁擠</span>
              </label>
              <label class="radio-item">
                <input type="radio" v-model="editForm.category" value="danger" />
                <span class="dot dot-red"></span>
                <span>緊急 / 突發</span>
              </label>
            </div>
          </div>

          <div class="form-group">
            <textarea v-model="editForm.description" rows="3" maxlength="1000" placeholder="詳細描述..." class="input-light"></textarea>
          </div>

          <button type="submit" class="submit-btn">儲存變更</button>
        </form>
      </div>
    </div>
  </div>
  <!-- 加入主畫面後的推播詢問 -->
  <transition name="toast">
    <div v-if="showPushPrompt" class="push-prompt-overlay">
      <div class="push-prompt-card">
        <div class="push-prompt-icon">🔔</div>
        <div class="push-prompt-title">開啟通知？</div>
        <p class="push-prompt-desc">開啟後即使沒有打開 App，附近有緊急事件時也會直接推播到這台裝置。</p>
        <div class="push-prompt-actions">
          <button type="button" class="push-prompt-later" @click="dismissPushPrompt">先不用</button>
          <button type="button" class="push-prompt-enable" @click="onEnablePush">開啟通知</button>
        </div>
      </div>
    </div>
  </transition>
  <!-- 大圖燈箱 Lightbox Modal -->
  <transition name="toast">
    <div v-if="showLightbox" class="lightbox-overlay" @click="closeLightbox">
     <button class="lightbox-close-btn" @click="closeLightbox">✕</button>
      <img :src="lightboxImage" class="lightbox-img" @click.stop alt="現場大圖" />
    </div>
  </transition>
</template>