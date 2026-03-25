import { useContext } from 'react';

import { MotionContext } from './context';

export const useMotionPolicy = () => useContext(MotionContext);
