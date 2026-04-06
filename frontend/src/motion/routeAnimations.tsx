import type { ComponentPropsWithoutRef, PropsWithChildren } from 'react';
import { motion } from 'framer-motion';

import { getPageTransitionProps } from './presets';
import { useMotionPolicy } from './useMotionPolicy';

export const PageTransition = ({
  children,
  ...rest
}: PropsWithChildren<ComponentPropsWithoutRef<'div'>>) => {
  const { effectiveTier } = useMotionPolicy();

  if (effectiveTier === 'off') {
    return <div {...rest}>{children}</div>;
  }

  return (
    <motion.div {...getPageTransitionProps(effectiveTier)} {...(rest as Record<string, unknown>)}>
      {children}
    </motion.div>
  );
};
