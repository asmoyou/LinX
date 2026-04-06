import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FolderKanban, Sparkles, Workflow } from 'lucide-react';
import toast from 'react-hot-toast';

import { platformApi } from '@/api/platform';

export const ProjectExecutionPolicySettings = () => {
  const [commandTemplate, setCommandTemplate] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    void platformApi.getProjectExecutionSettings()
      .then((settings) => setCommandTemplate(settings.external_agent_command_template || ''))
      .catch(() => undefined);
  }, []);

  const handleSave = async () => {
    try {
      setIsSaving(true);
      await platformApi.updateProjectExecutionSettings({
        external_agent_command_template: commandTemplate,
      });
      toast.success('Project execution settings saved');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save project execution settings';
      toast.error(message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-700 dark:bg-zinc-900/40">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <Workflow className="h-5 w-5 text-emerald-500" />
              <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                Project Execution Policy
              </h2>
            </div>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              The platform now manages execution policy through project-scoped planning and run
              orchestration instead of the legacy mission policy surface.
            </p>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-700 dark:bg-zinc-900/40">
        <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
          <Workflow className="h-5 w-5 text-indigo-500" />
          <h3 className="font-semibold">External agent runner</h3>
        </div>
        <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
          Default command template used by external runtime hosts when spawning an external agent session.
        </p>
        <textarea
          value={commandTemplate}
          onChange={(event) => setCommandTemplate(event.target.value)}
          rows={4}
          className="mt-4 w-full rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 outline-none transition focus:border-indigo-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100"
          placeholder={"Example: external-agent --prompt-file LINX_AGENT_PROMPT_FILE"}
        />
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={isSaving}
          className="mt-4 rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSaving ? 'Saving…' : 'Save external runner'}
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-700 dark:bg-zinc-900/40">
          <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
            <FolderKanban className="h-5 w-5 text-indigo-500" />
            <h3 className="font-semibold">Project defaults</h3>
          </div>
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            Planning, task creation, and run launch now start from project spaces. Configure
            behavior from the project workspace instead of a global mission editor.
          </p>
          <Link
            to="/projects"
            className="mt-4 inline-flex rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
          >
            Open Projects
          </Link>
        </div>

        <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-700 dark:bg-zinc-900/40">
          <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
            <Workflow className="h-5 w-5 text-emerald-500" />
            <h3 className="font-semibold">Run orchestration</h3>
          </div>
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            Run start, retry, and execution visibility live in the run center. This replaces the
            old mission execution board as the primary runtime surface.
          </p>
          <Link
            to="/runs"
            className="mt-4 inline-flex rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
          >
            Open Run Center
          </Link>
        </div>

        <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-700 dark:bg-zinc-900/40">
          <div className="flex items-center gap-2 text-zinc-900 dark:text-zinc-100">
            <Sparkles className="h-5 w-5 text-amber-500" />
            <h3 className="font-semibold">Capabilities</h3>
          </div>
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            Skills, MCP servers, and extension-backed tools are managed from the Skills Library.
            The project execution UI only shows scoped summaries and launch actions.
          </p>
          <Link
            to="/skills/library?section=library"
            className="mt-4 inline-flex rounded-full border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-600 dark:hover:bg-zinc-900"
          >
            Open Skills Library
          </Link>
        </div>
      </div>
    </div>
  );
};
