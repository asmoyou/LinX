import type { HTMLAttributes, PropsWithChildren } from 'react';
import { motion } from 'framer-motion';

import { getPageTransitionProps } from './presets';
import { useMotionPolicy } from './useMotionPolicy';

export const PageTransition = ({
  children,
  ...rest
}: PropsWithChildren<HTMLAttributes<HTMLDivElement>>) => {
  const { effectiveTier } = useMotionPolicy();

  if (effectiveTier === 'off') {
    return <div {...rest}>{children}</div>;
  }

  return (
    <motion.div {...getPageTransitionProps(effectiveTier)} {...rest}>
      {children}
    </motion.div>
  );
};
