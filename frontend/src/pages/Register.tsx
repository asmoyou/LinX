import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { UserPlus, Loader2 } from 'lucide-react';
import { authApi } from '../api';
import { useAuthStore } from '../stores';
import toast from 'react-hot-toast';
import { LanguageSwitcher } from '../components/LanguageSwitcher';

export default function Register() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { login } = useAuthStore();

  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.username.trim()) {
      newErrors.username = t('register.errors.usernameRequired', 'Username is required');
    } else if (formData.username.length < 3) {
      newErrors.username = t('register.errors.usernameTooShort', 'Username must be at least 3 characters');
    }

    if (!formData.email.trim()) {
      newErrors.email = t('register.errors.emailRequired', 'Email is required');
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = t('register.errors.emailInvalid', 'Email is invalid');
    }

    if (!formData.password) {
      newErrors.password = t('register.errors.passwordRequired', 'Password is required');
    } else if (formData.password.length < 6) {
      newErrors.password = t('register.errors.passwordTooShort', 'Password must be at least 6 characters');
    }

    if (!formData.confirmPassword) {
      newErrors.confirmPassword = t('register.errors.confirmPasswordRequired', 'Please confirm your password');
    } else if (formData.password !== formData.confirmPassword) {
      newErrors.confirmPassword = t('register.errors.passwordMismatch', 'Passwords do not match');
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
      const response = await authApi.register({
        username: formData.username,
        email: formData.email,
        password: formData.password,
      });

      // Store tokens
      login(response.user, response.token);
      localStorage.setItem('refresh_token', response.refresh_token);

      toast.success(t('register.success', 'Registration successful!'));
      navigate('/dashboard');
    } catch (error: any) {
      console.error('Registration failed:', error);
      
      const errorMessage = error.response?.data?.message || 
        t('register.errors.failed', 'Registration failed. Please try again.');
      
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

      {/* Register card */}
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
              {t('register.title', 'Create Account')}
            </h1>
            <p className="text-slate-300">
              {t('register.subtitle', 'Join LinX Platform')}
            </p>
          </div>

          {/* Register form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Username field */}
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-slate-200 mb-2">
                {t('register.username', 'Username')}
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
                placeholder={t('register.usernamePlaceholder', 'Choose a username')}
                autoComplete="username"
                autoFocus
              />
              {errors.username && (
                <p className="mt-1 text-sm text-red-400">{errors.username}</p>
              )}
            </div>

            {/* Email field */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-200 mb-2">
                {t('register.email', 'Email')}
              </label>
              <input
                type="email"
                id="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                disabled={isLoading}
                className={`w-full px-4 py-3 bg-white/5 border ${
                  errors.email ? 'border-red-500' : 'border-white/10'
                } rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder={t('register.emailPlaceholder', 'Enter your email')}
                autoComplete="email"
              />
              {errors.email && (
                <p className="mt-1 text-sm text-red-400">{errors.email}</p>
              )}
            </div>

            {/* Password field */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-200 mb-2">
                {t('register.password', 'Password')}
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
                placeholder={t('register.passwordPlaceholder', 'Create a password')}
                autoComplete="new-password"
              />
              {errors.password && (
                <p className="mt-1 text-sm text-red-400">{errors.password}</p>
              )}
            </div>

            {/* Confirm Password field */}
            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-slate-200 mb-2">
                {t('register.confirmPassword', 'Confirm Password')}
              </label>
              <input
                type="password"
                id="confirmPassword"
                name="confirmPassword"
                value={formData.confirmPassword}
                onChange={handleChange}
                disabled={isLoading}
                className={`w-full px-4 py-3 bg-white/5 border ${
                  errors.confirmPassword ? 'border-red-500' : 'border-white/10'
                } rounded-lg text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder={t('register.confirmPasswordPlaceholder', 'Confirm your password')}
                autoComplete="new-password"
              />
              {errors.confirmPassword && (
                <p className="mt-1 text-sm text-red-400">{errors.confirmPassword}</p>
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
                  {t('register.creatingAccount', 'Creating account...')}
                </>
              ) : (
                <>
                  <UserPlus className="w-5 h-5" />
                  {t('register.createAccount', 'Create Account')}
                </>
              )}
            </button>
          </form>

          {/* Login link */}
          <div className="mt-6 text-center">
            <p className="text-slate-300">
              {t('register.haveAccount', 'Already have an account?')}{' '}
              <Link
                to="/login"
                className="text-purple-400 hover:text-purple-300 font-medium transition-colors"
              >
                {t('register.signIn', 'Sign in')}
              </Link>
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-slate-400 text-sm">
          <p>{t('register.footer', '© 2026 灵枢科技. All rights reserved.')}</p>
        </div>
      </div>
    </div>
  );
}
