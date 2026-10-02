import {constants} from 'node:fs';
import {access, mkdir} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {bundle} from '@remotion/bundler';
import {
  ensureBrowser,
  renderMedia,
  selectComposition,
  type RenderMediaOnProgress,
} from '@remotion/renderer';
import type {VideoProject} from '../remotion/types.js';

export type RenderVideoOptions = {
  project: VideoProject;
  outputPath: string;
  assetsDirectory: string;
  entryPoint?: string;
  onProgress?: (progress: number) => void;
};

const BROWSER_CANDIDATES = [
  process.env.REMOTION_BROWSER_EXECUTABLE,
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  '/snap/bin/chromium',
  '/home/ubuntu/.local/bin/google-chrome',
].filter((candidate): candidate is string => Boolean(candidate));

const canExecute = async (path: string): Promise<boolean> => {
  try {
    await access(path, constants.X_OK);
    return true;
  } catch {
    return false;
  }
};

export const resolveBrowserExecutable = async (): Promise<string | null> => {
  for (const candidate of BROWSER_CANDIDATES) {
    if (await canExecute(candidate)) {
      return candidate;
    }
  }
  const status = await ensureBrowser({
    chromeMode: 'headless-shell',
    logLevel: 'warn',
  });
  return status.type === 'local-puppeteer-browser' ||
    status.type === 'user-defined-path'
    ? status.path
    : null;
};

export const renderVideo = async ({
  project,
  outputPath,
  assetsDirectory,
  entryPoint = resolve(process.cwd(), 'src/remotion/index.ts'),
  onProgress,
}: RenderVideoOptions): Promise<void> => {
  await mkdir(dirname(outputPath), {recursive: true});
  const serveUrl = await bundle({
    entryPoint,
    publicDir: assetsDirectory,
    webpackOverride: (configuration) => ({
      ...configuration,
      resolve: {
        ...configuration.resolve,
        extensionAlias: {
          '.js': ['.ts', '.tsx', '.js'],
        },
      },
    }),
  });
  const browserExecutable = await resolveBrowserExecutable();
  const browserOptions = browserExecutable
    ? {browserExecutable, chromeMode: 'chrome-for-testing' as const}
    : {chromeMode: 'headless-shell' as const};
  const composition = await selectComposition({
    serveUrl,
    id: 'ShortVideo',
    inputProps: project,
    logLevel: 'warn',
    ...browserOptions,
  });
  let lastPercentage = -1;
  const handleProgress: RenderMediaOnProgress = ({progress}) => {
    const percentage = Math.floor(progress * 100);
    if (percentage >= lastPercentage + 5 || percentage === 100) {
      lastPercentage = percentage;
      onProgress?.(percentage);
    }
  };

  await renderMedia({
    composition,
    serveUrl,
    codec: 'h264',
    audioCodec: 'aac',
    outputLocation: outputPath,
    inputProps: project,
    overwrite: true,
    concurrency: 1,
    crf: 24,
    x264Preset: 'ultrafast',
    pixelFormat: 'yuv420p',
    logLevel: 'warn',
    onProgress: handleProgress,
    ...browserOptions,
  });
};
