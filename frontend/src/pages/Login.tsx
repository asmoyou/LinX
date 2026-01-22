import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LogIn, Loader2, Moon, Sun } from 'lucide-react';
import { authApi } from '../api';
import { useAuthStore } from '../stores';
import toast from 'react-hot-toast';
import { LanguageSwitcher } from '../components/LanguageSwitcher';
import { ThreeBackground } from '../components/ThreeBackground';
import { useSystemTheme } from '../hooks/useSystemTheme';

export default function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { login } = useAuthStore();
  const isDark = useSystemTheme();
  const [manualDarkMode, setManualDarkMode] = useState<boolean | null>(null);
  
  // Use manual override if set, otherwise use system theme
  const displayDarkMode = manualDarkMode !== null ? manualDarkMode : isDark;

  const toggleTheme = () => {
    setManualDarkMode(prev => prev === null ? !isDark : !prev);
  };

  const [formData, setFormData] = useState({
    username: '',
    password: '',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.username.trim()) {
      newErrors.username = t('login.errors.usernameRequired', 'Username is required');
    }

    if (!formData.password) {
      newErrors.password = t('login.errors.passwordRequired', 'Password is required');
    } else if (formData.password.length < 6) {
      newErrors.password = t('login.errors.passwordTooShort', 'Password must be at least 6 characters');
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);
    setErrors({});

    try {
      const response = await authApi.login({
        username: formData.username,
        password: formData.password,
      });

      // Store tokens
      login(response.user, response.token);
      localStorage.setItem('refresh_token', response.refresh_token);

      toast.success(t('login.success', 'Login successful!'));
      navigate('/dashboard');
    } catch (error: any) {
      console.error('Login failed:', error);
      
      const errorMessage = error.response?.data?.message || 
        t('login.errors.failed', 'Login failed. Please check your credentials.');
      
      toast.error(errorMessage);
      setErrors({ submit: errorMessage });
    } finally {
      setIsLoading(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    // Clear error when user starts typing
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: '' }));
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden bg-gradient-to-br from-zinc-50 via-emerald-50/30 to-zinc-50 dark:from-zinc-950 dark:via-emerald-950/20 dark:to-zinc-950 p-4 transition-colors duration-500">
      {/* Three.js animated background */}
      <ThreeBackground isDark={displayDarkMode} key={displayDarkMode ? 'dark' : 'light'} />
      
      {/* Static background effects (fallback/enhancement) */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none" style={{ zIndex: 1 }}>
        {/* Subtle grid pattern overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808008_1px,transparent_1px),linear-gradient(to_bottom,#80808008_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_50%,#000_70%,transparent_110%)]" />
      </div>

      {/* Login card */}
      <div className="relative w-full max-w-md z-10">
        {/* Top controls */}
        <div className="flex justify-between items-center mb-4">
          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg bg-white/20 dark:bg-zinc-800/20 hover:bg-white/30 dark:hover:bg-zinc-800/30 text-zinc-700 dark:text-zinc-300 transition-all duration-300 backdrop-blur-sm border border-white/10 dark:border-zinc-700/10"
            title={displayDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {displayDarkMode ? (
              <Sun className="w-5 h-5" />
            ) : (
              <Moon className="w-5 h-5" />
            )}
          </button>
          <LanguageSwitcher />
        </div>

        <div className="backdrop-blur-xl bg-white/80 dark:bg-zinc-900/80 border border-zinc-200/50 dark:border-zinc-800/50 rounded-2xl shadow-2xl shadow-emerald-500/5 p-8 transition-colors duration-500">
          {/* Logo and title */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 mb-4">
              <img 
                src="/logo-md.webp" 
                alt="LinX Logo" 
                className="w-16 h-16 object-contain"
              />
            </div>
            <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-100 mb-2 transition-colors">
              {t('login.title', 'Welcome Back')}
            </h1>
            <p className="text-zinc-600 dark:text-zinc-400 transition-colors">
              {t('login.subtitle', 'Sign in to LinX Platform')}
            </p>
          </div>

          {/* Login form */}
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Username field */}
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2 transition-colors">
                {t('login.username', 'Username')}
              </label>
              <input
                type="text"
                id="username"
                name="username"
                value={formData.username}
                onChange={handleChange}
                disabled={isLoading}
                className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
                  errors.username ? 'border-red-500 dark:border-red-400' : 'border-zinc-300 dark:border-zinc-700'
                } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder={t('login.usernamePlaceholder', 'Enter your username')}
                autoComplete="username"
                autoFocus
              />
              {errors.username && (
                <p className="mt-1 text-sm text-red-500 dark:text-red-400">{errors.username}</p>
              )}
            </div>

            {/* Password field */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2 transition-colors">
                {t('login.password', 'Password')}
              </label>
              <input
                type="password"
                id="password"
                name="password"
                value={formData.password}
                onChange={handleChange}
                disabled={isLoading}
                className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
                  errors.password ? 'border-red-500 dark:border-red-400' : 'border-zinc-300 dark:border-zinc-700'
                } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder={t('login.passwordPlaceholder', 'Enter your password')}
                autoComplete="current-password"
              />
              {errors.password && (
                <p className="mt-1 text-sm text-red-500 dark:text-red-400">{errors.password}</p>
              )}
            </div>

            {/* Submit error */}
            {errors.submit && (
              <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/30 rounded-lg transition-colors">
                <p className="text-sm text-red-600 dark:text-red-400">{errors.submit}</p>
              </div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white font-medium rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/25"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  {t('login.signingIn', 'Signing in...')}
                </>
              ) : (
                <>
                  <LogIn className="w-5 h-5" />
                  {t('login.signIn', 'Sign In')}
                </>
              )}
            </button>
          </form>

          {/* Register link */}
          <div className="mt-6 text-center">
            <p className="text-zinc-600 dark:text-zinc-400 transition-colors">
              {t('login.noAccount', "Don't have an account?")}{' '}
              <Link
                to="/register"
                className="text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 font-medium transition-colors"
              >
                {t('login.signUp', 'Sign up')}
              </Link>
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-zinc-500 dark:text-zinc-500 text-sm transition-colors">
          <p>{t('login.footer', '© 2026 灵枢科技. All rights reserved.')}</p>
        </div>
      </div>
    </div>
  );
}
