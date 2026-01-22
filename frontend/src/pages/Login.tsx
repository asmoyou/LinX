import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LogIn, Loader2 } from 'lucide-react';
import { authApi } from '../api';
import { useAuthStore } from '../stores';
import toast from 'react-hot-toast';
import { LanguageSwitcher } from '../components/LanguageSwitcher';

export default function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { login } = useAuthStore();

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
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 p-4">
      {/* Background effects */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-purple-500/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-500/20 rounded-full blur-3xl animate-pulse delay-1000" />
      </div>

      {/* Login card */}
      <div className="relative w-full max-w-md">
        {/* Language switcher */}
        <div className="flex justify-end mb-4">
          <LanguageSwitcher />
        </div>

        <div className="backdrop-blur-xl bg-white/10 border border-white/20 rounded-2xl shadow-2xl p-8">
          {/* Logo and title */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 mb-4">
              <img 
                src="/logo-md.webp" 
                alt="LinX Logo" 
                className="w-16 h-16 object-contain"
              />
            </div>
            <h1 className="text-3xl font-bold text-white mb-2">
              {t('login.title', 'Welcome Back')}
            </h1>
            <p className="text-slate-300">
              {t('login.subtitle', 'Sign in to LinX Platform')}
            </p>
          </div>

          {/* Login form */}
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Username field */}
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-slate-200 mb-2">
                {t('login.username', 'Username')}
              </label>
              <input
                type="text"
                id="username"
                name="username"
                value={formData.username}
                onChange={handleChange}
                disabled={isLoading}
                className={`w-full px-4 py-3 bg-white/5 border ${
                  errors.username ? 'border-red-500' : 'border-white/10'
                } rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder={t('login.usernamePlaceholder', 'Enter your username')}
                autoComplete="username"
                autoFocus
              />
              {errors.username && (
                <p className="mt-1 text-sm text-red-400">{errors.username}</p>
              )}
            </div>

            {/* Password field */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-200 mb-2">
                {t('login.password', 'Password')}
              </label>
              <input
                type="password"
                id="password"
                name="password"
                value={formData.password}
                onChange={handleChange}
                disabled={isLoading}
                className={`w-full px-4 py-3 bg-white/5 border ${
                  errors.password ? 'border-red-500' : 'border-white/10'
                } rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder={t('login.passwordPlaceholder', 'Enter your password')}
                autoComplete="current-password"
              />
              {errors.password && (
                <p className="mt-1 text-sm text-red-400">{errors.password}</p>
              )}
            </div>

            {/* Submit error */}
            {errors.submit && (
              <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                <p className="text-sm text-red-400">{errors.submit}</p>
              </div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3 px-4 bg-gradient-to-r from-purple-500 to-blue-500 hover:from-purple-600 hover:to-blue-600 text-white font-medium rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
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
            <p className="text-slate-300">
              {t('login.noAccount', "Don't have an account?")}{' '}
              <Link
                to="/register"
                className="text-purple-400 hover:text-purple-300 font-medium transition-colors"
              >
                {t('login.signUp', 'Sign up')}
              </Link>
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-slate-400 text-sm">
          <p>{t('login.footer', '© 2026 灵枢科技. All rights reserved.')}</p>
        </div>
      </div>
    </div>
  );
}
