FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir yt-dlp flask gunicorn

WORKDIR /app
COPY app.py /app/app.py

EXPOSE 8080
# 3 workers × 4 hilos = 12 peticiones a la vez. Cada petición en frío se pasa ~2 s
# esperando a yt-dlp (red, no CPU): con workers síncronos, la 4.ª se quedaba en cola
# (medido: 5 vídeos a la vez → 2,4/2,7/2,8/4,9/7,7 s). Con hilos no se bloquean.
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "3", "--threads", "4", "-t", "120", "app:app"]