FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY backend/notification-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/shared /app/backend/shared
COPY backend/entrypoint.sh /app/entrypoint.sh
COPY backend/notification-service/app /app/app

RUN useradd --create-home appuser
USER appuser

CMD ["/app/entrypoint.sh"]
