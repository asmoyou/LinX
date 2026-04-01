import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Skills from '@/pages/Skills';
import { skillsApi } from '@/api/skills';
import { agentsApi } from '@/api';
import { mcpServersApi } from '@/api/mcpServers';

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, options?: string | { defaultValue?: string }) => {
        if (typeof options === 'string') {
          return options;
        }
        if (options && typeof options === 'object' && 'defaultValue' in options) {
          return options.defaultValue || _key;
        }
        return _key;
      },
      i18n: { language: 'zh-CN' },
    }),
  };
});

vi.mock('@/api/skills', () => ({
  skillsApi: {
    listPage: vi.fn(),
    getCandidates: vi.fn(),
    getBindings: vi.fn(),
    getOverviewStats: vi.fn(),
    getStore: vi.fn(),
    installSkill: vi.fn(),
    uninstallSkill: vi.fn(),
    getAgentBindings: vi.fn(),
    updateAgentBindings: vi.fn(),
    create: vi.fn(),
    getById: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    deactivateSkill: vi.fn(),
    activateSkill: vi.fn(),
    promoteCandidate: vi.fn(),
    rejectCandidate: vi.fn(),
  },
}));

vi.mock('@/api', () => ({
  agentsApi: {
    getAll: vi.fn(),
  },
}));

vi.mock('@/api/mcpServers', () => ({
  mcpServersApi: {
    getAll: vi.fn(),
  },
}));

vi.mock('@/components/skills/SkillCardV2', () => ({
  default: ({ skill }: any) => <div>{skill.display_name}</div>,
}));

vi.mock('@/components/skills/AddSkillModalV2', () => ({ default: () => null }));
vi.mock('@/components/skills/EditSkillModal', () => ({ default: () => null }));
vi.mock('@/components/skills/AgentSkillViewer', () => ({ default: () => null }));
vi.mock('@/components/skills/SkillTesterModal', () => ({ default: () => null }));
vi.mock('@/components/skills/McpServerCard', () => ({ default: () => null }));
vi.mock('@/components/skills/AddMcpServerModal', () => ({ default: () => null }));
vi.mock('@/components/skills/EditMcpServerModal', () => ({ default: () => null }));

