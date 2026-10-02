import {describe, expect, it} from 'vitest';
import {generateHeuristicScript} from '../src/generator/script.js';
import {validateVideoScript} from '../src/generator/schema.js';

describe('video script', () => {
  it('generates a valid local script without credentials', () => {
    const script = generateHeuristicScript(
      'Los 3 errores más comunes al entrenar calistenia',
    );

    expect(validateVideoScript(script)).toEqual(script);
    expect(script.scenes).toHaveLength(3);
    expect(script.scenes.every((scene) => scene.durationInSeconds >= 3)).toBe(
      true,
    );
  });

  it('rejects unsupported camera motions', () => {
    expect(() =>
      validateVideoScript({
        title: 'Tema',
        scenes: [
          {
            sceneId: 'scene-1',
            textToSpeak: 'Texto',
            imagePrompt: 'Imagen',
            cameraMotion: 'spin',
            durationInSeconds: 3,
          },
        ],
      }),
    ).toThrow();
  });
});
