# metrics.md — Mediciones reales

Fecha de medición: 2026-09-23 UTC. Entorno: Windows Server 2022, Python 3.12.8,
ffmpeg 8.1.2. Sin `HF_TOKEN` ni credenciales de ningún tipo.

## Vía principal — `Saravutw/WAN2.2_I2V_LIGHTNING_4-8step_custom`

- **URL:** https://saravutw-wan2-2-i2v-lightning-4-8step-custom.hf.space
- **Endpoint:** `POST /gradio_api/call/generate_video` + SSE poll
- **Tiempo total** (upload → evento complete → mp4 descargado): **13.9 s**
- **Parámetros:** 16 args de `wan_gen.py`; `duration_s=2.0`, seed=42,
  steps=4, safe_mode=True
- **Salida `clip-ejemplo.mp4`** (ffprobe):
  - codec: h264 · contenedor: mp4
  - resolución: 640×640 · fps: 16 · duración: 2.0625 s
  - tamaño: 73,976 B (≈72 KB)
- **Evidencia de movimiento:** frame 0 (239,488 B PNG) ≠ frame 30
  (266,798 B PNG) — contenido distinto, no imagen congelada.

## Vía alternativa — `linoyts/wan2-2-i2v-rCM`

- **URL:** https://linoyts-wan2-2-i2v-rcm.hf.space
- **Endpoint:** `POST /gradio_api/call/generate_video` + SSE poll
- **Tiempo total:** **25.0 s**
- **Parámetros:** 9 args — image, prompt, steps=4, negative, duration=2.0,
  gs1=1, gs2=1, seed=7, randomize=False
- **Salida `clip-alternativo-linoyts.mp4`** (ffprobe):
  - codec: h264 · contenedor: mp4
  - resolución: 640×640 · fps: 16 · duración: 2.0625 s
  - tamaño: 110,470 B (≈108 KB)
- **Evidencia:** pose distinta a la imagen fuente (giro de cabeza lateral).

## Entrada (zero-auth)

- **Pollinations:** `image.pollinations.ai/prompt/…?width=640&height=640&seed=7`
- Descarga: 31,922 B JPEG → `input-scene.jpg` (sin `POLL_TOKEN`).

## Observaciones de cuota

- Ambas llamadas ZeroGPU funcionaron **anónimas** (sin token). HF aplica cuota
  diaria por IP a usuarios anónimos; si se agota, el SSE devuelve
  `event: error` y toca cambiar de Space (hay 5 más verificados en
  `fuentes.md`) o aportar `HF_TOKEN` (ver `HANDOFF-usuario.md`).
- Latencias medidas en horario 00:42–00:45 UTC; en horas pico la cola ZeroGPU
  puede añadir decenas de segundos.
