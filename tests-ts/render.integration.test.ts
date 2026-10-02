import {spawn} from 'node:child_process';
import {mkdir, rm, stat} from 'node:fs/promises';
import {resolve} from 'node:path';
import {afterAll, describe, expect, it} from 'vitest';
import {DEFAULT_PROJECT} from '../src/remotion/types.js';
import {renderVideo} from '../src/render/render.js';

const outputDirectory = resolve('output/test-render');
const outputPath = resolve(outputDirectory, 'three-seconds.mp4');

const ffprobe = (path: string): Promise<{duration: number; dimensions: string}> =>
  new Promise((resolveResult, reject) => {
    const child = spawn('ffprobe', [
      '-v',
      'error',
      '-show_entries',
      'format=duration:stream=width,height',
      '-of',
      'default=noprint_wrappers=1',
      path,
    ]);
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
      if (code !== 0) {
        reject(new Error(stderr));
        return;
      }
      const duration = Number(stdout.match(/duration=([0-9.]+)/)?.[1]);
      const width = stdout.match(/width=(\d+)/)?.[1];
      const height = stdout.match(/height=(\d+)/)?.[1];
      resolveResult({duration, dimensions: `${width}x${height}`});
    });
  });

afterAll(async () => {
  await rm(outputDirectory, {recursive: true, force: true});
});

describe('Remotion integration', () => {
  it('renders a three-second vertical MP4 headlessly', async () => {
    await mkdir(outputDirectory, {recursive: true});
    await renderVideo({
      project: DEFAULT_PROJECT,
      outputPath,
      assetsDirectory: resolve('assets'),
      entryPoint: resolve('src/remotion/index.ts'),
    });

    const file = await stat(outputPath);
    const media = await ffprobe(outputPath);
    expect(file.size).toBeGreaterThan(10_000);
    expect(media.duration).toBeGreaterThanOrEqual(2.9);
    expect(media.duration).toBeLessThanOrEqual(3.1);
    expect(media.dimensions).toBe('1080x1920');
  });
});
