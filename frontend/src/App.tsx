import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { Dashboard } from './pages/Dashboard';
import { Workforce } from './pages/Workforce';
import { Tasks } from './pages/Tasks';
import { Knowledge } from './pages/Knowledge';
import { Memory } from './pages/Memory';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="workforce" element={<Workforce />} />
          <Route path="tasks" element={<Tasks />} />
          <Route path="knowledge" element={<Knowledge />} />
          <Route path="memory" element={<Memory />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;

