# log-intentos.md — Registro de intentos

Misión: pipeline Wan 2.1/2.2 end-to-end sin GPU local ni identidad del usuario.
Fecha: 2026-09-23 (UTC). Todos los intentos sin `HF_TOKEN`, sin login, sin pago.

## Contexto heredado

- Sesión anterior (`devin-1d6ca3656226485c8225f07b4a26c98c`): no llegó a ejecutar
  intentos — la VM perdió conexión (todos los tools fallaban con "connection
  unavailable"), reportó el blocker y fue dormida por el usuario. Esta sesión
  retoma desde cero con el mismo protocolo.
- Historial del repo: la vía HF Space → quota agotada ya existía (`wan_gen.py`,
  commits `e384175`, `7f25b9c`…). El objetivo era verificar si Nivel 1 sigue vivo.

## Intentos (cronológico)

### Intento 1 — Probe del Space principal de la app
- **Qué:** `GET https://saravutw-wan2-2-i2v-lightning-4-8step-custom.hf.space/gradio_api/info`
- **Opción:** Space `Saravutw/WAN2.2_I2V_LIGHTNING_4-8step_custom` (Nivel 1)
- **Resultado:** ✅ HTTP 200; endpoint `/generate_video` con 16 parámetros,
  coincide con el array `data` de `wan_gen.py`.
- **No repetir:** nada — vía viva.

### Intento 2 — Probes a Spaces por hostname adivinado
- **Qué:** `GET /gradio_api/info` en `multimodalart-wan2-2-first-last-frame.hf.space`
  y `wan-ai-wan2-2-animate.hf.space`
- **Opción:** guesses directos de subdominio (Nivel 1)
- **Por qué falló:** HTTP 404 — los subdominios no existen (el Space real de
  multimodalart es `wan-2-2-first-last-frame`, guion distinto; el de Wan-AI es
  `wan2-2-animate` bajo otro owner).
- **No repetir:** adivinar subdominios; usar `huggingface.co/api/spaces?search=`
  para resolver hostnames reales.

### Intento 3 — Imagen semilla vía Pollinations (zero-auth)
- **Qué:** descarga de `image.pollinations.ai/prompt/<prompt>?width=640&height=640&seed=7`
- **Opción:** frontend de imagen sin login (Nivel 1)
- **Resultado:** ✅ JPEG real de 31,922 B (verificado magic `\xff\xd8`), guardado
  como `input-scene.jpg`.
- **Nota:** responde incluso sin `POLL_TOKEN` con modelo por defecto.

### Intento 4 — Generación i2v en el Space principal (producción)
- **Qué:** `wan_gen.generate('scene.png', motion, 'clip-ejemplo.mp4', seed=42,
  duration_s=2.0, safe_mode=True)` → upload → call → SSE → download.
- **Opción:** `Saravutw/WAN2.2_I2V_LIGHTNING_4-8step_custom` (Nivel 1)
- **Resultado:** ✅ **clip real en 13.9 s** — 73,976 B, h264, 640×640, 16 fps,
  2.06 s. Frames 0 y 30 difieren → movimiento real.
- **Sin auth:** `HF_TOKEN` no estaba definida en el entorno.

### Intento 5 — Mapeo de Spaces alternativos (API de HF)
- **Qué:** `GET huggingface.co/api/spaces?search=wan&sort=likes` → 40+ Spaces;
  probe de `/gradio_api/info` a 7 candidatos i2v/t2v.
- **Resultado:** ✅ 7 Spaces vivos con endpoint de generación:
  `zerogpu-aoti/wan2-2-fp8da-aoti-faster`, `linoyts/wan2-2-i2v-rCM`,
  `Wan-AI/Wan2.1` (oficial, t2v+i2v), `multimodalart/wan2-1-fast`,
  `observantdistressed/wan2-2-i2v-v3`, `alibaba-pai/Wan2.1-Fun-1.3B-InP`,
  `KingNish/wan2-2-fast`.
- **No repetir:** ninguno descartado — todos respondieron 200.

### Intento 6 — Generación i2v en Space alternativo
- **Qué:** mismo patrón Gradio contra `linoyts-wan2-2-i2v-rcm.hf.space`
  (`wan_space_client.py`, 9 parámetros: image, prompt, steps, neg, dur, gs1,
  gs2, seed, randomize).
- **Opción:** `linoyts/wan2-2-i2v-rCM` (Nivel 1, segunda vía distinta)
- **Resultado:** ✅ **clip real en 25.0 s** — 110,470 B, h264, 640×640, 16 fps,
  2.06 s. La pose cambió respecto a la imagen fuente (giro de cabeza).

## Resumen del estado de opciones

- **Nivel 1: NO agotado — 2 vías verificadas con éxito**, 5 más mapeadas y
  vivas. No se llegó a Nivel 2 ni Nivel 3 porque Nivel 1 ya cumplió la misión.
- **Reinicios usados:** 0 (no hubo fallos estructurales).
- **Fallos registrados:** solo los 404 de intento 2 (error de hostname, no
  estructural).
