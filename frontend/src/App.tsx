import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { GlassPanel } from './components/GlassPanel';

function App() {
  const { t } = useTranslation();

  return (
    <Router>
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800 p-8">
        <GlassPanel className="max-w-4xl mx-auto">
          <h1 className="text-4xl font-bold text-gray-800 dark:text-white mb-4">
            {t('app.name')}
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-300">
            {t('app.tagline')}
          </p>
          <div className="mt-8">
            <p className="text-gray-700 dark:text-gray-200">
              Frontend foundation is ready! 🚀
            </p>
            <ul className="mt-4 space-y-2 text-sm text-gray-600 dark:text-gray-400">
              <li>✅ React 18 + TypeScript</li>
              <li>✅ Vite build tool</li>
              <li>✅ TailwindCSS with glassmorphism</li>
              <li>✅ React Router</li>
              <li>✅ i18n (English/Chinese)</li>
              <li>✅ Zustand state management</li>
              <li>✅ Axios API client</li>
              <li>✅ WebSocket client</li>
            </ul>
          </div>
        </GlassPanel>
      </div>
    </Router>
  );
}

export default App;

