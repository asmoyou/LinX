import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './i18n/config'
import App from './App.tsx'
import { unregisterLegacyServiceWorkers } from './utils/pwaCleanup'

if (import.meta.env.VITE_ENABLE_PWA !== 'true') {
  void unregisterLegacyServiceWorkers()
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
