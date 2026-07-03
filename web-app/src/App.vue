<script setup>
import { onMounted } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

onMounted(() => {
  // 1. 初始化地圖，先設定預設中心點 (台北車站)，縮放級別 13
  const map = L.map('map').setView([25.0415, 121.5198], 13)

  // 2. 載入 OpenStreetMap 免費圖資
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap'
  }).addTo(map)

  // 3. 自動要求並獲取使用者真實 GPS 定位
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        map.flyTo([latitude, longitude], 16);
        L.marker([latitude, longitude]).addTo(map)
          .bindPopup('📍 您目前的位置').openPopup();
      },
      (error) => {
        console.warn('無法取得定位權限，將停留在預設畫面：', error.message);
      }
    )
  } else {
    console.warn('您的瀏覽器不支援地理定位功能。');
  }
})
</script>

<template>
  <div id="map"></div>

  <button class="fab-btn">+</button>
</template>

<style scoped>
/* 讓地圖 100% 填滿視窗，不留空白 */
#map {
  width: 100vw;
  height: 100vh;
  margin: 0;
  padding: 0;
  z-index: 0; 
}

/* 清除瀏覽器預設的邊界與捲軸 */
:global(body) {
  margin: 0;
  overflow: hidden;
}

/* 懸浮按鈕的樣式設計 */
.fab-btn {
  position: fixed;           /* 絕對固定在畫面上 */
  bottom: 30px;              /* 距離底部 30px */
  right: 30px;               /* 距離右邊 30px */
  width: 60px;               /* Figma 設定的寬度 */
  height: 60px;              /* Figma 設定的高度 */
  background-color: #FF6D00; /* 亮橘色主色調 */
  color: white;              /* ＋號是白色的 */
  border: none;              /* 移除邊框 */
  border-radius: 50%;        /* 變成正圓形 */
  font-size: 36px;           /* 放大文字 */
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3); /* 加上靈魂陰影 */
  cursor: pointer;           /* 滑鼠變成手指 */
  z-index: 1000;             /* 確保數字大於地圖，不被蓋住 */
  
  /* 讓＋號完美置中 */
  display: flex;
  justify-content: center;
  align-items: center;
}

/* 加上互動感：按下去時微微縮小 */
.fab-btn:active {
  transform: scale(0.95);
}
</style>