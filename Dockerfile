FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir yt-dlp flask gunicorn

WORKDIR /app
COPY app.py /app/app.py

EXPOSE 8080
# 3 workers, timeout amplio para la extracción + descarga de yt-dlp
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "3", "-t", "120", "app:app"]