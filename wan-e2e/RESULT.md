# RESULT — Pipeline Wan 2.2 sin GPU local, zero-auth

**Fecha:** 2026-09-23 (UTC)
**Sesión:** continuación de `devin-1d6ca3656226485c8225f07b4a26c98c` (la sesión
anterior se durmió tras una caída de VM antes de poder ejecutar nada).

## Veredicto

✅ **CLIP REAL GENERADO** — el pipeline imagen→video Wan 2.2 funciona end-to-end
**sin GPU local, sin login, sin token, sin tarjeta** (Nivel 1 del Bootstrap
Protocol). Se verificaron **dos vías independientes** dentro de Nivel 1:

| Vía | Space | Resultado | Tiempo total |
|-----|-------|-----------|--------------|
| Principal | `Saravutw/WAN2.2_I2V_LIGHTNING_4-8step_custom` (el que ya usa `wan_gen.py`) | `clip-ejemplo.mp4` — 640×640, h264, 16 fps, 2.06 s, 74 KB | 13.9 s |
| Alternativa | `linoyts/wan2-2-i2v-rCM` | `clip-alternativo-linoyts.mp4` — 640×640, h264, 16 fps, 2.06 s, 110 KB | 25.0 s |

Ambos mp4 se verificaron con `ffprobe` y extrayendo frames (los frames difieren
entre sí → movimiento real, no imagen estática). `frame-muestra.png` es el
frame 30 del clip principal.

## Pipeline completo probado (todo zero-auth)

1. **Imagen de entrada** — Pollinations.ai sin token:
   `image.pollinations.ai/prompt/...` → `input-scene.jpg` (JPEG 640×640, 32 KB).
2. **Animación i2v** — Space de Hugging Face vía API Gradio HTTP plana
   (`/gradio_api/upload` → `/gradio_api/call/generate_video` → SSE poll →
   `/gradio_api/file=…`). Sin `HF_TOKEN` (la variable no estaba definida).
3. **Salida** — mp4 h264 descargado directo del Space.

Es exactamente el mismo camino que ya ejecuta `wan_gen.py` en producción
(`engine=wan`), así que el hallazgo principal es: **la vía Nivel 1 sigue viva
hoy** y además hay un Space alternativo i2v verificado que puede servir de
respaldo si el principal se queda sin cuota.

## Qué NO funcionó

- Nada relevante. Los únicos fallos fueron probes a hostnames de Spaces mal
  adivinados (404) — ver `log-intentos.md`. No hubo bloqueos estructurales:
  no se pidió login, verificación, captcha ni pago en ninguna vía.

## Qué quedó sin probar (y por qué)

- **wan2.video y clones**: no hizo falta — Nivel 1 ya tenía 2 vías exitosas
  antes de probar frontends web. Quedan como siguiente opción documentada en
  `HANDOFF-usuario.md` si ambos Spaces mueren.
- **Generación vía app desplegada** (`video.byrongonzalez.dev`, engine=auto):
  el pipeline del Space es idéntico al de `wan_gen.py`; probar el endpoint
  de Render es QA de la app, no del pipeline Wan.

## Archivos del bundle

- `clip-ejemplo.mp4` — clip real, vía principal (13.9 s).
- `clip-alternativo-linoyts.mp4` — clip real, vía alternativa (25.0 s).
- `input-scene.jpg` — imagen semilla usada (Pollinations, zero-auth).
- `frame-muestra.png` — frame 30 del clip principal (evidencia de movimiento).
- `wan_space_client.py` — cliente Gradio HTTP plano genérico reutilizable
  (el mismo patrón que `wan_gen.py`, parametrizable a otros Spaces).
- `metrics.md`, `log-intentos.md`, `fuentes.md`, `HANDOFF-usuario.md`.
