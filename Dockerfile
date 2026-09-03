# Denon AVP-A1HD RS-232 integration for Unfolded Circle Remote — Docker image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UC_CONFIG_HOME=/config \
    UC_INTEGRATION_INTERFACE=0.0.0.0 \
    UC_INTEGRATION_HTTP_PORT=9092 \
    UC_LOG_LEVEL=INFO

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY driver.json .
COPY denon.png .
COPY intg-denon ./intg-denon

VOLUME ["/config"]
EXPOSE 9092

WORKDIR /app/intg-denon
# driver.json is looked up relative to the working directory
RUN ln -s /app/driver.json driver.json

CMD ["python", "driver.py"]
