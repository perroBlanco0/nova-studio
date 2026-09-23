# fuentes.md — URLs verificadas con fecha

Todas verificadas el **2026-09-23 UTC** con llamadas reales (HTTP 200 +, en dos
casos, generación completa). Estado de cada una según ese probe.

## Vías exitosas (clip real generado)

| Fuente | URL | Estado 2026-09-23 |
|--------|-----|-------------------|
| Saravutw/WAN2.2_I2V_LIGHTNING_4-8step_custom (Space) | https://saravutw-wan2-2-i2v-lightning-4-8step-custom.hf.space | ✅ clip en 13.9 s, zero-auth |
| linoyts/wan2-2-i2v-rCM (Space) | https://linoyts-wan2-2-i2v-rcm.hf.space | ✅ clip en 25.0 s, zero-auth |
| Pollinations (imagen) | https://image.pollinations.ai/prompt/… | ✅ JPEG 640×640 sin token |

## Spaces vivos mapeados (API responde, endpoint de generación presente)

Verificados con `GET /gradio_api/info` → 200 (no se corrió generación completa):

| Space | URL | Endpoint principal |
|-------|-----|--------------------|
| zerogpu-aoti/wan2-2-fp8da-aoti-faster | https://zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space | `/generate_video` (t2v+i2v) |
| Wan-AI/Wan2.1 (oficial) | https://wan-ai-wan2-1.hf.space | `/t2v_generation_async`, `/i2v_generation_async` |
| multimodalart/wan2-1-fast | https://multimodalart-wan2-1-fast.hf.space | `/generate_video` |
| observantdistressed/wan2-2-i2v-v3 | https://observantdistressed-wan2-2-i2v-v3.hf.space | `/generate_video` (i2v) |
| alibaba-pai/Wan2.1-Fun-1.3B-InP | https://alibaba-pai-wan2-1-fun-1-3b-inp.hf.space | `/generate` |
| KingNish/wan2-2-fast | https://kingnish-wan2-2-fast.hf.space | `/generate_video` |

## APIs públicas de referencia

- Búsqueda de Spaces (resuelve hostnames reales, evita el error del intento 2):
  `https://huggingface.co/api/spaces?search=wan&sort=likes&direction=-1`
- Patrón Gradio HTTP plano usado:
  `POST {base}/gradio_api/upload` → `POST {base}/gradio_api/call/<fn>` →
  `GET {base}/gradio_api/call/<fn>/<event_id>` (SSE) →
  `GET {base}/gradio_api/file=<path>`.

## Frontends citados (no probados — innecesarios tras 2 éxitos en Nivel 1)

- https://wan2.video — frontend público Wan (estado por verificar).
- https://modelscope.cn — demos Wan 2.1/2.2 de Alibaba.

## Repos/código local relacionado

- `wan_gen.py` (raíz del repo) — cliente del Space Saravutw usado en producción.
- `main.py` `_animate_wan` / `engine=wan` — integración en la app.
