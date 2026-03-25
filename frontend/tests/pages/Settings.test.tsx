import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Settings } from '@/pages/Settings';

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (_key: string, fallback?: string) => fallback || _key,
    }),
  };
});

vi.mock('@/components/settings/BusinessBaselineSettings', () => ({
  BusinessBaselineSettings: ({
    onOpenTab,
  }: {
    onOpenTab: (tab: 'experience' | 'llm' | 'envVars' | 'missionPolicy') => void;
  }) => (
    <div>
      <p>Business Baseline Panel</p>
      <button type="button" onClick={() => onOpenTab('experience')}>
        Open Experience
      </button>
    </div>
  ),
}));

vi.mock('@/components/settings/ExperienceSettings', () => ({
  ExperienceSettings: () => <div>Experience Panel</div>,
}));

vi.mock('@/components/settings/LLMSettings', () => ({
  LLMSettings: () => <div>LLM Panel</div>,
}));

vi.mock('@/components/settings/EnvVarsSettings', () => ({
  EnvVarsSettings: () => <div>Env Vars Panel</div>,
}));

vi.mock('@/components/settings/MissionPolicySettings', () => ({
  MissionPolicySettings: () => <div>Mission Policy Panel</div>,
}));

const LocationDisplay = () => {
  const location = useLocation();

  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>;
};

describe('Settings page', () => {
  afterEach(() => {
    cleanup();
  });

  it('uses the tab query parameter to open the requested settings panel', () => {
    render(
      <MemoryRouter initialEntries={['/settings?tab=experience']}>
        <Routes>
          <Route
            path="/settings"
            element={
              <>
                <Settings />
                <LocationDisplay />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Experience Panel')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/settings?tab=experience');
  });

  it('writes the selected tab back to the URL', () => {
    render(
      <MemoryRouter initialEntries={['/settings']}>
        <Routes>
          <Route
            path="/settings"
            element={
              <>
                <Settings />
                <LocationDisplay />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Mission Policy' }));

    expect(screen.getByText('Mission Policy Panel')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/settings?tab=missionPolicy');
  });

  it('lets baseline shortcuts open the experience tab without local-only state', () => {
    render(
      <MemoryRouter initialEntries={['/settings']}>
        <Routes>
          <Route
            path="/settings"
            element={
              <>
                <Settings />
                <LocationDisplay />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Open Experience' }));

    expect(screen.getByText('Experience Panel')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/settings?tab=experience');
  });
});
