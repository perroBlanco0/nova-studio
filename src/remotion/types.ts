import type {CaptionWord} from '../audio/tts.js';
import type {CameraMotion} from '../generator/schema.js';

export type RenderScene = {
  sceneId: string;
  textToSpeak: string;
  imagePrompt: string;
  cameraMotion: CameraMotion;
  durationInSeconds: number;
  sfxTrigger: string | null;
  assetPath: string;
  startFrame: number;
  durationInFrames: number;
};

export type VideoProject = Record<string, unknown> & {
  title: string;
  fps: number;
  scenes: RenderScene[];
  captions: CaptionWord[];
  narrationPath: string | null;
  backgroundMusicPath: string | null;
  sfxPaths: Record<string, string>;
};

export const projectDurationInFrames = (project: VideoProject): number => {
  const lastScene = project.scenes.at(-1);
  return lastScene
    ? lastScene.startFrame + lastScene.durationInFrames
    : project.fps * 3;
};

export const DEFAULT_PROJECT: VideoProject = {
  title: 'NOVA Studio',
  fps: 30,
  scenes: [
    {
      sceneId: 'preview',
      textToSpeak: 'Generador de video gratuito',
      imagePrompt: 'abstract aurora',
      cameraMotion: 'zoom_in',
      durationInSeconds: 3,
      sfxTrigger: null,
      assetPath: 'placeholders/aurora.svg',
      startFrame: 0,
      durationInFrames: 90,
    },
  ],
  captions: [
    {text: 'Generador', startMs: 0, endMs: 900},
    {text: 'de', startMs: 900, endMs: 1200},
    {text: 'video', startMs: 1200, endMs: 2000},
    {text: 'gratuito', startMs: 2000, endMs: 3000},
  ],
  narrationPath: null,
  backgroundMusicPath: null,
  sfxPaths: {},
};
