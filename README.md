# ttdlp

Un **sidecar de streaming con yt-dlp** para vídeo de TikTok. Dado el ID de un vídeo, lo descarga con [yt-dlp](https://github.com/yt-dlp/yt-dlp) (forzando H.264/MP4 reproducible en navegador), lo cachea un rato y lo sirve por HTTP con soporte de `Range`.

Existe para resolver lo único que la API web no puede: TikTok sirve la mayoría de los `playAddr` de vídeo desde `*-webapp-prime.tiktok.com`, que devuelven **403 Access Denied** a cualquier petición server-side (ni cookies ni cabeceras coincidentes valen — está protegido por TLS/WAF). yt-dlp es el único componente que resuelve un stream reproducible de forma fiable, así que este servicio le deja hacer el trabajo duro y expone un endpoint trivial.

Hecho como backend de vídeo para una instancia revivida de [ProxiTok](https://github.com/darlopvil/ProxiTok), pero usable por sí solo.

## Cómo funciona

```
navegador ──► ProxiTok /video?id= ──► ttdlp /video?id= ──► yt-dlp ──► TikTok
                                          │
                                  descarga mp4 H.264, cachea 30 min, sirve con Range
```

## Endpoints

| Endpoint | Qué hace |
|----------|----------|
| `GET /health` | Comprobación de vida → `{"status":"ok"}` |
| `GET /video?id=<id>&user=<uniqueId>` | Sirve el vídeo inline (`video/mp4`, con Range) |
| `GET /download?id=<id>&user=<uniqueId>[&watermark=1]` | Igual, pero como descarga (`tiktok-<id>-no_watermark.mp4` / `-watermark.mp4`) |

`user` es opcional (yt-dlp resuelve solo con el ID); pasarlo construye una URL de origen más limpia.

## Ejecutar

```bash
docker compose up -d --build
```

El servicio **no expone puertos al host** — se une a una red Docker externa (`nginx-proxy-manager_default` por defecto) y se accede internamente por nombre de contenedor (`ttdlp_app:8080`). Ajusta la red en `docker-compose.yml` según tu setup. Está pensado para ir **detrás** de tu propio proxy inverso / frontend, no expuesto directamente.

## Notas

- **Códec:** el formato por defecto de TikTok suele ser `bytevc1` (H.265), que los navegadores no decodifican. ttdlp ordena por `vcodec:h264` y remuxea a MP4 para que el `<video>` funcione sin más.
- **Caché:** los clips se cachean en un volumen 30 min (`TTL` en `app.py`) porque las URLs de TikTok caducan; los ficheros viejos se purgan en cada petición.
- **Mantenerlo vivo:** cuando TikTok cambie algo, `pip install -U yt-dlp` (reconstruir la imagen) es todo el arreglo — ese es el sentido de delegar en yt-dlp.
- La primera reproducción de un clip tarda ~1-3s (extracción + descarga); las siguientes van instantáneas desde caché.

## Créditos

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — hace todo el trabajo de verdad.
- [Flask](https://flask.palletsprojects.com/) + [Gunicorn](https://gunicorn.org/) — la fina capa HTTP.

## Licencia

Lee el archivo [LICENSE](LICENSE)