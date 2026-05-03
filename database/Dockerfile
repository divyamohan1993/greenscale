FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY schema.sql .
COPY main.py .

RUN mkdir -p /data
ENV DATA_DIR=/data PORT=8080
EXPOSE 8080
CMD ["python", "main.py"]
