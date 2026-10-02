import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
} from 'remotion';
import type {RenderScene} from './types.js';

type BackgroundVisualProps = {
  scene: RenderScene;
};

export const BackgroundVisual = ({
  scene,
}: BackgroundVisualProps): React.ReactNode => {
  const frame = useCurrentFrame();
  const progress = interpolate(
    frame,
    [0, Math.max(1, scene.durationInFrames - 1)],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.ease},
  );

  const zoom =
    scene.cameraMotion === 'zoom_in'
      ? interpolate(progress, [0, 1], [1.04, 1.16])
      : 1.1;
  const panX =
    scene.cameraMotion === 'pan_slow'
      ? interpolate(progress, [0, 1], [-45, 45])
      : 0;
  const shake =
    scene.cameraMotion === 'shake_impact' && frame < 14
      ? Math.sin(frame * 2.8) * (1 - frame / 14) * 18
      : 0;
  const scale =
    scene.cameraMotion === 'shake_impact'
      ? interpolate(progress, [0, 1], [1.1, 1.14])
      : zoom;

  return (
    <AbsoluteFill style={{overflow: 'hidden', backgroundColor: '#05070d'}}>
      <Img
        src={staticFile(scene.assetPath)}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transform: `translate3d(${panX + shake}px, ${shake * 0.35}px, 0) scale(${scale})`,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(180deg, rgba(3,7,15,.2) 0%, rgba(3,7,15,.03) 45%, rgba(3,7,15,.74) 100%)',
        }}
      />
    </AbsoluteFill>
  );
};
