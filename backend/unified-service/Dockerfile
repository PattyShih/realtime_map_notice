# Unified API：單一執行個體部署設定檔（掛載四個微服務）。
# 適用於 Render Starter（每月 7 美元單實例），四個服務共用一個執行個體；
# 本機 docker-compose 與 Kubernetes 之微服務部署不受影響。
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app

# 資安應變（Render 2026-10 通告）：建置時刷新系統 CA 憑證儲存庫
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

COPY backend/unified-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/shared /app/backend/shared
COPY backend/location-service/app /app/backend/location-service/app
COPY backend/event-service/app /app/backend/event-service/app
COPY backend/notification-service/app /app/backend/notification-service/app
COPY backend/ai-service/app /app/backend/ai-service/app
COPY backend/unified-service/app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
