FROM python:3.12-slim

WORKDIR /app

COPY simulator/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY simulator /app/simulator

CMD ["python", "simulator/simulate_users.py"]
