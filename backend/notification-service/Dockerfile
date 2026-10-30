FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app

# 資安應變（Render 2026-10 通告）：刷新系統 CA 憑證庫，
# 因應 eMudhra 中繼憑證簽發金鑰外洩事件
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

COPY backend/notification-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/shared /app/backend/shared
COPY backend/notification-service/app /app/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]


EXPOSE 8000
