import { useState, useEffect } from 'react';

export const useSystemTheme = () => {
  const [isDark, setIsDark] = useState(() => {
    // Check if user has a preference stored
    const stored = localStorage.getItem('theme');
    if (stored) {
      return stored === 'dark';
    }
    // Otherwise check system preference
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    
    const handleChange = (e: MediaQueryListEvent) => {
      // Only update if user hasn't set a manual preference
      const stored = localStorage.getItem('theme');
      if (!stored) {
        setIsDark(e.matches);
      }
    };

    mediaQuery.addEventListener('change', handleChange);
    
    // Also listen for manual theme changes
    const handleStorageChange = () => {
      const stored = localStorage.getItem('theme');
      if (stored) {
        setIsDark(stored === 'dark');
      }
    };
    
    window.addEventListener('storage', handleStorageChange);

    return () => {
      mediaQuery.removeEventListener('change', handleChange);
      window.removeEventListener('storage', handleStorageChange);
    };
  }, []);

  // Apply theme to document
  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  return isDark;
};
