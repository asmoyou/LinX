import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LogIn, Loader2, Moon, Sun, Eye, EyeOff } from 'lucide-react';
import { authApi } from '../api';
import { useAuthStore } from '../stores';
import { useThemeStore } from '../stores/themeStore';
import toast from 'react-hot-toast';
import { LanguageSwitcher } from '../components/LanguageSwitcher';
import { ParticleBackground } from '../components/ParticleBackground';

export default function Login() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { login } = useAuthStore();
  const { theme, setTheme, applyTheme } = useThemeStore();
  const [isDark, setIsDark] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  
  // Apply theme on mount and when theme changes
  useEffect(() => {
    applyTheme();
    
    // Update isDark based on current theme
    const updateIsDark = () => {
      const dark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
      setIsDark(dark);
    };
    
    updateIsDark();
    
    // Listen for system theme changes if using system theme
    if (theme === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      mediaQuery.addEventListener('change', updateIsDark);
      return () => mediaQuery.removeEventListener('change', updateIsDark);
    }
  }, [theme, applyTheme]);
  
  const toggleTheme = () => {
    setTheme(isDark ? 'light' : 'dark');
  };

  const [formData, setFormData] = useState({
    username: '',
    password: '',
    rememberMe: false,
  });
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    // Username/Email validation (allow both)
    if (!formData.username.trim()) {
      newErrors.username = t('login.errors.usernameRequired', 'Username or email is required');
    } else if (formData.username.length < 3) {
      newErrors.username = t('login.errors.usernameTooShort', 'Username or email must be at least 3 characters');
    }
    // Removed format validation to allow email addresses

    // Password validation
    if (!formData.password) {
      newErrors.password = t('login.errors.passwordRequired', 'Password is required');
    } else if (formData.password.length < 6) {
      newErrors.password = t('login.errors.passwordTooShort', 'Password must be at least 6 characters');
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const validateField = (name: string, value: string) => {
    const newErrors = { ...errors };

    if (name === 'username') {
      if (!value.trim()) {
        newErrors.username = t('login.errors.usernameRequired', 'Username or email is required');
      } else if (value.length < 3) {
        newErrors.username = t('login.errors.usernameTooShort', 'Username or email must be at least 3 characters');
      } else {
        delete newErrors.username;
      }
      // Removed format validation to allow email addresses
    }

    if (name === 'password') {
      if (!value) {
        newErrors.password = t('login.errors.passwordRequired', 'Password is required');
      } else if (value.length < 6) {
        newErrors.password = t('login.errors.passwordTooShort', 'Password must be at least 6 characters');
      } else {
        delete newErrors.password;
      }
    }

    setErrors(newErrors);
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
      login(response.user, response.access_token);  // 使用 access_token 而不是 token
      localStorage.setItem('refresh_token', response.refresh_token);
      
      // Store remember me preference
      if (formData.rememberMe) {
        localStorage.setItem('remember_username', formData.username);
      } else {
        localStorage.removeItem('remember_username');
      }

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
    const { name, value, type, checked } = e.target;
    const newValue = type === 'checkbox' ? checked : value;
    
    setFormData((prev) => ({ ...prev, [name]: newValue }));
    
    // Mark field as touched
    setTouched((prev) => ({ ...prev, [name]: true }));
    
    // Real-time validation for text inputs
    if (type !== 'checkbox' && touched[name]) {
      validateField(name, value);
    }
  };

  const handleBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setTouched((prev) => ({ ...prev, [name]: true }));
    validateField(name, value);
  };

  // Load remembered username on mount
  useEffect(() => {
    const rememberedUsername = localStorage.getItem('remember_username');
    if (rememberedUsername) {
      setFormData((prev) => ({ ...prev, username: rememberedUsername, rememberMe: true }));
    }
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden bg-white dark:bg-zinc-950 p-4">
      <ParticleBackground isDark={isDark} />
      
      {/* Static background effects */}
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
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 bg-white/20 dark:bg-zinc-800/20 hover:bg-white/30 dark:hover:bg-zinc-800/30 border border-white/10 dark:border-zinc-700/10 rounded-lg transition-all duration-200 backdrop-blur-sm"
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {isDark ? (
              <Sun className="w-4 h-4" />
            ) : (
              <Moon className="w-4 h-4" />
            )}
            <span>{isDark ? '亮色' : '暗色'}</span>
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
            {/* Username/Email field */}
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2 transition-colors">
                {t('login.username', 'Username or Email')}
              </label>
              <input
                type="text"
                id="username"
                name="username"
                value={formData.username}
                onChange={handleChange}
                onBlur={handleBlur}
                disabled={isLoading}
                className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
                  errors.username ? 'border-red-500 dark:border-red-400' : 'border-zinc-300 dark:border-zinc-700'
                } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder={t('login.usernamePlaceholder', 'Enter your username or email')}
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
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  id="password"
                  name="password"
                  value={formData.password}
                  onChange={handleChange}
                  onBlur={handleBlur}
                  disabled={isLoading}
                  className={`w-full px-4 py-3 pr-12 bg-white/50 dark:bg-zinc-800/50 border ${
                    errors.password ? 'border-red-500 dark:border-red-400' : 'border-zinc-300 dark:border-zinc-700'
                  } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                  placeholder={t('login.passwordPlaceholder', 'Enter your password')}
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <EyeOff className="w-5 h-5" />
                  ) : (
                    <Eye className="w-5 h-5" />
                  )}
                </button>
              </div>
              {errors.password && (
                <p className="mt-1 text-sm text-red-500 dark:text-red-400">{errors.password}</p>
              )}
            </div>

            {/* Remember me and Forgot password */}
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  name="rememberMe"
                  checked={formData.rememberMe}
                  onChange={handleChange}
                  disabled={isLoading}
                  className="w-4 h-4 text-emerald-600 bg-white/50 dark:bg-zinc-800/50 border-zinc-300 dark:border-zinc-700 rounded focus:ring-2 focus:ring-emerald-500 focus:ring-offset-0 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                />
                <span className="text-sm text-zinc-600 dark:text-zinc-400 transition-colors">
                  {t('login.rememberMe', 'Remember me')}
                </span>
              </label>
              <button
                type="button"
                className="text-sm text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 font-medium transition-colors"
                onClick={() => toast(t('login.forgotPasswordInfo', 'Please contact your administrator to reset your password'), { icon: 'ℹ️' })}
              >
                {t('login.forgotPassword', 'Forgot password?')}
              </button>
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
              className={`w-full py-3 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white font-medium rounded-lg transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/25 ${
                isLoading 
                  ? 'opacity-75 cursor-not-allowed scale-[0.98]' 
                  : 'hover:scale-[1.02] active:scale-[0.98]'
              }`}
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span className="animate-pulse">{t('login.signingIn', 'Signing in...')}</span>
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
