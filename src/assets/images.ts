import {copyFile, mkdir, stat, writeFile} from 'node:fs/promises';
import {join, relative, sep} from 'node:path';
import type {VideoScript} from '../generator/schema.js';
import type {VisualStyle} from '../generator/style.js';

export type SceneAsset = {
  sceneId: string;
  assetPath: string;
  source: 'pollinations' | 'placeholder';
};

const PLACEHOLDERS = ['aurora.svg', 'sunrise.svg', 'grid.svg'] as const;
const LANDSCAPE_PLACEHOLDERS = {
  anime: 'landscape-anime.png',
  realistic: 'landscape-realistic.png',
  fantasy: 'landscape-fantasy.png',
} as const;

const hashSeed = (value: string): number => {
  let hash = 2166136261;
  for (const character of value) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return Math.abs(hash) % 1_000_000;
};

const downloadImage = async (
  prompt: string,
  destination: string,
): Promise<void> => {
  const url = new URL(
    `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}`,
  );
  url.searchParams.set('width', '1080');
  url.searchParams.set('height', '1920');
  url.searchParams.set('nologo', 'true');
  url.searchParams.set('seed', String(hashSeed(prompt)));
  url.searchParams.set('model', 'flux');

  const response = await fetch(url, {
    headers: {'User-Agent': 'nova-studio-free-video-generator/1.0'},
    signal: AbortSignal.timeout(45_000),
  });
  if (!response.ok) {
    throw new Error(`Pollinations respondió ${response.status}`);
  }
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.startsWith('image/')) {
    throw new Error(`Pollinations devolvió ${contentType || 'contenido desconocido'}`);
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength < 1024) {
    throw new Error('La imagen descargada está vacía');
  }
  await writeFile(destination, bytes);
};

const hasCachedImage = async (path: string): Promise<boolean> => {
  try {
    const details = await stat(path);
    return details.isFile() && details.size >= 1024;
  } catch {
    return false;
  }
};

const toAssetPath = (assetsDirectory: string, path: string): string =>
  relative(assetsDirectory, path).split(sep).join('/');

export const fetchSceneImages = async (
  script: VideoScript,
  runDirectory: string,
  assetsDirectory: string,
  offline: boolean,
  style: VisualStyle = 'general',
): Promise<SceneAsset[]> => {
  await mkdir(runDirectory, {recursive: true});
  const results: SceneAsset[] = [];

  for (let index = 0; index < script.scenes.length; index += 1) {
    const scene = script.scenes[index];
    if (!scene) {
      continue;
    }
    const remoteName = `${scene.sceneId}.jpg`;
    const remoteDestination = join(runDirectory, remoteName);

    if (await hasCachedImage(remoteDestination)) {
      results.push({
        sceneId: scene.sceneId,
        assetPath: toAssetPath(assetsDirectory, remoteDestination),
        source: 'pollinations',
      });
      continue;
    }

    if (!offline) {
      try {
        await downloadImage(scene.imagePrompt, remoteDestination);
        results.push({
          sceneId: scene.sceneId,
          assetPath: toAssetPath(assetsDirectory, remoteDestination),
          source: 'pollinations',
        });
        continue;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.warn(`${scene.sceneId}: ${message}; usando placeholder local.`);
      }
    }

    const landscapePlaceholder =
      style === 'general' ? null : LANDSCAPE_PLACEHOLDERS[style];
    const placeholder =
      landscapePlaceholder ??
      PLACEHOLDERS[index % PLACEHOLDERS.length] ??
      'aurora.svg';
    const extension = placeholder.endsWith('.png') ? 'png' : 'svg';
    const localName = `${scene.sceneId}.${extension}`;
    await copyFile(
      join(assetsDirectory, 'placeholders', placeholder),
      join(runDirectory, localName),
    );
    results.push({
      sceneId: scene.sceneId,
      assetPath: toAssetPath(
        assetsDirectory,
        join(runDirectory, localName),
      ),
      source: 'placeholder',
    });
  }

  return results;
};
