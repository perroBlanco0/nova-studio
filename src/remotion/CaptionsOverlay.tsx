import {useCurrentFrame, useVideoConfig} from 'remotion';
import type {CaptionWord} from '../audio/tts.js';

type CaptionsOverlayProps = {
  captions: CaptionWord[];
};

const visibleChunk = (
  captions: CaptionWord[],
  currentMs: number,
): {words: CaptionWord[]; activeIndex: number} => {
  if (captions.length === 0) {
    return {words: [], activeIndex: -1};
  }
  const exact = captions.findIndex(
    (caption) => currentMs >= caption.startMs && currentMs < caption.endMs,
  );
  let latest = -1;
  for (let index = captions.length - 1; index >= 0; index -= 1) {
    const caption = captions[index];
    if (caption && currentMs >= caption.startMs) {
      latest = index;
      break;
    }
  }
  const activeIndex = exact >= 0 ? exact : Math.max(0, latest);
  const chunkStart = Math.floor(activeIndex / 6) * 6;
  return {
    words: captions.slice(chunkStart, chunkStart + 6),
    activeIndex: activeIndex - chunkStart,
  };
};

export const CaptionsOverlay = ({
  captions,
}: CaptionsOverlayProps): React.ReactNode => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const currentMs = (frame / fps) * 1000;
  const {words, activeIndex} = visibleChunk(captions, currentMs);

  if (words.length === 0) {
    return null;
  }

  return (
    <div
      style={{
        position: 'absolute',
        left: 70,
        right: 70,
        bottom: 270,
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'center',
        gap: '10px 16px',
        textAlign: 'center',
        fontFamily: 'Arial, Helvetica, sans-serif',
        fontSize: 76,
        fontWeight: 900,
        lineHeight: 1.02,
        letterSpacing: -2,
        textTransform: 'uppercase',
        textShadow:
          '0 5px 0 rgba(0,0,0,.85), 0 0 24px rgba(0,0,0,.9), 0 0 5px rgba(0,0,0,1)',
      }}
    >
      {words.map((word, index) => (
        <span
          key={`${word.startMs}-${word.text}`}
          style={{
            color: index === activeIndex ? '#ffe34f' : '#ffffff',
            transform: index === activeIndex ? 'scale(1.08)' : 'scale(1)',
          }}
        >
          {word.text}
        </span>
      ))}
    </div>
  );
};
