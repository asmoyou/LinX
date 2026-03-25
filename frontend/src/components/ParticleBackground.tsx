import { useEffect, useMemo, useRef } from 'react';

import { useMotionPolicy } from '@/motion';

interface ParticleBackgroundProps {
  isDark?: boolean;
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
}

export const ParticleBackground: React.FC<ParticleBackgroundProps> = ({ isDark = false }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const particlesRef = useRef<Particle[]>([]);
  const animationFrameRef = useRef<number | undefined>(undefined);
  const { deviceClass, effectiveTier, saveData } = useMotionPolicy();

  const shouldAnimateCanvas = effectiveTier === 'full';
  const staticOrbOpacity = effectiveTier === 'off' ? '0.16' : '0.2';
  const particleCount = useMemo(() => {
    if (!shouldAnimateCanvas) {
      return 0;
    }

    if (typeof window === 'undefined') {
      return 24;
    }

    const estimatedCount = Math.round((window.innerWidth * window.innerHeight) / 45_000);
    const clampedCount = Math.min(Math.max(estimatedCount, 24), 64);

    if (deviceClass === 'low' || saveData) {
      return Math.min(clampedCount, 36);
    }

    return clampedCount;
  }, [deviceClass, saveData, shouldAnimateCanvas]);

  useEffect(() => {
    if (!shouldAnimateCanvas || typeof window === 'undefined') {
      return undefined;
    }

    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    const resizeCanvas = () => {
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = window.innerWidth * pixelRatio;
      canvas.height = window.innerHeight * pixelRatio;
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      
      // Reinitialize particles when window resizes
      particlesRef.current = Array.from({ length: particleCount }, () => ({
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        size: Math.random() * 2 + 1,
      }));
    };
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    const startLoop = () => {
      animationFrameRef.current = requestAnimationFrame(animate);
    };

    const stopLoop = () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = undefined;
      }
    };

    // Animation loop
    const animate = () => {
      if (!ctx || !canvas) return;
      if (document.visibilityState !== 'visible') {
        return;
      }

      // Clear canvas
      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

      // Update and draw particles
      const particles = particlesRef.current;
      const connectionDistance = 150;

      // Theme colors
      const particleColor = isDark ? 'rgba(16, 185, 129, 0.6)' : 'rgba(5, 150, 105, 0.5)';
      const lineColor = isDark ? 'rgba(16, 185, 129, 0.15)' : 'rgba(5, 150, 105, 0.1)';
      const glowColor = isDark ? 'rgba(16, 185, 129, 0.3)' : 'rgba(5, 150, 105, 0.2)';

      particles.forEach((particle, i) => {
        // Update position
        particle.x += particle.vx;
        particle.y += particle.vy;

        // Bounce off edges
        if (particle.x < 0 || particle.x > window.innerWidth) particle.vx *= -1;
        if (particle.y < 0 || particle.y > window.innerHeight) particle.vy *= -1;

        // Keep particles in bounds
        particle.x = Math.max(0, Math.min(window.innerWidth, particle.x));
        particle.y = Math.max(0, Math.min(window.innerHeight, particle.y));

        // Draw connections to nearby particles
        for (let j = i + 1; j < particles.length; j++) {
          const other = particles[j];
          const dx = particle.x - other.x;
          const dy = particle.y - other.y;
          const distance = Math.sqrt(dx * dx + dy * dy);

          if (distance < connectionDistance) {
            const opacity = (1 - distance / connectionDistance) * 0.5;
            ctx.strokeStyle = lineColor.replace('0.15', String(opacity * 0.15)).replace('0.1', String(opacity * 0.1));
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(particle.x, particle.y);
            ctx.lineTo(other.x, other.y);
            ctx.stroke();
          }
        }

        // Draw particle with glow
        ctx.shadowBlur = 10;
        ctx.shadowColor = glowColor;
        ctx.fillStyle = particleColor;
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;
      });

      animationFrameRef.current = requestAnimationFrame(animate);
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        stopLoop();
        startLoop();
      } else {
        stopLoop();
      }
    };

    startLoop();
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      stopLoop();
    };
  }, [isDark, particleCount, shouldAnimateCanvas]);

  return (
    <>
      {shouldAnimateCanvas ? (
        <canvas
          ref={canvasRef}
          className="fixed inset-0 pointer-events-none"
          style={{ zIndex: 0 }}
        />
      ) : null}
      
      {/* Gradient orbs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none" style={{ zIndex: 1 }}>
        <div
          className={`absolute top-1/4 left-1/4 w-96 h-96 rounded-full blur-3xl ${shouldAnimateCanvas ? 'animate-pulse motion-decorative' : ''}`}
          style={{
            background: isDark
              ? 'radial-gradient(circle, rgba(16, 185, 129, 0.3) 0%, transparent 70%)'
              : 'radial-gradient(circle, rgba(5, 150, 105, 0.2) 0%, transparent 70%)',
            opacity: staticOrbOpacity,
            animationDuration: shouldAnimateCanvas ? '8s' : undefined,
          }}
        />
        <div
          className={`absolute bottom-1/4 right-1/4 w-96 h-96 rounded-full blur-3xl ${shouldAnimateCanvas ? 'animate-pulse motion-decorative' : ''}`}
          style={{
            background: isDark
              ? 'radial-gradient(circle, rgba(16, 185, 129, 0.3) 0%, transparent 70%)'
              : 'radial-gradient(circle, rgba(5, 150, 105, 0.2) 0%, transparent 70%)',
            opacity: staticOrbOpacity,
            animationDuration: shouldAnimateCanvas ? '10s' : undefined,
            animationDelay: shouldAnimateCanvas ? '2s' : undefined,
          }}
        />
      </div>
    </>
  );
};
