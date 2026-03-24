import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Setup from '@/pages/Setup';

const changeLanguageMock = vi.fn().mockResolvedValue(undefined);

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: {
      language: 'en',
      changeLanguage: changeLanguageMock,
    },
  }),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock('@/api', () => ({
  authApi: {
    initializePlatform: vi.fn(),
  },
}));

vi.mock('@/components/ParticleBackground', () => ({
  ParticleBackground: () => null,
}));

describe('Setup page password feedback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();

    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it('shows realtime password strength and confirm password match feedback', () => {
    render(<Setup />);

    const passwordInput = screen.getByLabelText('Admin Password');
    const confirmPasswordInput = screen.getByLabelText('Confirm Password');

    fireEvent.change(passwordInput, {
      target: { name: 'password', value: 'weak' },
    });

    expect(screen.getByText('Password Strength')).toBeInTheDocument();
    expect(screen.getByText('Weak')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Password is too weak. Include uppercase, lowercase, numbers, and symbols.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('At least 8 characters')).toBeInTheDocument();

    fireEvent.change(confirmPasswordInput, {
      target: { name: 'confirmPassword', value: 'weaker' },
    });

    expect(screen.getByText('The two passwords do not match.')).toBeInTheDocument();

    fireEvent.change(passwordInput, {
      target: { name: 'password', value: 'SecurePassword123!' },
    });

    expect(screen.getByText('Strong')).toBeInTheDocument();

    fireEvent.change(confirmPasswordInput, {
      target: { name: 'confirmPassword', value: 'SecurePassword123!' },
    });

    expect(screen.getByText('Passwords match.')).toBeInTheDocument();
  });
});