describe('Skills page store flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(skillsApi.getCandidates).mockResolvedValue([] as any);
    vi.mocked(skillsApi.getBindings).mockResolvedValue([] as any);
    vi.mocked(skillsApi.getOverviewStats).mockResolvedValue({
      total_skills: 1,
      active_skills: 1,
      inactive_skills: 0,
      agent_skills: 1,
      langchain_tool_skills: 0,
      skills_with_dependencies: 0,
      total_execution_count: 0,
      average_execution_time: 0,
      last_executed_at: null,
    } as any);
    vi.mocked(mcpServersApi.getAll).mockResolvedValue([] as any);
    vi.mocked(agentsApi.getAll).mockResolvedValue([
      {
        id: 'agent-1',
        name: 'Writer Agent',
        type: 'general',
        status: 'idle',
        tasksCompleted: 0,
        uptime: '1h',
        ownerUserId: 'user-1',
        canManage: true,
      },
    ] as any);
    vi.mocked(skillsApi.listPage).mockResolvedValue({
      items: [
        {
          skill_id: 'installed-skill-id',
          skill_slug: 'document-artifact-rendering-installed',
          display_name: 'Document Artifact Rendering',
          description: 'Installed copy',
          version: '1.0.0',
          access_level: 'private',
          source_kind: 'curated_install',
          interface_definition: { inputs: {}, outputs: {} },
          dependencies: [],
          created_at: '2025-01-01T00:00:00Z',
        },
      ],
      total: 1,
      limit: 24,
      offset: 0,
      hasMore: false,
    } as any);
    vi.mocked(skillsApi.getStore).mockResolvedValue([
      {
        skill_id: 'canonical-skill-id',
        skill_slug: 'document-artifact-rendering',
        display_name: 'Document Artifact Rendering',
        description: 'Official rendering skill',
        version: '1.0.0',
        access_level: 'public',
        source_kind: 'curated',
        interface_definition: { inputs: {}, outputs: {} },
        dependencies: [],
        created_at: '2025-01-01T00:00:00Z',
        is_installed: false,
        installed_skill_id: null,
        installed_skill_slug: null,
        installed_binding_count: 0,
      },
    ] as any);
    vi.mocked(skillsApi.installSkill).mockResolvedValue({
      installed_skill_id: 'installed-skill-id',
      installed_skill_slug: 'document-artifact-rendering-installed',
      canonical_skill_id: 'canonical-skill-id',
      source: 'curated_install',
    });
    vi.mocked(skillsApi.uninstallSkill).mockResolvedValue(undefined);
    vi.mocked(skillsApi.getAgentBindings).mockResolvedValue({
      owner_id: 'agent-1',
      owner_type: 'agent',
      bindings: [],
      available_skills: [],
    } as any);
    vi.mocked(skillsApi.updateAgentBindings).mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
  });

  it('keeps installed skills in library and official skills in a dedicated store tab', async () => {
    render(
      <MemoryRouter initialEntries={['/skills?section=library']}>
        <Skills />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Document Artifact Rendering')).toBeInTheDocument();
    expect(screen.queryByText('Official rendering skill')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Skill Store/ }));

    expect(await screen.findByText('Official rendering skill')).toBeInTheDocument();
    expect(screen.queryByText('Browse official curated skills. Install adds the skill to your library; uninstall removes your installed copy.')).toBeInTheDocument();
  });

  it('installs and uninstalls official skills from the store tab', async () => {
    const storeState = [
      {
        skill_id: 'canonical-skill-id',
        skill_slug: 'document-artifact-rendering',
        display_name: 'Document Artifact Rendering',
        description: 'Official rendering skill',
        version: '1.0.0',
        access_level: 'public',
        source_kind: 'curated',
        interface_definition: { inputs: {}, outputs: {} },
        dependencies: [],
        created_at: '2025-01-01T00:00:00Z',
        is_installed: false,
        installed_skill_id: null,
        installed_skill_slug: null,
        installed_binding_count: 0,
      },
    ];
    vi.mocked(skillsApi.getStore).mockImplementation(async () => storeState as any);
    vi.mocked(skillsApi.installSkill).mockImplementation(async () => {
      storeState[0] = {
        ...storeState[0],
        is_installed: true,
        installed_skill_id: 'installed-skill-id',
        installed_skill_slug: 'document-artifact-rendering-installed',
        installed_binding_count: 0,
      };
      return {
        installed_skill_id: 'installed-skill-id',
        installed_skill_slug: 'document-artifact-rendering-installed',
        canonical_skill_id: 'canonical-skill-id',
        source: 'curated_install',
      };
    });
    vi.mocked(skillsApi.uninstallSkill).mockImplementation(async () => {
      storeState[0] = {
        ...storeState[0],
        is_installed: false,
        installed_skill_id: null,
        installed_skill_slug: null,
        installed_binding_count: 0,
      };
    });

    render(
      <MemoryRouter initialEntries={['/skills?section=store']}>
        <Skills />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Official rendering skill')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Install' }));

    await waitFor(() => {
      expect(vi.mocked(skillsApi.installSkill)).toHaveBeenCalledWith('canonical-skill-id');
    });

    await waitFor(() => {
      expect(screen.getByText('Installed')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Uninstall' }));

    await waitFor(() => {
      expect(vi.mocked(skillsApi.uninstallSkill)).toHaveBeenCalledWith('canonical-skill-id');
    });
    await waitFor(() => {
      expect(screen.getByText('Not installed')).toBeInTheDocument();
    });
  });

  it('supports install and bind from the store tab', async () => {
    vi.mocked(skillsApi.installSkill).mockResolvedValue({
      installed_skill_id: 'installed-skill-id',
      installed_skill_slug: 'document-artifact-rendering-installed',
      canonical_skill_id: 'canonical-skill-id',
      source: 'curated_install',
    });

    render(
      <MemoryRouter initialEntries={['/skills?section=store']}>
        <Skills />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Official rendering skill')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Install & Bind' }));

    expect(await screen.findByText(/Select one or more agents to start using/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Save Bindings' }));

    await waitFor(() => {
      expect(vi.mocked(skillsApi.installSkill)).toHaveBeenCalledWith('canonical-skill-id');
    });
    await waitFor(() => {
      expect(vi.mocked(skillsApi.updateAgentBindings)).toHaveBeenCalledWith(
        'agent-1',
        expect.arrayContaining([
          expect.objectContaining({
            skill_id: 'installed-skill-id',
            binding_mode: 'doc',
            enabled: true,
          }),
        ]),
      );
    });
  });

  it('prefills bound agents and allows clearing them to unbind', async () => {
    vi.mocked(skillsApi.getBindings).mockResolvedValue([
      {
        binding_id: 'binding-1',
        owner_id: 'agent-1',
        owner_name: 'Writer Agent',
        owner_type: 'agent',
        skill_id: 'installed-skill-id',
        skill_slug: 'document-artifact-rendering-installed',
        display_name: 'Document Artifact Rendering',
        binding_mode: 'doc',
        enabled: true,
        priority: 0,
        source: 'manual',
        auto_update_policy: 'follow_active',
      },
    ] as any);
    vi.mocked(skillsApi.getStore).mockResolvedValue([
      {
        skill_id: 'canonical-skill-id',
        skill_slug: 'document-artifact-rendering',
        display_name: 'Document Artifact Rendering',
        description: 'Official rendering skill',
        version: '1.0.0',
        access_level: 'public',
        source_kind: 'curated',
        interface_definition: { inputs: {}, outputs: {} },
        dependencies: [],
        created_at: '2025-01-01T00:00:00Z',
        is_installed: true,
        installed_skill_id: 'installed-skill-id',
        installed_skill_slug: 'document-artifact-rendering-installed',
        installed_binding_count: 1,
      },
    ] as any);
    vi.mocked(skillsApi.getAgentBindings).mockResolvedValue({
      owner_id: 'agent-1',
      owner_type: 'agent',
      bindings: [
        {
          skill_id: 'installed-skill-id',
          binding_mode: 'doc',
          enabled: true,
          priority: 0,
          source: 'manual',
          auto_update_policy: 'follow_active',
          revision_pin_id: null,
        },
      ],
      available_skills: [],
    } as any);

    render(
      <MemoryRouter initialEntries={['/skills?section=store']}>
        <Skills />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Bound to/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Bind to Agent/ }));

    const checkbox = await screen.findByRole('checkbox');
    expect(checkbox).toBeChecked();

    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole('button', { name: 'Save Bindings' }));

    await waitFor(() => {
      expect(vi.mocked(skillsApi.updateAgentBindings)).toHaveBeenCalledWith('agent-1', []);
    });
  });

  it('disables uninstall when an installed skill is already bound to agents', async () => {
    vi.mocked(skillsApi.getStore).mockResolvedValue([
      {
        skill_id: 'canonical-skill-id',
        skill_slug: 'document-artifact-rendering',
        display_name: 'Document Artifact Rendering',
        description: 'Official rendering skill',
        version: '1.0.0',
        access_level: 'public',
        source_kind: 'curated',
        interface_definition: { inputs: {}, outputs: {} },
        dependencies: [],
        created_at: '2025-01-01T00:00:00Z',
        is_installed: true,
        installed_skill_id: 'installed-skill-id',
        installed_skill_slug: 'document-artifact-rendering-installed',
        installed_binding_count: 2,
      },
    ] as any);

    render(
      <MemoryRouter initialEntries={['/skills?section=store']}>
        <Skills />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Bound to/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Uninstall' })).toBeDisabled();
  });
});
