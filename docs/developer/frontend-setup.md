# Frontend Setup Guide

Complete guide for setting up the LinX (灵枢) frontend.

## Prerequisites

- Node.js 18+ and npm 9+
- Git

## Step 1: Initialize Vite Project

Navigate to the project root and initialize the frontend with Vite:

```bash
cd frontend
npm create vite@latest . -- --template react-ts
```

When prompted:
- **Project name**: Use `.` (current directory)
- **Select a framework**: React
- **Select a variant**: TypeScript

This will create a standard Vite + React + TypeScript project structure.

## Step 2: Install Dependencies

Install the required dependencies:

```bash
npm install
```

## Step 3: Install Additional Dependencies

Install project-specific dependencies:

```bash
# UI and Icons
npm install lucide-react

# Routing
npm install react-router-dom
npm install --save-dev @types/react-router-dom

# HTTP Client
npm install axios

# State Management
npm install zustand

# Internationalization
npm install i18next react-i18next

# Styling
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

## Step 4: Configure TailwindCSS

Update `tailwind.config.js`:

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
        },
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [],
}
```

Update `src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
  }

  .dark {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
  }
}

@layer utilities {
  .glass {
    @apply bg-white/10 backdrop-blur-md border border-white/20;
  }
  
  .glass-dark {
    @apply bg-black/10 backdrop-blur-md border border-white/10;
  }
}
```

## Step 5: Configure Vite

Update `vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

## Step 6: Update TypeScript Configuration

Update `tsconfig.json` to add path mapping:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,

    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",

    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,

    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

## Step 7: Create Project Structure

Create the following directory structure:

```bash
mkdir -p src/{api,components,hooks,pages,styles,types,utils,stores,i18n}
```

## Step 8: Set Up i18n

Create `src/i18n/config.ts`:

```typescript
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import zh from './locales/zh.json';

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      zh: { translation: zh },
    },
    lng: 'en',
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false,
    },
  });

export default i18n;
```

Create translation files:
- `src/i18n/locales/en.json`
- `src/i18n/locales/zh.json`

## Step 9: Create API Client

Create `src/api/client.ts`:

```typescript
import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for adding auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for handling errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

## Step 10: Create WebSocket Client

Create `src/api/websocket.ts`:

```typescript
class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  constructor(url: string) {
    this.url = url;
  }

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectAttempts = 0;
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected');
      this.reconnect();
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  private reconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      setTimeout(() => this.connect(), 1000 * this.reconnectAttempts);
    }
  }

  send(data: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  onMessage(callback: (data: any) => void) {
    if (this.ws) {
      this.ws.onmessage = (event) => {
        callback(JSON.parse(event.data));
      };
    }
  }

  disconnect() {
    this.ws?.close();
  }
}

export default WebSocketClient;
```

## Step 11: Create Theme Store

Create `src/stores/themeStore.ts`:

```typescript
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type Theme = 'light' | 'dark' | 'system';

interface ThemeStore {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set) => ({
      theme: 'system',
      setTheme: (theme) => set({ theme }),
    }),
    {
      name: 'theme-storage',
    }
  )
);
```

## Step 12: Create Glass Panel Component

Create `src/components/GlassPanel.tsx`:

```typescript
import React from 'react';

interface GlassPanelProps {
  children: React.ReactNode;
  className?: string;
}

export const GlassPanel: React.FC<GlassPanelProps> = ({ 
  children, 
  className = '' 
}) => {
  return (
    <div className={`glass rounded-lg p-6 ${className}`}>
      {children}
    </div>
  );
};
```

## Step 13: Update Main Entry Point

Update `src/main.tsx`:

```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'
import './i18n/config'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

## Step 14: Run Development Server

```bash
npm run dev
```

The application will be available at `http://localhost:3000`

## Project Structure

After setup, your frontend structure should look like:

```
frontend/
├── public/
├── src/
│   ├── api/
│   │   ├── client.ts
│   │   └── websocket.ts
│   ├── components/
│   │   └── GlassPanel.tsx
│   ├── hooks/
│   ├── i18n/
│   │   ├── config.ts
│   │   └── locales/
│   │       ├── en.json
│   │       └── zh.json
│   ├── pages/
│   ├── stores/
│   │   └── themeStore.ts
│   ├── styles/
│   ├── types/
│   ├── utils/
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── tailwind.config.js
└── postcss.config.js
```

## Next Steps

After completing the setup:

1. Implement routing with React Router
2. Create layout components (Sidebar, Header)
3. Build page components (Dashboard, Workforce, Tasks, etc.)
4. Implement authentication flow
5. Connect to backend API

## Troubleshooting

### Port Already in Use

If port 3000 is already in use, change it in `vite.config.ts`:

```typescript
server: {
  port: 3001, // Change to any available port
}
```

### Path Alias Not Working

Make sure `tsconfig.json` includes the path mapping and restart your IDE.

### TailwindCSS Not Working

Ensure `tailwind.config.js` content paths are correct and `index.css` imports are in place.

## References

- [Vite Documentation](https://vitejs.dev/)
- [React Documentation](https://react.dev/)
- [TailwindCSS Documentation](https://tailwindcss.com/)
- [React Router Documentation](https://reactrouter.com/)
- [i18next Documentation](https://www.i18next.com/)
