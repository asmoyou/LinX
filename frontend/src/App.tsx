import {
  BrowserRouter as Router,
  Navigate,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { authApi, type SetupStatusResponse } from './api';
import { ProtectedRoute } from './components/ProtectedRoute';
import ErrorBoundary from './components/error/ErrorBoundary';
import PageErrorBoundary from './components/error/PageErrorBoundary';
import { Layout } from './components/layout/Layout';
import { LoadingSpinner } from './components/LoadingSpinner';
import { Toast } from './components/Toast';
import { useUserInitialization } from './hooks';
import {
  DEFAULT_UI_EXPERIENCE_SETTINGS,
  MotionProvider,
  PageTransition,
  useMotionPolicy,
  useMotionTelemetry,
} from './motion';
import { useAuthStore } from './stores';

const Dashboard = lazy(() =>
  import('./pages/Dashboard').then((module) => ({ default: module.Dashboard })),
);
const Projects = lazy(() =>
  import('./pages/Projects').then((module) => ({ default: module.Projects })),
);
const ProjectDetail = lazy(() =>
  import('./pages/ProjectDetail').then((module) => ({ default: module.ProjectDetail })),
);
const ProjectTaskDetail = lazy(() =>
  import('./pages/ProjectTaskDetail').then((module) => ({
    default: module.ProjectTaskDetail,
  })),
);
const RunCenter = lazy(() =>
  import('./pages/RunCenter').then((module) => ({ default: module.RunCenter })),
);
const RunDetail = lazy(() =>
  import('./pages/RunDetail').then((module) => ({ default: module.RunDetail })),
);
const ExecutionNodes = lazy(() =>
  import('./pages/ExecutionNodes').then((module) => ({
    default: module.ExecutionNodes,
  })),
);
const Workforce = lazy(() =>
  import('./pages/Workforce').then((module) => ({ default: module.Workforce })),
);
const AgentConversation = lazy(() =>
  import('./pages/AgentConversation').then((module) => ({
    default: module.AgentConversation,
  })),
);
const Schedules = lazy(() =>
  import('./pages/Schedules').then((module) => ({ default: module.Schedules })),
);
const ScheduleDetail = lazy(() =>
  import('./pages/ScheduleDetail').then((module) => ({
    default: module.ScheduleDetail,
  })),
);
const Knowledge = lazy(() =>
  import('./pages/Knowledge').then((module) => ({ default: module.Knowledge })),
);
const Memory = lazy(() =>
  import('./pages/Memory').then((module) => ({ default: module.Memory })),
);
const Robots = lazy(() =>
  import('./pages/Robots').then((module) => ({ default: module.Robots })),
);
const Skills = lazy(() => import('./pages/Skills'));
const Departments = lazy(() =>
  import('./pages/Departments').then((module) => ({ default: module.Departments })),
);
const UserManagement = lazy(() =>
  import('./pages/UserManagement').then((module) => ({
    default: module.UserManagement,
  })),
);
const RoleManagement = lazy(() =>
  import('./pages/RoleManagement').then((module) => ({
    default: module.RoleManagement,
  })),
);
const Settings = lazy(() =>
  import('./pages/Settings').then((module) => ({ default: module.Settings })),
);
const Profile = lazy(() =>
  import('./pages/Profile').then((module) => ({ default: module.Profile })),
);
const Notifications = lazy(() =>
  import('./pages/Notifications').then((module) => ({
    default: module.Notifications,
  })),
);
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const Setup = lazy(() => import('./pages/Setup'));

const PageLoader = () => (
  <div className="flex min-h-screen items-center justify-center">
    <LoadingSpinner size="lg" />
  </div>
);

const buildRouteAnimationKey = (pathname: string): string =>
  pathname.replace(
    /^\/workforce\/([^/]+)\/conversations(?:\/[^/]+)?$/,
    '/workforce/$1/conversations',
  );

const wrapPage = (pageName: string, node: ReactNode) => (
  <PageErrorBoundary pageName={pageName}>
    <Suspense fallback={<PageLoader />}>
      <PageTransition>{node}</PageTransition>
    </Suspense>
  </PageErrorBoundary>
);

interface AnimatedRoutesProps {
  setupStatus: SetupStatusResponse | null;
  onSetupStatusRefresh: () => Promise<void>;
}

const AnimatedRoutes = ({ setupStatus, onSetupStatusRefresh }: AnimatedRoutesProps) => {
  const location = useLocation();
  const { isAuthenticated } = useAuthStore();
  const { effectiveTier } = useMotionPolicy();

  useMotionTelemetry();

  const requiresSetup = setupStatus?.requires_setup ?? false;
  const defaultAdminUsername = setupStatus?.default_admin_username ?? 'admin';
  const routeAnimationKey = buildRouteAnimationKey(location.pathname);

  return (
    <AnimatePresence initial={effectiveTier !== 'off'} mode="wait">
      <Routes location={location} key={routeAnimationKey}>
        <Route
          path="/setup"
          element={
            isAuthenticated ? (
              <Navigate to="/projects" replace />
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
        <Route
          path="/login"
          element={
            isAuthenticated ? (
              <Navigate to="/projects" replace />
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
              <Navigate to="/projects" replace />
            ) : requiresSetup ? (
              <Navigate to="/setup" replace />
            ) : (
              <Suspense fallback={<PageLoader />}>
                <Register />
              </Suspense>
            )
          }
        />

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
          <Route index element={<Navigate to="/projects" replace />} />
          <Route path="projects" element={wrapPage('Projects', <Projects />)} />
          <Route
            path="projects/:projectId"
            element={wrapPage('Project Detail', <ProjectDetail />)}
          />
          <Route
            path="projects/:projectId/tasks/:taskId"
            element={wrapPage('Project Task Detail', <ProjectTaskDetail />)}
          />
          <Route path="runs" element={wrapPage('Run Center', <RunCenter />)} />
          <Route path="runs/:runId" element={wrapPage('Run Detail', <RunDetail />)} />
          <Route
            path="execution-nodes"
            element={wrapPage('Execution Nodes', <ExecutionNodes />)}
          />
          <Route path="skill-hub" element={<Navigate to="/skills/library?section=library" replace />} />
          <Route path="extensions" element={<Navigate to="/skills/library?section=mcp_servers" replace />} />
          <Route path="dashboard" element={wrapPage('仪表盘', <Dashboard />)} />
          <Route path="workforce" element={wrapPage('智能体', <Workforce />)} />
          <Route
            path="workforce/:agentId/conversations"
            element={wrapPage('持久化对话', <AgentConversation />)}
          />
          <Route
            path="workforce/:agentId/conversations/:conversationId"
            element={wrapPage('持久化对话', <AgentConversation />)}
          />
          <Route path="tasks" element={<Navigate to="/projects" replace />} />
          <Route path="schedules" element={wrapPage('定时任务', <Schedules />)} />
          <Route
            path="schedules/:scheduleId"
            element={wrapPage('定时任务详情', <ScheduleDetail />)}
          />
          <Route path="knowledge" element={wrapPage('知识库', <Knowledge />)} />
          <Route path="memory" element={wrapPage('记忆', <Memory />)} />
          <Route path="memory/user-memory" element={<Navigate to="/memory" replace />} />
          <Route path="skills" element={<Navigate to="/skills/library?section=library" replace />} />
          <Route path="skills/library" element={wrapPage('技能库', <Skills />)} />
          <Route path="robots" element={wrapPage('机器人', <Robots />)} />
          <Route path="departments" element={wrapPage('部门', <Departments />)} />
          <Route
            path="user-management"
            element={wrapPage('用户管理', <UserManagement />)}
          />
          <Route
            path="role-management"
            element={wrapPage('角色权限', <RoleManagement />)}
          />
          <Route path="settings" element={wrapPage('设置', <Settings />)} />
          <Route path="profile" element={wrapPage('个人资料', <Profile />)} />
          <Route
            path="notifications"
            element={wrapPage('通知中心', <Notifications />)}
          />
        </Route>
      </Routes>
    </AnimatePresence>
  );
};

const AppShell = ({
  setupStatus,
  onSetupStatusRefresh,
}: AnimatedRoutesProps) => {
  const { isAuthenticated } = useAuthStore();
  const { hasInitialized, isInitializing } = useUserInitialization();

  const shouldHoldProtectedUi = isAuthenticated && (!hasInitialized || isInitializing);

  if (shouldHoldProtectedUi) {
    return <PageLoader />;
  }

  return (
    <Router>
      <Toast />
      <AnimatedRoutes
        setupStatus={setupStatus}
        onSetupStatusRefresh={onSetupStatusRefresh}
      />
    </Router>
  );
};

function App() {
  const [setupStatus, setSetupStatus] = useState<SetupStatusResponse | null>(null);
  const [isSetupStatusLoading, setIsSetupStatusLoading] = useState(true);

  const refreshSetupStatus = useCallback(async () => {
    setIsSetupStatusLoading(true);

    try {
      const nextStatus = await authApi.getSetupStatus();
      setSetupStatus(nextStatus);
    } catch (error) {
      console.error('Failed to load setup status:', error);
      setSetupStatus({
        requires_setup: false,
        has_admin_account: true,
        default_admin_username: 'admin',
        ui_experience: DEFAULT_UI_EXPERIENCE_SETTINGS,
      });
    } finally {
      setIsSetupStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshSetupStatus();
  }, [refreshSetupStatus]);

  const platformSettings = useMemo(
    () => setupStatus?.ui_experience ?? DEFAULT_UI_EXPERIENCE_SETTINGS,
    [setupStatus?.ui_experience],
  );

  return (
    <ErrorBoundary>
      {isSetupStatusLoading ? (
        <PageLoader />
      ) : (
        <MotionProvider platformSettings={platformSettings}>
          <AppShell
            setupStatus={setupStatus}
            onSetupStatusRefresh={refreshSetupStatus}
          />
        </MotionProvider>
      )}
    </ErrorBoundary>
  );
}

export default App;
