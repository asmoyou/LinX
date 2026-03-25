import { render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ParticleBackground } from '@/components/ParticleBackground';
import { DEFAULT_UI_EXPERIENCE_SETTINGS, MotionProvider } from '@/motion';

const createMediaQueryList = (matches = false): MediaQueryList =>
  ({
    matches,
    media: '(prefers-reduced-motion: reduce)',
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }) as unknown as MediaQueryList;

describe('ParticleBackground', () => {
  let visibilityState = 'visible';
  const rafSpy = vi.fn(() => 1);
  const cancelAnimationFrameSpy = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    visibilityState = 'visible';

    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn(() => createMediaQueryList(false)),
    });

    Object.defineProperty(window, 'requestAnimationFrame', {
      writable: true,
      value: rafSpy,
    });

    Object.defineProperty(window, 'cancelAnimationFrame', {
      writable: true,
      value: cancelAnimationFrameSpy,
    });

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => visibilityState,
    });

    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
      configurable: true,
      value: vi.fn(() => ({
        setTransform: vi.fn(),
        clearRect: vi.fn(),
        beginPath: vi.fn(),
        moveTo: vi.fn(),
        lineTo: vi.fn(),
        stroke: vi.fn(),
        arc: vi.fn(),
        fill: vi.fn(),
        shadowBlur: 0,
        shadowColor: '',
        fillStyle: '',
        strokeStyle: '',
        lineWidth: 1,
      })),
    });
  });

  it('renders a static background without canvas animation in reduced mode', () => {
    const { container } = render(
      <MotionProvider
        platformSettings={{
          ...DEFAULT_UI_EXPERIENCE_SETTINGS,
          default_motion_preference: 'reduced',
        }}
      >
        <ParticleBackground />
      </MotionProvider>,
    );

    expect(container.querySelector('canvas')).toBeNull();
    expect(rafSpy).not.toHaveBeenCalled();
  });

  it('starts canvas animation in full mode and pauses it when the page is hidden', () => {
    const { container } = render(
      <MotionProvider
        platformSettings={{
          ...DEFAULT_UI_EXPERIENCE_SETTINGS,
          default_motion_preference: 'full',
        }}
      >
        <ParticleBackground />
      </MotionProvider>,
    );

    expect(container.querySelector('canvas')).not.toBeNull();
    expect(rafSpy).toHaveBeenCalled();

    visibilityState = 'hidden';
    document.dispatchEvent(new Event('visibilitychange'));

    expect(cancelAnimationFrameSpy).toHaveBeenCalled();
  });
});
