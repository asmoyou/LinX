import { useEffect, useRef } from 'react';
import * as THREE from 'three';

interface ThreeBackgroundProps {
  isDark?: boolean;
}

export const ThreeBackground: React.FC<ThreeBackgroundProps> = ({ isDark = false }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const particlesRef = useRef<THREE.Points | null>(null);
  const linesRef = useRef<THREE.LineSegments | null>(null);
  const animationFrameIdRef = useRef<number | null>(null);
  const stateRef = useRef<{
    positions: Float32Array;
    velocities: Float32Array;
    particleCount: number;
    mouseX: number;
    mouseY: number;
  } | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Detect device performance
    const cpuCores = navigator.hardwareConcurrency || 4;
    const deviceMemory = (navigator as any).deviceMemory || 4;
    const particleCount = cpuCores >= 8 && deviceMemory >= 8 ? 400 : 
                         cpuCores >= 4 && deviceMemory >= 4 ? 250 : 150;

    // Scene setup
    const scene = new THREE.Scene();
    sceneRef.current = scene;

    // Camera setup
    const camera = new THREE.PerspectiveCamera(
      75,
      window.innerWidth / window.innerHeight,
      0.1,
      1000
    );
    camera.position.z = 50;

    // Renderer setup
    const renderer = new THREE.WebGLRenderer({ 
      alpha: true, 
      antialias: true,
      powerPreference: 'high-performance'
    });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    containerRef.current.appendChild(renderer.domElement);
    rendererRef.current = renderer;

    // Create particle system
    const positions = new Float32Array(particleCount * 3);
    const velocities = new Float32Array(particleCount * 3);

    for (let i = 0; i < particleCount; i++) {
      positions[i * 3] = (Math.random() - 0.5) * 100;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 100;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 100;

      velocities[i * 3] = (Math.random() - 0.5) * 0.03;
      velocities[i * 3 + 1] = (Math.random() - 0.5) * 0.03;
      velocities[i * 3 + 2] = (Math.random() - 0.5) * 0.03;
    }

    // Store state in ref
    stateRef.current = {
      positions,
      velocities,
      particleCount,
      mouseX: 0,
      mouseY: 0,
    };

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    // Material with color based on theme
    const particleColor = isDark ? 0x10b981 : 0x059669;
    const particleOpacity = isDark ? 0.6 : 0.4;
    
    const material = new THREE.PointsMaterial({
      size: 1.5,
      color: particleColor,
      transparent: true,
      opacity: particleOpacity,
      blending: THREE.AdditiveBlending,
      sizeAttenuation: true,
    });

    const particles = new THREE.Points(geometry, material);
    scene.add(particles);
    particlesRef.current = particles;

    // Add connecting lines
    const lineGeometry = new THREE.BufferGeometry();
    const lineMaterial = new THREE.LineBasicMaterial({
      color: particleColor,
      transparent: true,
      opacity: isDark ? 0.15 : 0.08,
      blending: THREE.AdditiveBlending,
    });

    const lines = new THREE.LineSegments(lineGeometry, lineMaterial);
    scene.add(lines);
    linesRef.current = lines;

    // Mouse interaction
    const handleMouseMove = (event: MouseEvent) => {
      if (stateRef.current) {
        stateRef.current.mouseX = (event.clientX / window.innerWidth) * 2 - 1;
        stateRef.current.mouseY = -(event.clientY / window.innerHeight) * 2 + 1;
      }
    };

    window.addEventListener('mousemove', handleMouseMove);

    // Animation loop
    const animate = () => {
      animationFrameIdRef.current = requestAnimationFrame(animate);

      if (!stateRef.current || !particles) return;

      const state = stateRef.current;
      const { positions, velocities, particleCount, mouseX, mouseY } = state;

      // Update particle positions
      for (let i = 0; i < particleCount; i++) {
        const idx = i * 3;
        positions[idx] += velocities[idx];
        positions[idx + 1] += velocities[idx + 1];
        positions[idx + 2] += velocities[idx + 2];

        // Boundary wrapping
        if (positions[idx] > 50) positions[idx] = -50;
        if (positions[idx] < -50) positions[idx] = 50;
        if (positions[idx + 1] > 50) positions[idx + 1] = -50;
        if (positions[idx + 1] < -50) positions[idx + 1] = 50;
        if (positions[idx + 2] > 50) positions[idx + 2] = -50;
        if (positions[idx + 2] < -50) positions[idx + 2] = 50;
      }

      particles.geometry.attributes.position.needsUpdate = true;

      // Update lines
      const linePositions: number[] = [];
      const maxDistance = 20;

      for (let i = 0; i < particleCount; i += 3) {
        for (let j = i + 1; j < particleCount; j += 3) {
          const dx = positions[i * 3] - positions[j * 3];
          const dy = positions[i * 3 + 1] - positions[j * 3 + 1];
          const dz = positions[i * 3 + 2] - positions[j * 3 + 2];
          const distance = Math.sqrt(dx * dx + dy * dy + dz * dz);

          if (distance < maxDistance) {
            linePositions.push(
              positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2],
              positions[j * 3], positions[j * 3 + 1], positions[j * 3 + 2]
            );
          }
        }
      }

      lines.geometry.setAttribute(
        'position',
        new THREE.Float32BufferAttribute(linePositions, 3)
      );

      // Rotation
      particles.rotation.x += 0.0001 + mouseY * 0.00003;
      particles.rotation.y += 0.0001 + mouseX * 0.00003;
      lines.rotation.x = particles.rotation.x;
      lines.rotation.y = particles.rotation.y;

      renderer.render(scene, camera);
    };

    animate();

    // Handle resize
    const handleResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    };

    window.addEventListener('resize', handleResize);

    // Cleanup
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('resize', handleResize);
      if (animationFrameIdRef.current !== null) {
        cancelAnimationFrame(animationFrameIdRef.current);
      }
      if (containerRef.current && renderer.domElement.parentNode === containerRef.current) {
        containerRef.current.removeChild(renderer.domElement);
      }
      geometry.dispose();
      material.dispose();
      lineGeometry.dispose();
      lineMaterial.dispose();
      renderer.dispose();
    };
  }, [isDark]);

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 pointer-events-none"
      style={{ zIndex: 0 }}
    />
  );
};
