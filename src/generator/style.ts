import type {VideoScript} from './schema.js';

export const LANDSCAPE_STYLES = [
  'anime',
  'realistic',
  'fantasy',
] as const;

export type LandscapeStyle = (typeof LANDSCAPE_STYLES)[number];
export type VisualStyle = 'general' | LandscapeStyle;

const STYLE_PROMPTS: Record<LandscapeStyle, string> = {
  anime:
    'vertical 9:16 cinematic anime landscape, no people, hand-painted anime film background, layered depth, atmospheric clouds, vivid natural light, no text',
  realistic:
    'vertical 9:16 photorealistic natural landscape, no people, cinematic photography, realistic sky and water, detailed foreground, natural light, no text',
  fantasy:
    'vertical 9:16 epic fantasy landscape, no people, floating islands, magical waterfalls, luminous vegetation, layered cinematic depth, no text',
};

export const applyVisualStyle = (
  script: VideoScript,
  style: VisualStyle,
): VideoScript => {
  if (style === 'general') {
    return script;
  }

  return {
    ...script,
    scenes: script.scenes.map((scene, index) => ({
      ...scene,
      imagePrompt: `${scene.imagePrompt}, ${STYLE_PROMPTS[style]}`,
      cameraMotion: index % 2 === 0 ? 'static' : 'pan_slow',
    })),
  };
};
