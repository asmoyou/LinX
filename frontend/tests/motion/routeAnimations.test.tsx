import { describe, expect, it } from 'vitest';

import { getModalMotionPreset, getPageTransitionProps } from '@/motion';

describe('motion transition presets', () => {
  it('uses fast opacity-only transitions for reduced motion pages', () => {
    expect(getPageTransitionProps('reduced')).toMatchObject({
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: 0.12, ease: 'easeOut' },
    });
  });

  it('disables page transitions entirely when motion is off', () => {
    expect(getPageTransitionProps('off')).toEqual({});
  });

  it('returns zero-duration modal variants when motion is off', () => {
    const preset = getModalMotionPreset('off');

    expect(preset.backdrop.transition).toMatchObject({ duration: 0 });
    expect(preset.variants.hidden).toEqual({ opacity: 1, scale: 1, y: 0 });
    expect(preset.variants.visible).toMatchObject({
      opacity: 1,
      scale: 1,
      y: 0,
      transition: { duration: 0 },
    });
  });
});
