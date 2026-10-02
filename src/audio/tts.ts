import {spawn} from 'node:child_process';
import {mkdir, readFile, rm} from 'node:fs/promises';
import {dirname} from 'node:path';

export type CaptionWord = {
  text: string;
  startMs: number;
  endMs: number;
};

export type NarrationResult = {
  audioPath: string;
  captions: CaptionWord[];
  durationMs: number;
  engine: 'edge-tts' | 'offline-mock';
};

export type SynthesizeOptions = {
  text: string;
  outputPath: string;
  voice: string;
  rate?: string;
  targetDurationMs: number;
  offline?: boolean;
};

type CommandResult = {
  stdout: string;
  stderr: string;
};

const runCommand = (
  command: string,
  args: readonly string[],
): Promise<CommandResult> =>
  new Promise((resolve, reject) => {
    const child = spawn(command, args, {stdio: ['ignore', 'pipe', 'pipe']});
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) {
        resolve({stdout, stderr});
      } else {
        reject(new Error(`${command} terminó con código ${code}: ${stderr}`));
      }
    });
  });

export const parseTimestampMs = (value: string): number => {
  const parts = value.trim().replace(',', '.').split(':');
  if (parts.length !== 3) {
    throw new Error(`Timestamp inválido: ${value}`);
  }
  const hours = Number(parts[0]);
  const minutes = Number(parts[1]);
  const seconds = Number(parts[2]);
  if (![hours, minutes, seconds].every(Number.isFinite)) {
    throw new Error(`Timestamp inválido: ${value}`);
  }
  return Math.round(((hours * 60 + minutes) * 60 + seconds) * 1000);
};

const plainText = (value: string): string =>
  value
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim();

const wordsForCue = (
  text: string,
  startMs: number,
  endMs: number,
): CaptionWord[] => {
  const words = plainText(text).split(/\s+/).filter(Boolean);
  if (words.length === 0) {
    return [];
  }
  const weights = words.map((word) => Math.max(1, word.replace(/\W/gu, '').length));
  const totalWeight = weights.reduce((total, weight) => total + weight, 0);
  const duration = Math.max(words.length, endMs - startMs);
  let elapsed = 0;

  return words.map((word, index) => {
    const weight = weights[index] ?? 1;
    const wordStart = startMs + Math.round((elapsed / totalWeight) * duration);
    elapsed += weight;
    const wordEnd =
      index === words.length - 1
        ? endMs
        : startMs + Math.round((elapsed / totalWeight) * duration);
    return {text: word, startMs: wordStart, endMs: wordEnd};
  });
};

export const parseVttCaptions = (content: string): CaptionWord[] => {
  const lines = content.replace(/^\uFEFF/, '').split(/\r?\n/);
  const captions: CaptionWord[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]?.trim() ?? '';
    const match = line.match(
      /(\d{2}:\d{2}:\d{2}[.,]\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}[.,]\d{3})/,
    );
    if (!match?.[1] || !match[2]) {
      continue;
    }
    const cueLines: string[] = [];
    index += 1;
    while (index < lines.length && (lines[index]?.trim() ?? '') !== '') {
      cueLines.push(lines[index] ?? '');
      index += 1;
    }
    captions.push(
      ...wordsForCue(
        cueLines.join(' '),
        parseTimestampMs(match[1]),
        parseTimestampMs(match[2]),
      ),
    );
  }

  return captions;
};

export const buildFallbackCaptions = (
  text: string,
  durationMs: number,
): CaptionWord[] => wordsForCue(text, 0, durationMs);

const probeDurationMs = async (audioPath: string): Promise<number> => {
  const result = await runCommand('ffprobe', [
    '-v',
    'error',
    '-show_entries',
    'format=duration',
    '-of',
    'default=noprint_wrappers=1:nokey=1',
    audioPath,
  ]);
  const seconds = Number(result.stdout.trim());
  if (!Number.isFinite(seconds) || seconds <= 0) {
    throw new Error('ffprobe no pudo calcular la duración de la narración');
  }
  return Math.round(seconds * 1000);
};

const edgeCommands = (
  voice: string,
  rate: string,
  text: string,
  audioPath: string,
  subtitlePath: string,
): ReadonlyArray<readonly [string, readonly string[]]> => {
  const args = [
    '--voice',
    voice,
    '--rate',
    rate,
    '--text',
    text,
    '--write-media',
    audioPath,
    '--write-subtitles',
    subtitlePath,
  ] as const;
  return [
    ['edge-tts', args],
    ['python3', ['-m', 'edge_tts', ...args]],
    ['python', ['-m', 'edge_tts', ...args]],
  ];
};

const synthesizeWithEdge = async (
  options: SynthesizeOptions,
): Promise<NarrationResult> => {
  const subtitlePath = `${options.outputPath}.vtt`;
  let lastError = 'edge-tts no está instalado';

  for (const [command, args] of edgeCommands(
    options.voice,
    options.rate ?? '+0%',
    options.text,
    options.outputPath,
    subtitlePath,
  )) {
    try {
      await runCommand(command, args);
      const captions = parseVttCaptions(await readFile(subtitlePath, 'utf8'));
      const durationMs = await probeDurationMs(options.outputPath);
      await rm(subtitlePath, {force: true});
      return {
        audioPath: options.outputPath,
        captions:
          captions.length > 0
            ? captions
            : buildFallbackCaptions(options.text, durationMs),
        durationMs,
        engine: 'edge-tts',
      };
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      await rm(options.outputPath, {force: true});
      await rm(subtitlePath, {force: true});
    }
  }

  throw new Error(lastError);
};

const synthesizeOfflineMock = async (
  options: SynthesizeOptions,
): Promise<NarrationResult> => {
  const durationMs = Math.max(1000, options.targetDurationMs);
  await runCommand('ffmpeg', [
    '-y',
    '-loglevel',
    'error',
    '-f',
    'lavfi',
    '-i',
    'anullsrc=channel_layout=stereo:sample_rate=44100',
    '-t',
    (durationMs / 1000).toFixed(3),
    '-codec:a',
    'libmp3lame',
    '-q:a',
    '9',
    options.outputPath,
  ]);
  return {
    audioPath: options.outputPath,
    captions: buildFallbackCaptions(options.text, durationMs),
    durationMs,
    engine: 'offline-mock',
  };
};

export const synthesizeNarration = async (
  options: SynthesizeOptions,
): Promise<NarrationResult> => {
  await mkdir(dirname(options.outputPath), {recursive: true});
  if (!options.offline) {
    try {
      return await synthesizeWithEdge(options);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.warn(`Edge-TTS no disponible (${message}); usando audio offline.`);
    }
  }
  return synthesizeOfflineMock(options);
};
