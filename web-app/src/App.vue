<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

// ==========================================
// 地圖核心與狀態
// ==========================================
const DEFAULT_COORDS = { lat: 25.0366, lng: 121.4323 } // 預設座標（輔仁大學）
const map = ref(null)
const userMarker = ref(null)
const currentCoords = ref({ ...DEFAULT_COORDS })
const locationText = ref('正在取得真實 GPS 座標...')
const eventsList = ref([])
const markerMap = ref(new Map())

let expirationTimer = null

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

// ==========================================
// 定位成功/失敗防呆處理
// ==========================================
const handleLocationSuccess = async (position) => {
  const { latitude, longitude } = position.coords
  currentCoords.value = { lat: latitude, lng: longitude }
  fetchAddress(latitude, longitude)

  if (!map.value) return
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
// WebSocket 連線與即時推播
// ==========================
const wsStatus = ref('connecting')
let reconnectAttempts = 0
let reconnectTimeout = null

const setupWebSocket = () => {
  if (reconnectTimeout) clearTimeout(reconnectTimeout)
  
  const userId = getOrCreateUserId()
  const ws = new WebSocket(`ws://127.0.0.1:8003/ws/${userId}`)

  ws.onopen = () => {
    console.log('✅ WebSocket 即時廣播頻道連線成功！')
    wsStatus.value = 'connected'
    reconnectAttempts = 0
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === 'hello' || data.type === 'ping') return

      const eventData = data.event || data.payload || data

      if (eventData.latitude && eventData.longitude) {
        const eventLat = eventData.latitude
        const eventLng = eventData.longitude
        const dist = getDistance(currentCoords.value.lat, currentCoords.value.lng, eventLat, eventLng)
        const walkTime = Math.max(1, Math.round(dist / 80))
        const durationMinutes = parseFloat(eventData.duration) || 60
        const expiresAt = eventData.expires_at ? new Date(eventData.expires_at).getTime() : (Date.now() + durationMinutes * 60 * 1000)

        if (Date.now() >= expiresAt) return

        const newEvent = {
          id: eventData.event_id || eventData.id || Date.now(),
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

        if (!markerMap.value.has(newEvent.id)) {
          eventsList.value.unshift(newEvent)

          const marker = L.marker([newEvent.location.lat, newEvent.location.lng], {
            icon: createColoredPin(newEvent.category)
          })
          marker.bindPopup(createPopupContent(newEvent))

          if (selectedFilters.value[newEvent.category]) {
            marker.addTo(map.value)
          }

          markerMap.value.set(newEvent.id, marker)
          triggerToast(`🔔 收到周遭即時通報：「${newEvent.title}」`)
        }
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
onMounted(() => {
  map.value = L.map('map').setView([currentCoords.value.lat, currentCoords.value.lng], 16)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(map.value)

  setupWebSocket()
  requestUserLocation() // 統一由此函式初始化定位與單一標記

  expirationTimer = setInterval(checkAndCleanExpiredEvents, 10000)
})

onUnmounted(() => {
  if (expirationTimer) clearInterval(expirationTimer)
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

const handleImageUpload = (e) => {
  const file = e.target.files[0]
  if (file) {
    formData.value.imageFile = file
    const reader = new FileReader()
    reader.onload = (event) => {
      formData.value.imagePreview = event.target.result
    }
    reader.readAsDataURL(file)
  }
}

const removeImage = () => { 
  formData.value.imageFile = null
  formData.value.imagePreview = '' 
}

const triggerToast = (msg) => { 
  toastMessage.value = msg
  showToast.value = true
  setTimeout(() => { showToast.value = false }, 3500) 
}

const handleSubmit = async () => {
  const durationMinutes = parseFloat(formData.value.duration) || 60
  const expiresAt = Date.now() + durationMinutes * 60 * 1000
  const apiPayload = {
    title: formData.value.title,
    message: formData.value.description || '無詳細描述',
    latitude: currentCoords.value.lat,
    longitude: currentCoords.value.lng,
    severity: formData.value.category === 'danger' ? 'urgent' : formData.value.category,
    radius_meters: 500,
    image_url: formData.value.imagePreview || ''
  }

  try {
    const response = await fetch('http://localhost:8002/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(apiPayload)
    })

    if (response.ok) {
      const dist = getDistance(currentCoords.value.lat, currentCoords.value.lng, currentCoords.value.lat, currentCoords.value.lng)
      const walkTime = Math.max(1, Math.round(dist / 80))
      
      const newEvent = {
        id: Date.now(),
        title: formData.value.title,
        category: formData.value.category,
        description: formData.value.description || '無詳細描述',
        imageUrl: formData.value.imagePreview || '',
        location: { ...currentCoords.value },
        distance: dist,
        walkTime: walkTime,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        expiresAt: expiresAt
      }
      
      eventsList.value.unshift(newEvent)
      
      const marker = L.marker([newEvent.location.lat, newEvent.location.lng], { 
        icon: createColoredPin(newEvent.category) 
      })
      marker.bindPopup(createPopupContent(newEvent))
      
      if (selectedFilters.value[newEvent.category]) {
        marker.addTo(map.value).openPopup()
      }
      
      markerMap.value.set(newEvent.id, marker)

      showModal.value = false
      triggerToast(`成功發布「${newEvent.title}」！已同步新增至地圖與清單。`)
      formData.value = { title: '', category: 'info', duration: '60', description: '', imageFile: null, imagePreview: '' }
    } else {
      triggerToast('發布失敗，請確認 API 欄位格式！')
    }
  } catch (error) {
    console.error('網路連線失敗:', error)
    triggerToast('網路請求失敗，請確認後端服務是否正常！')
  }
}

// 取得周遭事件 (GET API)
const fetchNearbyEvents = async (lat, lng) => {
  try {
    const response = await fetch(`http://localhost:8002/events?latitude=${lat}&longitude=${lng}&radius=3000`)
    if (response.ok) {
      const data = await response.json()
      console.log('GET /events 回傳資料：', data)

      markerMap.value.forEach(marker => marker.remove())
      markerMap.value.clear()
      eventsList.value = []

      const rawEvents = Array.isArray(data) ? data : (data.events || [])

      rawEvents.forEach(event => {
        if (typeof event === 'string') return

        const eventLat = event.latitude || lat
        const eventLng = event.longitude || lng
        const dist = getDistance(lat, lng, eventLat, eventLng)
        const walkTime = Math.max(1, Math.round(dist / 80))
        
        const createdAtMs = event.created_at ? new Date(event.created_at).getTime() : Date.now()
        const durationMs = (event.duration_minutes || 60) * 60 * 1000
        const expiresAt = event.expires_at ? new Date(event.expires_at).getTime() : (createdAtMs + durationMs)

        if (Date.now() >= expiresAt) return

        const newEvent = {
          id: event.event_id || event.id || Date.now(),
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
    <!-- 頂部純淨搜尋列 -->
    <header class="top-nav">
      <div class="search-bar">
        <span class="search-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" stroke="#888888" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
        </span>
        <input type="text" placeholder="尋找事件或地點..." />
      </div>
    </header>
    <!-- 連線狀態指示膠囊 -->
  <div class="connection-pill" :class="wsStatus">
    <span class="status-indicator-dot"></span>
    <span v-if="wsStatus === 'connected'">即時同步中</span>
    <span v-else-if="wsStatus === 'reconnecting'">連線中斷，重試中...</span>
    <span v-else>伺服器未連線</span>
  </div>
    <!-- Toast 通知 -->
    <transition name="toast">
      <div v-if="showToast" class="toast-card">
        <span class="toast-icon">✨</span>
        <span class="toast-text">{{ toastMessage }}</span>
      </div>
    </transition>

    <!-- 地圖容器 -->
    <div id="map"></div>

    <!-- 左下角：「📋 查看附近清單」按鈕 -->
    <button class="list-fab-btn" @click="showListModal = true">
      📋 列表 <span v-if="filteredSortedEvents.length > 0" class="badge">{{ filteredSortedEvents.length }}</span>
    </button>

    <!-- 右下方「定位回正」按鈕 -->
    <button class="recenter-btn" @click="recenterMap" title="回到我的位置">
      <svg viewBox="0 0 24 24" width="20" height="20" stroke="#555555" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="8"></circle>
        <line x1="12" y1="2" x2="12" y2="4"></line>
        <line x1="12" y1="20" x2="12" y2="22"></line>
        <line x1="2" y1="12" x2="4" y2="12"></line>
        <line x1="20" y1="12" x2="22" y2="12"></line>
      </svg>
    </button>

    <!-- 右下角懸浮按鈕 FAB -->
    <button class="fab-btn" @click="showModal = true">＋</button>

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

          <div class="form-group category-group">
            <label class="group-label">事件類別選擇：</label>
            <div class="radio-options">
              <label class="radio-item">
                <input type="radio" v-model="formData.category" value="info" />
                <span class="dot dot-green"></span>
                <span>空位 / 活動 (綠色圖釘)</span>
              </label>
              <label class="radio-item">
                <input type="radio" v-model="formData.category" value="warning" />
                <span class="dot dot-yellow"></span>
                <span>遺失 / 擁擠 (黃色圖釘)</span>
              </label>
              <label class="radio-item">
                <input type="radio" v-model="formData.category" value="danger" />
                <span class="dot dot-red"></span>
                <span>緊急 / 突發 (紅色圖釘)</span>
              </label>
            </div>
          </div>

          <div class="form-group">
            <label class="group-label">⏳ 事件時效：</label>
            <select v-model="formData.duration" class="select-light">
              <option value="0.16">⚡ 測試用：10 秒後自動過期</option>
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
  </div>
  <!-- 大圖燈箱 Lightbox Modal -->
  <transition name="toast">
    <div v-if="showLightbox" class="lightbox-overlay" @click="closeLightbox">
     <button class="lightbox-close-btn" @click="closeLightbox">✕</button>
      <img :src="lightboxImage" class="lightbox-img" @click.stop alt="現場大圖" />
    </div>
  </transition>
</template>