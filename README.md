# ttdlp

Un **sidecar con yt-dlp** para TikTok. Resuelve lo que la API web no puede: reproducción y descarga de vídeo, audio original y el listado de vídeos de un perfil. Dado un ID (o un usuario), usa [yt-dlp](https://github.com/yt-dlp/yt-dlp) para hacer el trabajo duro, cachea el resultado y lo sirve por HTTP con soporte de `Range`.

Existe porque TikTok sirve la mayoría de los `playAddr` de vídeo desde `*-webapp-prime.tiktok.com`, que devuelven **403 Access Denied** a cualquier petición server-side (ni cookies ni cabeceras coincidentes valen — está protegido por TLS/WAF). Y porque `/api/post/item_list/` (la lista de vídeos de un usuario) responde **200 vacío** a la firma web. yt-dlp es el único componente que resuelve ambas cosas de forma fiable, así que este servicio le deja hacer el trabajo y expone endpoints triviales.

Hecho como backend de una instancia revivida de [ProxiTok](https://github.com/darlopvil/ProxiTok), pero usable por sí solo.

## Cómo funciona

```
navegador ─► ProxiTok ─► ttdlp ─► yt-dlp ─► TikTok
                           │
          ┌────────────────┼─────────────────────────────┐
          │ /video,/download: descarga mp4 H.264, Range   │
          │ /audio:  extrae el audio del mp4 (ffmpeg copy) │
          │ /user:   lista el perfil (--flat-playlist)     │
          └────────────────────────────────────────────────┘
```

## Endpoints

| Endpoint | Qué hace |
|----------|----------|
| `GET /health` | Comprobación de vida → `{"status":"ok"}` |
| `GET /video?id=<id>&user=<uniqueId>` | Sirve el vídeo inline (`video/mp4`, con Range) |
| `GET /download?id=<id>&user=<uniqueId>[&watermark=1]` | Igual, pero como descarga (`tiktok-<id>-no_watermark.mp4` / `-watermark.mp4`) |
| `GET /audio?id=<id>&user=<uniqueId>` | Sirve el audio original (`audio/mp4`/m4a) |
| `GET /user?user=<uniqueId>[&start=N&count=M]` | Lista los vídeos del perfil en JSON (`yt-dlp --flat-playlist`) |

`user` es opcional en los endpoints de vídeo/audio (yt-dlp resuelve solo con el ID); pasarlo construye una URL de origen más limpia.

## Ejecutar

```bash
docker compose up -d --build
```

El servicio **no expone puertos al host** — se une a una red Docker externa (`nginx-proxy-manager_default` por defecto) y se accede internamente por nombre de contenedor (`ttdlp_app:8080`). Ajusta la red en `docker-compose.yml` según tu setup. Está pensado para ir **detrás** de tu propio proxy inverso / frontend, no expuesto directamente.

## Notas

- **Códec (vídeo):** el formato por defecto de TikTok suele ser `bytevc1` (H.265), que los navegadores no decodifican. ttdlp ordena por `vcodec:h264` y remuxea a MP4 para que el `<video>` funcione sin más.
- **Audio:** se extrae del **mismo mp4 H.264** que `/video` (cacheado o nuevo) con `ffmpeg -vn -c:a copy` — instantáneo, sin transcode. Importante: hacer `yt-dlp -x` directo sobre el formato `bytevc1` falla (`unable to obtain file audio codec with ffprobe`), por eso se reutiliza el H.264.
- **Listado de perfil:** `yt-dlp --flat-playlist -J` devuelve `entries` con id, descripción, timestamp, counts y thumbnails (cover/dynamicCover/originCover). Paginación con `--playlist-start/--playlist-end`. Se cachea el JSON ~10 min.
- **Caché:** los clips se cachean en un volumen 30 min (las URLs de TikTok caducan); los ficheros viejos (mp4, audio, json) se purgan en cada petición.
- **Mantenerlo vivo:** cuando TikTok cambie algo, `pip install -U yt-dlp` (reconstruir la imagen) es todo el arreglo — ese es el sentido de delegar en yt-dlp.
- La primera reproducción/extracción de un clip tarda ~1-3 s; las siguientes van instantáneas desde caché.

## Créditos

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) — hace todo el trabajo de verdad.
- [Flask](https://flask.palletsprojects.com/) + [Gunicorn](https://gunicorn.org/) — la fina capa HTTP.

## Licencia

Lee el archivo [LICENSE](LICENSE)