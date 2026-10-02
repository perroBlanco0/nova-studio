import {describe, expect, it} from 'vitest';
import {
  buildFallbackCaptions,
  parseTimestampMs,
  parseVttCaptions,
} from '../src/audio/tts.js';

describe('audio timestamps', () => {
  it('parses WebVTT timestamps', () => {
    expect(parseTimestampMs('00:01:02.500')).toBe(62_500);
    expect(parseTimestampMs('00:00:03,125')).toBe(3_125);
  });

  it('expands phrase cues into ordered word captions', () => {
    const captions = parseVttCaptions(`WEBVTT

00:00:00.000 --> 00:00:02.000
Hola mundo increíble

00:00:02.000 --> 00:00:03.000
Guarda esto
`);

    expect(captions.map((caption) => caption.text)).toEqual([
      'Hola',
      'mundo',
      'increíble',
      'Guarda',
      'esto',
    ]);
    expect(captions[0]?.startMs).toBe(0);
    expect(captions.at(-1)?.endMs).toBe(3_000);
    expect(
      captions.every(
        (caption, index) =>
          index === 0 || caption.startMs >= (captions[index - 1]?.startMs ?? 0),
      ),
    ).toBe(true);
  });

  it('builds deterministic offline caption timing', () => {
    const captions = buildFallbackCaptions('uno dos tres', 3_000);
    expect(captions).toHaveLength(3);
    expect(captions[0]).toMatchObject({text: 'uno', startMs: 0});
    expect(captions[2]).toMatchObject({text: 'tres', endMs: 3_000});
  });
});
