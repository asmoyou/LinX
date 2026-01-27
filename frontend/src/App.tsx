import { BrowserRouter as Router, Routes, Route, useLocation, Navigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { lazy, Suspense } from 'react';
import { Layout } from './components/layout/Layout';
import { ProtectedRoute } from './components/ProtectedRoute';
import { LoadingSpinner } from './components/LoadingSpinner';
import { Toast } from './components/Toast';
import { useAuthStore } from './stores';
import ErrorBoundary from './components/error/ErrorBoundary';
import PageErrorBoundary from './components/error/PageErrorBoundary';

// Lazy load pages for better performance (6.9.6)
const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })));
const Workforce = lazy(() => import('./pages/Workforce').then(m => ({ default: m.Workforce })));
const Tasks = lazy(() => import('./pages/Tasks').then(m => ({ default: m.Tasks })));
const Knowledge = lazy(() => import('./pages/Knowledge').then(m => ({ default: m.Knowledge })));
const Memory = lazy(() => import('./pages/Memory').then(m => ({ default: m.Memory })));
const Skills = lazy(() => import('./pages/Skills'));
const Settings = lazy(() => import('./pages/Settings').then(m => ({ default: m.Settings })));
const Profile = lazy(() => import('./pages/Profile').then(m => ({ default: m.Profile })));
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));

// Loading fallback component
const PageLoader = () => (
  <div className="flex items-center justify-center min-h-screen">
    <LoadingSpinner size="lg" />
  </div>
);

const AnimatedRoutes = () => {
  const location = useLocation();
  const { isAuthenticated } = useAuthStore();

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        {/* Public routes */}
        <Route
          path="/login"
          element={
            isAuthenticated ? (
              <Navigate to="/dashboard" replace />
            ) : (
              <Suspense fallback={<PageLoader />}>
                <Login />
              </Suspense>
            )
          }
        />
        <Route
          path="/register"
          element={
            isAuthenticated ? (
              <Navigate to="/dashboard" replace />
            ) : (
              <Suspense fallback={<PageLoader />}>
                <Register />
              </Suspense>
            )
          }
        />

        {/* Protected routes */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route
            path="dashboard"
            element={
              <PageErrorBoundary pageName="仪表盘">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Dashboard />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
          <Route
            path="workforce"
            element={
              <PageErrorBoundary pageName="智能体">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Workforce />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
          <Route
            path="tasks"
            element={
              <PageErrorBoundary pageName="任务">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Tasks />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
          <Route
            path="knowledge"
            element={
              <PageErrorBoundary pageName="知识库">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Knowledge />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
          <Route
            path="memory"
            element={
              <PageErrorBoundary pageName="记忆">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Memory />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
          <Route
            path="skills"
            element={
              <PageErrorBoundary pageName="技能库">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Skills />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
          <Route
            path="settings"
            element={
              <PageErrorBoundary pageName="设置">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Settings />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
          <Route
            path="profile"
            element={
              <PageErrorBoundary pageName="个人资料">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Profile />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
        </Route>
      </Routes>
    </AnimatePresence>
  );
};

function App() {
  return (
    <ErrorBoundary>
      <Router>
        <Toast />
        <AnimatedRoutes />
      </Router>
    </ErrorBoundary>
  );
}

export default App;

