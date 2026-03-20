import {
  BrowserRouter as Router,
  Routes,
  Route,
  useLocation,
  Navigate,
} from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Layout } from "./components/layout/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoadingSpinner } from "./components/LoadingSpinner";
import { Toast } from "./components/Toast";
import { useAuthStore } from "./stores";
import ErrorBoundary from "./components/error/ErrorBoundary";
import PageErrorBoundary from "./components/error/PageErrorBoundary";
import { useUserInitialization } from "./hooks";
import { authApi, type SetupStatusResponse } from "./api";

// Lazy load pages for better performance (6.9.6)
const Dashboard = lazy(() =>
  import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })),
);
const Workforce = lazy(() =>
  import("./pages/Workforce").then((m) => ({ default: m.Workforce })),
);
const AgentConversation = lazy(() =>
  import("./pages/AgentConversation").then((m) => ({
    default: m.AgentConversation,
  })),
);
const Tasks = lazy(() =>
  import("./pages/Missions").then((m) => ({ default: m.Missions })),
);
const Schedules = lazy(() =>
  import("./pages/Schedules").then((m) => ({ default: m.Schedules })),
);
const ScheduleDetail = lazy(() =>
  import("./pages/ScheduleDetail").then((m) => ({ default: m.ScheduleDetail })),
);
const Knowledge = lazy(() =>
  import("./pages/Knowledge").then((m) => ({ default: m.Knowledge })),
);
const Memory = lazy(() =>
  import("./pages/Memory").then((m) => ({ default: m.Memory })),
);
const Robots = lazy(() =>
  import("./pages/Robots").then((m) => ({ default: m.Robots })),
);
const Skills = lazy(() => import("./pages/Skills"));
const Departments = lazy(() =>
  import("./pages/Departments").then((m) => ({ default: m.Departments })),
);
const UserManagement = lazy(() =>
  import("./pages/UserManagement").then((m) => ({ default: m.UserManagement })),
);
const RoleManagement = lazy(() =>
  import("./pages/RoleManagement").then((m) => ({ default: m.RoleManagement })),
);
const Settings = lazy(() =>
  import("./pages/Settings").then((m) => ({ default: m.Settings })),
);
const Profile = lazy(() =>
  import("./pages/Profile").then((m) => ({ default: m.Profile })),
);
const Notifications = lazy(() =>
  import("./pages/Notifications").then((m) => ({ default: m.Notifications })),
);
const Login = lazy(() => import("./pages/Login"));
const Register = lazy(() => import("./pages/Register"));
const Setup = lazy(() => import("./pages/Setup"));

// Loading fallback component
const PageLoader = () => (
  <div className="flex items-center justify-center min-h-screen">
    <LoadingSpinner size="lg" />
  </div>
);

const buildRouteAnimationKey = (pathname: string): string => {
  return pathname.replace(
    /^\/workforce\/([^/]+)\/conversations(?:\/[^/]+)?$/,
    "/workforce/$1/conversations",
  );
};

interface AnimatedRoutesProps {
  setupStatus: SetupStatusResponse | null;
  onSetupStatusRefresh: () => Promise<void>;
}

const AnimatedRoutes = ({
  setupStatus,
  onSetupStatusRefresh,
}: AnimatedRoutesProps) => {
  const location = useLocation();
  const { isAuthenticated } = useAuthStore();
  const requiresSetup = setupStatus?.requires_setup ?? false;
  const defaultAdminUsername = setupStatus?.default_admin_username ?? "admin";
  const routeAnimationKey = buildRouteAnimationKey(location.pathname);

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={routeAnimationKey}>
        <Route
          path="/setup"
          element={
            isAuthenticated ? (
              <Navigate to="/dashboard" replace />
            ) : requiresSetup ? (
              <Suspense fallback={<PageLoader />}>
                <Setup
                  defaultAdminUsername={defaultAdminUsername}
                  onSetupComplete={onSetupStatusRefresh}
                />
              </Suspense>
            ) : (
              <Navigate to="/login" replace />
            )
          }
        />

        {/* Public routes */}
        <Route
          path="/login"
          element={
            isAuthenticated ? (
              <Navigate to="/dashboard" replace />
            ) : requiresSetup ? (
              <Navigate to="/setup" replace />
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
            ) : requiresSetup ? (
              <Navigate to="/setup" replace />
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
            requiresSetup && !isAuthenticated ? (
              <Navigate to="/setup" replace />
            ) : (
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            )
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
            path="workforce/:agentId/conversations"
            element={
              <PageErrorBoundary pageName="持久化对话">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <AgentConversation />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
          <Route
            path="workforce/:agentId/conversations/:conversationId"
            element={
              <PageErrorBoundary pageName="持久化对话">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <AgentConversation />
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
            path="schedules"
            element={
              <PageErrorBoundary pageName="定时任务">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Schedules />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
          <Route
            path="schedules/:scheduleId"
            element={
              <PageErrorBoundary pageName="定时任务详情">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <ScheduleDetail />
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
            path="memory/user-memory"
            element={<Navigate to="/memory" replace />}
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
            path="robots"
            element={
              <PageErrorBoundary pageName="机器人">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Robots />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
          <Route
            path="departments"
            element={
              <PageErrorBoundary pageName="部门">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Departments />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
          <Route
            path="user-management"
            element={
              <PageErrorBoundary pageName="用户管理">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <UserManagement />
                  </motion.div>
                </Suspense>
              </PageErrorBoundary>
            }
          />
          <Route
            path="role-management"
            element={
              <PageErrorBoundary pageName="角色权限">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <RoleManagement />
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
          <Route
            path="notifications"
            element={
              <PageErrorBoundary pageName="通知中心">
                <Suspense fallback={<PageLoader />}>
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.3 }}
                  >
                    <Notifications />
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
  // Initialize user data when authenticated
  useUserInitialization();
  const [setupStatus, setSetupStatus] = useState<SetupStatusResponse | null>(
    null,
  );
  const [isSetupStatusLoading, setIsSetupStatusLoading] = useState(true);

  const refreshSetupStatus = useCallback(async () => {
    setIsSetupStatusLoading(true);

    try {
      const nextStatus = await authApi.getSetupStatus();
      setSetupStatus(nextStatus);
    } catch (error) {
      console.error("Failed to load setup status:", error);
      setSetupStatus({
        requires_setup: false,
        has_admin_account: true,
        default_admin_username: "admin",
      });
    } finally {
      setIsSetupStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshSetupStatus();
  }, [refreshSetupStatus]);

  return (
    <ErrorBoundary>
      <Router>
        <Toast />
        {isSetupStatusLoading ? (
          <PageLoader />
        ) : (
          <AnimatedRoutes
            setupStatus={setupStatus}
            onSetupStatusRefresh={refreshSetupStatus}
          />
        )}
      </Router>
    </ErrorBoundary>
  );
}

export default App;
