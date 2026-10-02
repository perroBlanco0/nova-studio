import {describe, expect, it} from 'vitest';
import {parseCliOptions} from '../src/cli/index.js';

describe('video CLI', () => {
  it('accepts every landscape style at once', () => {
    expect(parseCliOptions(['--style', 'all']).style).toBe('all');
  });

  it('rejects unknown visual styles', () => {
    expect(() => parseCliOptions(['--style', 'ugly-zoom'])).toThrow(
      'Estilo inválido',
    );
  });
});
