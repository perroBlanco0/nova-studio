# HANDOFF-usuario.md — Qué requiere que un humano toque algo

El pipeline **ya funciona sin ti** (ver `RESULT.md`). Esto es lo único que
necesitaría tu identidad si algún día las vías gratuitas se agotan o quieres
más calidad/cuota. Ordenado de menor a mayor fricción.

## 1. HF_TOKEN para más cuota ZeroGPU (GRATIS, 2 min) — opcional pero recomendado

Las llamadas anónimas a Spaces ZeroGPU tienen cuota diaria por IP. Con token
propio la cuota es mayor y separada:

1. Crea cuenta en https://huggingface.co/join (email + contraseña — requiere
   verificación de email, por eso no lo hice yo).
2. Genera un token **read**: https://huggingface.co/settings/tokens → "New
   token" → tipo Read.
3. En Render: variable de entorno `HF_TOKEN=<token>` (ya soportada por
   `wan_gen.py` y `_motion_available()`).

## 2. Frontends web públicos (GRATIS, solo necesitan tu navegador)

Si los Spaces mueren, puedes generar clips manualmente y subirlos vía
`/api/upload`:

- **wan2.video** — frontend público de Wan (verificar en el momento; algunos
  frontends clónicos piden login después de N clips).
- **La propia UI de cada Space** en el navegador (misma cuota ZeroGPU, pero
  a veces la cola anónima web difiere de la API).
- **ModelScope** (modelscope.cn, modelo Wan oficial de Alibaba) — la web permite
  probar demos; algunas funciones piden cuenta gratuita.

## 3. Kaggle (GRATIS con teléfono verificado) — ya está cableado en la app

La app ya tiene el engine Kaggle (`_animate_kaggle`, `KAGGLE_VIDEO_URL`,
commits `e384175`…`2cbb276`). Falta solo tu parte:

1. Registro en https://www.kaggle.com — pide verificación por SMS (usa tu
   número real; no intenté ni intentaré suplantarlo).
2. Corre el notebook Wan 2.2 con GPU T4 gratis (~30 h/semana) exponiendo
   `/generate`, `/result`, `/health` por un túnel.
3. Regístralo: `POST /api/kaggle/register {"url": "https://<tunel>", "secret": …}`.

## 4. Colab / Lightning AI (GRATIS con cuenta Google)

Misma idea que Kaggle: notebook con GPU T4 + túnel ngrok/localtunnel hacia
`/api/kaggle/register`. Requiere tu cuenta Google.

## 5. Pago por uso (si quieres producción estable sin cuotas)

- **fal.ai** — ya cableado (`engine=fal`, `FAL_KEY`). ~$0.05/video
  (fal.run/`fal-ai/wan-i2v`). Requiere tarjeta — no puedo aceptar ToS ni pagar.
- **Replicate** — `wan-video/wan-2.2-i2v-fast` por API key, similar a fal.
- **Vast.ai / RunPod** — GPU por hora (~$0.2–0.5/h) para self-host de Wan 2.2;
  máximo control, requiere tarjeta.

## Lo que NO hice (y no haré)

- Crear cuentas con emails temporales o datos de terceros.
- Pasar captchas, verificaciones SMS/email ni aceptar ToS.
- Usar tu Gmail/GitHub (no tengo acceso a nada tuyo en esta sesión).
