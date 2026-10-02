import {relative, sep} from 'node:path';
import type {NarrationResult} from '../audio/tts.js';
import type {SceneAsset} from '../assets/images.js';
import type {VideoScript} from '../generator/schema.js';
import type {RenderScene, VideoProject} from '../remotion/types.js';

const toStaticPath = (assetsDirectory: string, path: string): string =>
  relative(assetsDirectory, path).split(sep).join('/');

export const createVideoProject = (
  script: VideoScript,
  sceneAssets: SceneAsset[],
  narration: NarrationResult,
  assetsDirectory: string,
  fps = 30,
): VideoProject => {
  const requestedSeconds = script.scenes.reduce(
    (total, scene) => total + scene.durationInSeconds,
    0,
  );
  const targetSeconds = Math.max(3, narration.durationMs / 1000);
  const scale = requestedSeconds > 0 ? targetSeconds / requestedSeconds : 1;
  const targetFrames = Math.max(1, Math.round(targetSeconds * fps));
  let startFrame = 0;

  const scenes: RenderScene[] = script.scenes.map((scene, index) => {
    const asset = sceneAssets.find((candidate) => candidate.sceneId === scene.sceneId);
    if (!asset) {
      throw new Error(`No hay imagen para ${scene.sceneId}`);
    }
    const remainingFrames = targetFrames - startFrame;
    const durationInFrames =
      index === script.scenes.length - 1
        ? Math.max(1, remainingFrames)
        : Math.max(1, Math.round(scene.durationInSeconds * scale * fps));
    const rendered: RenderScene = {
      ...scene,
      sfxTrigger: scene.sfxTrigger ?? null,
      durationInSeconds: durationInFrames / fps,
      assetPath: asset.assetPath,
      startFrame,
      durationInFrames,
    };
    startFrame += durationInFrames;
    return rendered;
  });

  return {
    title: script.title,
    fps,
    scenes,
    captions: narration.captions,
    narrationPath: toStaticPath(assetsDirectory, narration.audioPath),
    backgroundMusicPath: 'audio/background.mp3',
    sfxPaths: {
      impact: 'audio/impact.wav',
      swoosh: 'audio/swoosh.wav',
      riser: 'audio/riser.wav',
    },
  };
};
