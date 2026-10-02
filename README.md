# NOVA Studio

NOVA Studio incluye dos flujos:

- La aplicación FastAPI existente para crear personajes y clips.
- Un generador CLI independiente de videos verticales con Remotion, Edge-TTS, Pollinations y fallbacks locales.

El generador produce MP4 de **1080x1920**, **30 fps** y no requiere servicios pagos, GPU ni tarjeta de crédito.

La interfaz web también incluye **Paisajes** como módulo adicional. Permite
crear un clip anime, realista o fantástico sin personaje, con paneo lateral
sin zoom, música incluida, voz opcional y fallback local si Pollinations no
responde.

## Inicio rápido

Requisitos:

- Node.js 20 o superior.
- FFmpeg y ffprobe disponibles en `PATH`.
- Opcional: Python 3 con `edge-tts` para narración neural.

```sh
npm install
npm run generate
```

El resultado se guarda en `output/video.mp4`. Si Edge-TTS o Pollinations no están disponibles, el comando termina usando audio mock silencioso, subtítulos temporizados y gráficos locales.

Para activar la narración neural gratuita:

```sh
python3 -m pip install edge-tts
npm run generate -- --topic "Los 3 errores más comunes al entrenar calistenia"
```

## CLI

```sh
npm run generate -- \
  --topic "Curiosidades impactantes del espacio" \
  --style anime \
  --output ./output/espacio.mp4 \
  --voice es-MX-DaliaNeural \
  --rate +5%
```

| Flag | Valor por defecto | Descripción |
| --- | --- | --- |
| `--topic` | Curiosidades del espacio | Tema del guion |
| `--output` | `./output/video.mp4` | Ruta del MP4 |
| `--provider` | `heuristic` | `heuristic`, `groq` o `gemini` |
| `--style` | `general` | `general`, `anime`, `realistic`, `fantasy` o `all` |
| `--voice` | `es-MX-DaliaNeural` | Voz compatible con Edge-TTS |
| `--rate` | `+0%` | Velocidad de voz |
| `--offline` | desactivado | Evita todas las llamadas de red |
| `--help` | — | Ayuda rápida |

Ejemplo totalmente offline:

```sh
npm run generate -- --offline --topic "Tres hábitos para empezar el día"
```

Cada MP4 incluye un manifiesto JSON con el guion, escenas, assets utilizados, timings y motor de narración.

Para generar automáticamente los tres estilos de paisaje:

```sh
npm run generate -- \
  --topic "Un valle atravesado por cascadas" \
  --style all \
  --output ./output/paisaje.mp4
```

El comando crea `paisaje-anime.mp4`, `paisaje-realistic.mp4` y
`paisaje-fantasy.mp4`. Los presets fuerzan paisajes sin personas y usan
fondos locales del mismo estilo si Pollinations no responde.

## Servicios gratuitos y fallbacks

### Guion

El proveedor por defecto es `heuristic`: genera localmente un JSON validado con Zod y no necesita claves.

Groq y Gemini son adaptadores opcionales para sus planes gratuitos:

```sh
GROQ_API_KEY=... npm run generate -- --provider groq --topic "Tema"
GEMINI_API_KEY=... npm run generate -- --provider gemini --topic "Tema"
```

Si la clave, red o endpoint falla, el pipeline vuelve automáticamente al generador local.

### Imágenes

Con internet, las imágenes se solicitan por GET a Pollinations.ai y se guardan en caché dentro de `assets/generated/`. Sin internet se usan los SVG procedurales de `assets/placeholders/`.

### Voz y subtítulos

El módulo intenta, en este orden:

1. `edge-tts`.
2. `python3 -m edge_tts`.
3. `python -m edge_tts`.
4. Audio mock local generado con FFmpeg.

Los WebVTT de Edge-TTS se convierten a palabras con tiempos individuales. El fallback reparte las palabras de forma determinista durante la duración estimada.

Para listar voces:

```sh
edge-tts --list-voices
```

### Música y efectos

Los archivos de `assets/audio/` son tonos procedurales incluidos en el repositorio. Puedes reemplazar:

- `background.mp3`
- `impact.wav`
- `swoosh.wav`
- `riser.wav`

Conserva los nombres o actualiza `src/render/project.ts`. La música se reproduce al 15% mientras hay narración.

## Arquitectura

```text
src/
  generator/     Generación y validación del guion
  assets/        Pollinations, caché y placeholders
  audio/         Edge-TTS, WebVTT y fallback offline
  remotion/      Composición 9:16 y componentes visuales
  render/        Preparación del proyecto y render headless
  cli/           Orquestador npm run generate
assets/
  placeholders/  Imágenes SVG locales
  audio/         Música y SFX procedurales
```

La composición aplica paneo lateral suave sin acercamiento, subtítulos activos de alto contraste, barra de progreso, voz, música con ducking y efectos al comenzar escenas.

## Desarrollo y pruebas

```sh
npm run typecheck
npm test
```

Vitest cubre:

- Validación estricta del JSON narrativo.
- Parseo de timestamps y captions WebVTT.
- Render headless real de tres segundos a 1080x1920.

Para abrir Remotion Studio:

```sh
npm run remotion:studio
```

## Aplicación FastAPI existente

```sh
python3 -m pip install -r requirements.txt
uvicorn main:app --reload
```

Las pruebas Python siguen disponibles con:

```sh
python3 -m pytest
```
