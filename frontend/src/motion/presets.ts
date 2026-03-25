import type { ComponentProps } from 'react';
import { motion, type Transition, type Variants } from 'framer-motion';

import type { MotionTier } from './types';

interface MotionBackdropPreset {
  initial: Record<string, number>;
  animate: Record<string, number>;
  exit: Record<string, number>;
  transition: Transition;
}

export const getPageTransitionProps = (
  tier: MotionTier,
): Partial<ComponentProps<typeof motion.div>> => {
  if (tier === 'off') {
    return {};
  }

  if (tier === 'reduced') {
    return {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: 0.12, ease: 'easeOut' },
    };
  }

  return {
    initial: { opacity: 0, y: 16 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -16 },
    transition: { duration: 0.24, ease: 'easeOut' },
  };
};

export const getModalMotionPreset = (
  tier: MotionTier,
): { backdrop: MotionBackdropPreset; variants: Variants } => {
  if (tier === 'off') {
    return {
      backdrop: {
        initial: { opacity: 1 },
        animate: { opacity: 1 },
        exit: { opacity: 1 },
        transition: { duration: 0 },
      },
      variants: {
        hidden: { opacity: 1, scale: 1, y: 0 },
        visible: { opacity: 1, scale: 1, y: 0, transition: { duration: 0 } },
        exit: { opacity: 1, scale: 1, y: 0, transition: { duration: 0 } },
      },
    };
  }

  if (tier === 'reduced') {
    return {
      backdrop: {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
        transition: { duration: 0.12, ease: 'easeOut' },
      },
      variants: {
        hidden: { opacity: 0, scale: 0.99, y: 4 },
        visible: {
          opacity: 1,
          scale: 1,
          y: 0,
          transition: { duration: 0.12, ease: 'easeOut' },
        },
        exit: {
          opacity: 0,
          scale: 0.995,
          y: 2,
          transition: { duration: 0.1, ease: 'easeOut' },
        },
      },
    };
  }

  return {
    backdrop: {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
      transition: { duration: 0.2 },
    },
    variants: {
      hidden: { opacity: 0, scale: 0.96, y: 8 },
      visible: {
        opacity: 1,
        scale: 1,
        y: 0,
        transition: { type: 'spring', stiffness: 450, damping: 32, mass: 1 },
      },
      exit: {
        opacity: 0,
        scale: 0.98,
        y: 4,
        transition: { duration: 0.15, ease: 'easeOut' },
      },
    },
  };
};
