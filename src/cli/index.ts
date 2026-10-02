#!/usr/bin/env node
import {mkdir, writeFile} from 'node:fs/promises';
import {basename, dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {synthesizeNarration} from '../audio/tts.js';
import {fetchSceneImages} from '../assets/images.js';
import {
  generateScript,
  type ScriptProvider,
} from '../generator/script.js';
import {createVideoProject} from '../render/project.js';
import {renderVideo} from '../render/render.js';

type CliOptions = {
  topic: string;
  output: string;
  provider: ScriptProvider;
  voice: string;
  rate: string;
  offline: boolean;
};

const HELP = `NOVA Studio — generador gratuito de videos verticales

Uso:
  npm run generate -- --topic "Los 3 errores al entrenar" --output ./output/video.mp4

Opciones:
  --topic       Tema del video
  --output      MP4 de salida (default: ./output/video.mp4)
  --provider    heuristic | groq | gemini (default: heuristic)
  --voice       Voz de Edge-TTS (default: es-MX-DaliaNeural)
  --rate        Velocidad Edge-TTS, por ejemplo +10% (default: +0%)
  --offline     No intenta usar Pollinations ni Edge-TTS
  --help        Muestra esta ayuda
`;

const valueAfter = (args: string[], index: number, flag: string): string => {
  const value = args[index + 1];
  if (!value || value.startsWith('--')) {
    throw new Error(`Falta el valor de ${flag}`);
  }
  return value;
};

export const parseCliOptions = (args: string[]): CliOptions => {
  const options: CliOptions = {
    topic: 'Tres curiosidades impactantes del espacio',
    output: resolve('output/video.mp4'),
    provider: 'heuristic',
    voice: 'es-MX-DaliaNeural',
    rate: '+0%',
    offline: false,
  };

  for (let index = 0; index < args.length; index += 1) {
    const argument = args[index];
    if (argument === '--help') {
      console.log(HELP);
      process.exit(0);
    }
    if (argument === '--offline') {
      options.offline = true;
      continue;
    }
    if (argument === '--topic') {
      options.topic = valueAfter(args, index, argument);
      index += 1;
      continue;
    }
    if (argument === '--output') {
      options.output = resolve(valueAfter(args, index, argument));
      index += 1;
      continue;
    }
    if (argument === '--voice') {
      options.voice = valueAfter(args, index, argument);
      index += 1;
      continue;
    }
    if (argument === '--rate') {
      options.rate = valueAfter(args, index, argument);
      index += 1;
      continue;
    }
    if (argument === '--provider') {
      const provider = valueAfter(args, index, argument);
      if (!['heuristic', 'groq', 'gemini'].includes(provider)) {
        throw new Error(`Proveedor inválido: ${provider}`);
      }
      options.provider = provider as ScriptProvider;
      index += 1;
      continue;
    }
    throw new Error(`Opción desconocida: ${argument}`);
  }
  return options;
};

const stableId = (value: string): string => {
  let hash = 2166136261;
  for (const character of value) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  const slug = value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 36);
  return `${slug || 'video'}-${(hash >>> 0).toString(16)}`;
};

export const run = async (options: CliOptions): Promise<void> => {
  const sourceDirectory = dirname(fileURLToPath(import.meta.url));
  const rootDirectory = resolve(sourceDirectory, '../..');
  const assetsDirectory = resolve(rootDirectory, 'assets');
  const runDirectory = resolve(
    assetsDirectory,
    'generated',
    stableId(options.topic),
  );
  await mkdir(runDirectory, {recursive: true});
  await mkdir(dirname(options.output), {recursive: true});

  console.log('1/4 Generando guion...');
  const script = await generateScript(options.topic, {
    provider: options.provider,
    ...(process.env.GROQ_API_KEY
      ? {groqApiKey: process.env.GROQ_API_KEY}
      : {}),
    ...(process.env.GEMINI_API_KEY
      ? {geminiApiKey: process.env.GEMINI_API_KEY}
      : {}),
  });
  await writeFile(
    resolve(runDirectory, 'script.json'),
    `${JSON.stringify(script, null, 2)}\n`,
  );

  console.log('2/4 Preparando imágenes...');
  const sceneAssets = await fetchSceneImages(
    script,
    runDirectory,
    assetsDirectory,
    options.offline,
  );

  console.log('3/4 Sintetizando narración...');
  const expectedDurationMs = Math.round(
    script.scenes.reduce(
      (total, scene) => total + scene.durationInSeconds,
      0,
    ) * 1000,
  );
  const narration = await synthesizeNarration({
    text: script.scenes.map((scene) => scene.textToSpeak).join(' '),
    outputPath: resolve(runDirectory, 'narrator.mp3'),
    voice: options.voice,
    rate: options.rate,
    targetDurationMs: expectedDurationMs,
    offline: options.offline,
  });
  const project = createVideoProject(
    script,
    sceneAssets,
    narration,
    assetsDirectory,
  );

  console.log('4/4 Renderizando con Remotion + FFmpeg...');
  await renderVideo({
    project,
    outputPath: options.output,
    assetsDirectory,
    entryPoint: resolve(rootDirectory, 'src/remotion/index.ts'),
    onProgress: (percentage) => process.stdout.write(`\rRender ${percentage}%`),
  });
  process.stdout.write('\n');

  const manifestPath = options.output.replace(/\.mp4$/i, '.json');
  await writeFile(
    manifestPath,
    `${JSON.stringify(
      {
        title: script.title,
        output: basename(options.output),
        provider: options.provider,
        narrationEngine: narration.engine,
        offline: options.offline,
        project,
        sceneAssets,
      },
      null,
      2,
    )}\n`,
  );
  console.log(`Video listo: ${options.output}`);
};

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  run(parseCliOptions(process.argv.slice(2))).catch((error: unknown) => {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`Error: ${message}`);
    process.exitCode = 1;
  });
}
