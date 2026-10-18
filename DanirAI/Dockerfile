FROM python:3.11-slim

WORKDIR /srv/danirai

# ffmpeg для видео (альтернатива imageio-ffmpeg) + шрифты для кадров
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt pillow

COPY backend/ backend/
COPY frontend/ frontend/

ENV DANIRAI_DATA_DIR=/srv/danirai/data \
    PYTHONUNBUFFERED=1

VOLUME ["/srv/danirai/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
