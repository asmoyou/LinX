import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { UserPlus, Loader2, Moon, Sun, Eye, EyeOff } from 'lucide-react';
import { authApi } from '../api';
import { useThemeStore } from '../stores/themeStore';
import toast from 'react-hot-toast';
import { LanguageSwitcher } from '../components/LanguageSwitcher';
import { ParticleBackground } from '../components/ParticleBackground';

export default function Register() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { theme, setTheme, applyTheme } = useThemeStore();
  const [isDark, setIsDark] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  
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
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [isLoading, setIsLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [passwordStrength, setPasswordStrength] = useState<'weak' | 'medium' | 'strong'>('weak');

  // Calculate password strength
  const calculatePasswordStrength = (password: string): 'weak' | 'medium' | 'strong' => {
    if (password.length === 0) return 'weak';
    
    let strength = 0;
    if (password.length >= 8) strength++;
    if (password.length >= 12) strength++;
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength++;
    if (/\d/.test(password)) strength++;
    if (/[^a-zA-Z0-9]/.test(password)) strength++;
    
    if (strength <= 2) return 'weak';
    if (strength <= 4) return 'medium';
    return 'strong';
  };

  const validateField = (name: string, value: string) => {
    const newErrors = { ...errors };

    if (name === 'username') {
      if (!value.trim()) {
        newErrors.username = t('register.errors.usernameRequired', 'Username is required');
      } else if (value.length < 3) {
        newErrors.username = t('register.errors.usernameTooShort', 'Username must be at least 3 characters');
      } else if (!/^[a-zA-Z0-9_-]+$/.test(value)) {
        newErrors.username = t('register.errors.usernameInvalid', 'Username can only contain letters, numbers, underscores and hyphens');
      } else {
        delete newErrors.username;
      }
    }

    if (name === 'email') {
      if (!value.trim()) {
        newErrors.email = t('register.errors.emailRequired', 'Email is required');
      } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
        newErrors.email = t('register.errors.emailInvalid', 'Email is invalid');
      } else {
        delete newErrors.email;
      }
    }

    if (name === 'password') {
      if (!value) {
        newErrors.password = t('register.errors.passwordRequired', 'Password is required');
      } else if (value.length < 6) {
        newErrors.password = t('register.errors.passwordTooShort', 'Password must be at least 6 characters');
      } else {
        delete newErrors.password;
      }
      
      // Update password strength
      setPasswordStrength(calculatePasswordStrength(value));
      
      // Re-validate confirm password if it has been touched
      if (touched.confirmPassword && formData.confirmPassword) {
        if (value !== formData.confirmPassword) {
          newErrors.confirmPassword = t('register.errors.passwordMismatch', 'Passwords do not match');
        } else {
          delete newErrors.confirmPassword;
        }
      }
    }

    if (name === 'confirmPassword') {
      if (!value) {
        newErrors.confirmPassword = t('register.errors.confirmPasswordRequired', 'Please confirm your password');
      } else if (value !== formData.password) {
        newErrors.confirmPassword = t('register.errors.passwordMismatch', 'Passwords do not match');
      } else {
        delete newErrors.confirmPassword;
      }
    }

    setErrors(newErrors);
  };

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    // Username validation
    if (!formData.username.trim()) {
      newErrors.username = t('register.errors.usernameRequired', 'Username is required');
    } else if (formData.username.length < 3) {
      newErrors.username = t('register.errors.usernameTooShort', 'Username must be at least 3 characters');
    } else if (!/^[a-zA-Z0-9_-]+$/.test(formData.username)) {
      newErrors.username = t('register.errors.usernameInvalid', 'Username can only contain letters, numbers, underscores and hyphens');
    }

    // Email validation
    if (!formData.email.trim()) {
      newErrors.email = t('register.errors.emailRequired', 'Email is required');
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      newErrors.email = t('register.errors.emailInvalid', 'Email is invalid');
    }

    // Password validation
    if (!formData.password) {
      newErrors.password = t('register.errors.passwordRequired', 'Password is required');
    } else if (formData.password.length < 6) {
      newErrors.password = t('register.errors.passwordTooShort', 'Password must be at least 6 characters');
    }

    // Confirm password validation
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
      await authApi.register({
        username: formData.username,
        email: formData.email,
        password: formData.password,
      });

      toast.success(t('register.success', 'Registration successful!'));
      navigate('/login');
    } catch (error: any) {
      console.error('Registration failed:', error);
      
      const errorMessage = error.response?.data?.detail ||
        error.response?.data?.message || 
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
    
    // Mark field as touched
    setTouched((prev) => ({ ...prev, [name]: true }));
    
    // Real-time validation if field has been touched
    if (touched[name]) {
      validateField(name, value);
    }
  };

  const handleBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setTouched((prev) => ({ ...prev, [name]: true }));
    validateField(name, value);
  };

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden bg-white dark:bg-zinc-950 p-4 transition-colors duration-500">
      <ParticleBackground isDark={isDark} />
      
      {/* Static background effects */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none" style={{ zIndex: 1 }}>
        {/* Subtle grid pattern overlay */}
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              'linear-gradient(to right, #80808008 1px, transparent 1px), linear-gradient(to bottom, #80808008 1px, transparent 1px)',
            backgroundSize: '4rem 4rem',
            maskImage:
              'radial-gradient(ellipse 80% 50% at 50% 50%, #000 70%, transparent 110%)',
          }}
        />
      </div>

      {/* Register card */}
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
              {t('register.title', 'Create Account')}
            </h1>
            <p className="text-zinc-600 dark:text-zinc-400 transition-colors">
              {t('register.subtitle', 'Join LinX Platform')}
            </p>
          </div>

          {/* Register form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Username field */}
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2 transition-colors">
                {t('register.username', 'Username')}
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
                placeholder={t('register.usernamePlaceholder', 'Choose a username')}
                autoComplete="username"
                autoFocus
              />
              {errors.username && (
                <p className="mt-1 text-sm text-red-500 dark:text-red-400">{errors.username}</p>
              )}
            </div>

            {/* Email field */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2 transition-colors">
                {t('register.email', 'Email')}
              </label>
              <input
                type="email"
                id="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                onBlur={handleBlur}
                disabled={isLoading}
                className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
                  errors.email ? 'border-red-500 dark:border-red-400' : 'border-zinc-300 dark:border-zinc-700'
                } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                placeholder={t('register.emailPlaceholder', 'Enter your email')}
                autoComplete="email"
              />
              {errors.email && (
                <p className="mt-1 text-sm text-red-500 dark:text-red-400">{errors.email}</p>
              )}
            </div>

            {/* Password field */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2 transition-colors">
                {t('register.password', 'Password')}
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
                  placeholder={t('register.passwordPlaceholder', 'Create a password')}
                  autoComplete="new-password"
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
              {/* Password strength indicator */}
              {formData.password && !errors.password && (
                <div className="mt-2">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-zinc-600 dark:text-zinc-400">
                      {t('register.passwordStrength', 'Password Strength')}:
                    </span>
                    <span className={`text-xs font-medium ${
                      passwordStrength === 'weak' ? 'text-red-500' :
                      passwordStrength === 'medium' ? 'text-yellow-500' :
                      'text-green-500'
                    }`}>
                      {passwordStrength === 'weak' && t('register.passwordStrengthWeak', 'Weak')}
                      {passwordStrength === 'medium' && t('register.passwordStrengthMedium', 'Medium')}
                      {passwordStrength === 'strong' && t('register.passwordStrengthStrong', 'Strong')}
                    </span>
                  </div>
                  <div className="flex gap-1">
                    <div className={`h-1 flex-1 rounded-full transition-colors ${
                      passwordStrength === 'weak' ? 'bg-red-500' :
                      passwordStrength === 'medium' ? 'bg-yellow-500' :
                      'bg-green-500'
                    }`} />
                    <div className={`h-1 flex-1 rounded-full transition-colors ${
                      passwordStrength === 'medium' ? 'bg-yellow-500' :
                      passwordStrength === 'strong' ? 'bg-green-500' :
                      'bg-zinc-300 dark:bg-zinc-700'
                    }`} />
                    <div className={`h-1 flex-1 rounded-full transition-colors ${
                      passwordStrength === 'strong' ? 'bg-green-500' : 'bg-zinc-300 dark:bg-zinc-700'
                    }`} />
                  </div>
                  <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                    {t('register.passwordRequirements', 'Password requirements: at least 6 characters')}
                  </p>
                </div>
              )}
            </div>

            {/* Confirm Password field */}
            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2 transition-colors">
                {t('register.confirmPassword', 'Confirm Password')}
              </label>
              <div className="relative">
                <input
                  type={showConfirmPassword ? "text" : "password"}
                  id="confirmPassword"
                  name="confirmPassword"
                  value={formData.confirmPassword}
                  onChange={handleChange}
                  onBlur={handleBlur}
                  disabled={isLoading}
                  className={`w-full px-4 py-3 pr-12 bg-white/50 dark:bg-zinc-800/50 border ${
                    errors.confirmPassword ? 'border-red-500 dark:border-red-400' : 'border-zinc-300 dark:border-zinc-700'
                  } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all disabled:opacity-50 disabled:cursor-not-allowed`}
                  placeholder={t('register.confirmPasswordPlaceholder', 'Confirm your password')}
                  autoComplete="new-password"
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
                  tabIndex={-1}
                >
                  {showConfirmPassword ? (
                    <EyeOff className="w-5 h-5" />
                  ) : (
                    <Eye className="w-5 h-5" />
                  )}
                </button>
              </div>
              {errors.confirmPassword && (
                <p className="mt-1 text-sm text-red-500 dark:text-red-400">{errors.confirmPassword}</p>
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
              className={`w-full py-3 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white font-medium rounded-lg transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/25 ${
                isLoading 
                  ? 'opacity-75 cursor-not-allowed scale-[0.98]' 
                  : 'hover:scale-[1.02] active:scale-[0.98]'
              }`}
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span className="animate-pulse">{t('register.creatingAccount', 'Creating account...')}</span>
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
            <p className="text-zinc-600 dark:text-zinc-400 transition-colors">
              {t('register.haveAccount', 'Already have an account?')}{' '}
              <Link
                to="/login"
                className="text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 font-medium transition-colors"
              >
                {t('register.signIn', 'Sign in')}
              </Link>
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-8 text-center text-zinc-500 dark:text-zinc-500 text-sm transition-colors">
          <p>{t('register.footer', '© 2026 灵枢科技. All rights reserved.')}</p>
        </div>
      </div>
    </div>
  );
}
