import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'

// https://vite.dev/config/
export default defineConfig(() => {
  const enablePwa = process.env.VITE_ENABLE_PWA === 'true';
  const plugins = [react()];

  if (enablePwa) {
    plugins.push(
      // PWA is opt-in only. Default is disabled to avoid stale service worker caches.
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['logo-favicon.webp', 'logo-lg.webp'],
        manifest: {
          name: 'LinX - 灵枢智能协作平台',
          short_name: 'LinX',
          description: 'LinX (灵枢) - Intelligent Collaboration Platform for AI agents',
          theme_color: '#10b981',
          background_color: '#000000',
          display: 'standalone',
          icons: [
            {
              src: '/logo-lg.webp',
              sizes: '512x512',
              type: 'image/webp',
            },
            {
              src: '/logo-md.webp',
              sizes: '192x192',
              type: 'image/webp',
            },
          ],
        },
        workbox: {
          globPatterns: ['**/*.{js,css,html,ico,png,svg,woff,woff2}'],
          runtimeCaching: [
            {
              urlPattern: /^https:\/\/api\./i,
              handler: 'NetworkFirst',
              options: {
                cacheName: 'api-cache',
                expiration: {
                  maxEntries: 50,
                  maxAgeSeconds: 60 * 60, // 1 hour
                },
              },
            },
          ],
        },
      }),
    );
  }

  return {
    plugins,
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          ws: true,
        },
      },
    },
    preview: {
      host: '0.0.0.0',
      port: 3000,
    },
    build: {
      // Code splitting for better performance (6.9.5)
      rollupOptions: {
        output: {
          manualChunks: {
            // Vendor chunks
            'react-vendor': ['react', 'react-dom', 'react-router-dom'],
            'ui-vendor': ['framer-motion', 'lucide-react'],
            'chart-vendor': ['recharts'],
            'flow-vendor': ['reactflow'],
          },
        },
      },
      // Optimize chunk size
      chunkSizeWarningLimit: 1000,
      // Source maps for production debugging
      sourcemap: false,
    },
    // Optimize dependencies
    optimizeDeps: {
      include: ['react', 'react-dom', 'react-router-dom'],
    },
    test: {
      environment: 'jsdom',
      include: ['tests/**/*.test.ts', 'tests/**/*.test.tsx'],
      setupFiles: ['tests/setup.ts'],
      clearMocks: true,
    },
  };
})
