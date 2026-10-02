import {interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

export const ProgressBar = (): React.ReactNode => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const width = interpolate(
    frame,
    [0, Math.max(1, durationInFrames - 1)],
    [0, 100],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );

  return (
    <div
      style={{
        position: 'absolute',
        left: 46,
        right: 46,
        top: 72,
        height: 12,
        borderRadius: 999,
        overflow: 'hidden',
        background: 'rgba(255,255,255,.24)',
        boxShadow: '0 2px 12px rgba(0,0,0,.35)',
      }}
    >
      <div
        style={{
          width: `${width}%`,
          height: '100%',
          borderRadius: 999,
          background: 'linear-gradient(90deg, #4fffe1, #ffe34f)',
        }}
      />
    </div>
  );
};
