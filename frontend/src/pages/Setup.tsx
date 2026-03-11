import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, Globe2, Loader2, LockKeyhole, Moon, ShieldCheck, Sun } from 'lucide-react';
import toast from 'react-hot-toast';

import { authApi } from '../api';
import { ParticleBackground } from '../components/ParticleBackground';
import { useAuthStore } from '../stores';
import { useThemeStore } from '../stores/themeStore';

const COMMON_TIMEZONES = [
  'UTC',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Singapore',
  'Europe/London',
  'Europe/Berlin',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
];

type SetupLanguage = 'zh' | 'en';
type SetupTheme = 'light' | 'dark' | 'system';

interface SetupProps {
  defaultAdminUsername?: string;
  onSetupComplete?: () => Promise<void> | void;
}

const getDetectedTimezone = (): string => {
  if (typeof Intl === 'undefined') {
    return 'UTC';
  }

  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
};

const getCopy = (language: SetupLanguage) =>
  language === 'zh'
    ? {
        title: '项目首次初始化',
        subtitle: '创建首个管理员账号，并设置平台的基础偏好。',
        adminCardTitle: '管理员账号',
        adminCardBody: '首次安装只会创建一个默认超级管理员账号，账号名固定为 admin。',
        platformCardTitle: '平台偏好',
        platformCardBody: '初始化时设置的语言、时区和主题会作为首个管理员的默认偏好保存。',
        accountLabel: '管理员账号',
        emailLabel: '管理员邮箱',
        emailPlaceholder: '请输入管理员邮箱',
        passwordLabel: '管理员密码',
        passwordPlaceholder: '请输入高强度密码',
        confirmPasswordLabel: '确认密码',
        confirmPasswordPlaceholder: '请再次输入密码',
        languageLabel: '默认语言',
        timezoneLabel: '默认时区',
        themeLabel: '默认主题',
        submit: '完成初始化',
        submitting: '正在初始化...',
        passwordHint: '密码至少 8 位，且必须包含大小写字母、数字和特殊字符。',
        success: '初始化完成，正在进入系统。',
        setupOnlyOnce: '首次安装向导只会在没有管理员账号时出现。',
        themeLight: '浅色',
        themeDark: '深色',
        themeSystem: '跟随系统',
        languageChinese: '简体中文',
        languageEnglish: 'English',
        timelineTitle: '初始化会完成这些事情',
        timelineItems: [
          '创建默认管理员账号 admin',
          '保存首个管理员的语言、时区和主题偏好',
          '自动登录并进入控制台',
        ],
        errors: {
          emailRequired: '管理员邮箱不能为空。',
          emailInvalid: '请输入有效的邮箱地址。',
          passwordRequired: '管理员密码不能为空。',
          passwordWeak: '密码强度不足，请补齐大小写字母、数字和特殊字符。',
          confirmPasswordRequired: '请再次输入管理员密码。',
          confirmPasswordMismatch: '两次输入的密码不一致。',
          timezoneRequired: '请选择平台默认时区。',
          submitFailed: '初始化失败，请稍后重试。',
        },
      }
    : {
        title: 'Initialize Your Workspace',
        subtitle: 'Create the first administrator account and set the platform defaults.',
        adminCardTitle: 'Administrator Account',
        adminCardBody:
          'The first installation creates a single default super admin account. The username is fixed as admin.',
        platformCardTitle: 'Platform Preferences',
        platformCardBody:
          'Language, timezone, and theme selected here are saved as the first administrator preferences.',
        accountLabel: 'Admin Username',
        emailLabel: 'Admin Email',
        emailPlaceholder: 'Enter the administrator email',
        passwordLabel: 'Admin Password',
        passwordPlaceholder: 'Create a strong password',
        confirmPasswordLabel: 'Confirm Password',
        confirmPasswordPlaceholder: 'Enter the password again',
        languageLabel: 'Default Language',
        timezoneLabel: 'Default Timezone',
        themeLabel: 'Default Theme',
        submit: 'Finish Setup',
        submitting: 'Initializing...',
        passwordHint:
          'Use at least 8 characters and include uppercase, lowercase, numbers, and symbols.',
        success: 'Setup completed. Redirecting into the workspace.',
        setupOnlyOnce: 'This first-run guide is only shown while no admin account exists.',
        themeLight: 'Light',
        themeDark: 'Dark',
        themeSystem: 'System',
        languageChinese: 'Simplified Chinese',
        languageEnglish: 'English',
        timelineTitle: 'This setup will',
        timelineItems: [
          'Create the default administrator account admin',
          'Save language, timezone, and theme preferences',
          'Sign in automatically and open the dashboard',
        ],
        errors: {
          emailRequired: 'Administrator email is required.',
          emailInvalid: 'Enter a valid email address.',
          passwordRequired: 'Administrator password is required.',
          passwordWeak:
            'Password is too weak. Include uppercase, lowercase, numbers, and symbols.',
          confirmPasswordRequired: 'Confirm the administrator password.',
          confirmPasswordMismatch: 'The two passwords do not match.',
          timezoneRequired: 'Select a default timezone.',
          submitFailed: 'Setup failed. Please try again.',
        },
      };

const isStrongPassword = (password: string): boolean => {
  if (password.length < 8) {
    return false;
  }

  const hasUpper = /[A-Z]/.test(password);
  const hasLower = /[a-z]/.test(password);
  const hasDigit = /\d/.test(password);
  const hasSpecial = /[^A-Za-z0-9]/.test(password);

  return hasUpper && hasLower && hasDigit && hasSpecial;
};

export default function Setup({
  defaultAdminUsername = 'admin',
  onSetupComplete,
}: SetupProps) {
  const navigate = useNavigate();
  const { i18n } = useTranslation();
  const { login } = useAuthStore();
  const { theme, setTheme, applyTheme } = useThemeStore();
  const [isDark, setIsDark] = useState(false);
  const currentLanguage = (i18n.language.startsWith('zh') ? 'zh' : 'en') as SetupLanguage;
  const copy = getCopy(currentLanguage);
  const [formData, setFormData] = useState(() => ({
    email: '',
    password: '',
    confirmPassword: '',
    language: currentLanguage,
    timezone: getDetectedTimezone(),
    theme: theme as SetupTheme,
  }));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    applyTheme();

    const updateIsDark = () => {
      const dark =
        theme === 'dark' ||
        (theme === 'system' &&
          window.matchMedia('(prefers-color-scheme: dark)').matches);
      setIsDark(dark);
    };

    updateIsDark();

    if (theme === 'system') {
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      mediaQuery.addEventListener('change', updateIsDark);
      return () => mediaQuery.removeEventListener('change', updateIsDark);
    }
  }, [theme, applyTheme]);

  useEffect(() => {
    setFormData((prev) => ({
      ...prev,
      language: currentLanguage,
    }));
  }, [currentLanguage]);

  const timezoneOptions = useMemo(() => {
    if (COMMON_TIMEZONES.includes(formData.timezone)) {
      return COMMON_TIMEZONES;
    }
    return [formData.timezone, ...COMMON_TIMEZONES];
  }, [formData.timezone]);

  const validateForm = () => {
    const nextErrors: Record<string, string> = {};

    if (!formData.email.trim()) {
      nextErrors.email = copy.errors.emailRequired;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      nextErrors.email = copy.errors.emailInvalid;
    }

    if (!formData.password) {
      nextErrors.password = copy.errors.passwordRequired;
    } else if (!isStrongPassword(formData.password)) {
      nextErrors.password = copy.errors.passwordWeak;
    }

    if (!formData.confirmPassword) {
      nextErrors.confirmPassword = copy.errors.confirmPasswordRequired;
    } else if (formData.confirmPassword !== formData.password) {
      nextErrors.confirmPassword = copy.errors.confirmPasswordMismatch;
    }

    if (!formData.timezone) {
      nextErrors.timezone = copy.errors.timezoneRequired;
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const toggleThemePreview = () => {
    const nextTheme: SetupTheme = isDark ? 'light' : 'dark';
    setTheme(nextTheme);
    setFormData((prev) => ({ ...prev, theme: nextTheme }));
  };

  const handleTextChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    setErrors((prev) => ({ ...prev, [name]: '' }));
  };

  const handleSelectChange = async (
    event: React.ChangeEvent<HTMLSelectElement>,
  ) => {
    const { name, value } = event.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    setErrors((prev) => ({ ...prev, [name]: '' }));

    if (name === 'language') {
      await i18n.changeLanguage(value);
    }

    if (name === 'theme') {
      setTheme(value as SetupTheme);
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsLoading(true);
    setErrors({});

    try {
      const response = await authApi.initializePlatform({
        email: formData.email.trim(),
        password: formData.password,
        language: formData.language,
        timezone: formData.timezone,
        theme: formData.theme,
      });

      login(response.user, response.access_token);
      localStorage.setItem('refresh_token', response.refresh_token);
      await i18n.changeLanguage(formData.language);
      setTheme(formData.theme);
      await onSetupComplete?.();

      toast.success(copy.success);
      navigate('/dashboard', { replace: true });
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.detail || copy.errors.submitFailed;
      setErrors({ submit: errorMessage });
      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center relative overflow-hidden bg-white dark:bg-zinc-950 p-4 transition-colors duration-500">
      <ParticleBackground isDark={isDark} />

      <div
        className="absolute inset-0 overflow-hidden pointer-events-none"
        style={{ zIndex: 1 }}
      >
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808008_1px,transparent_1px),linear-gradient(to_bottom,#80808008_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_50%,#000_70%,transparent_110%)]" />
      </div>

      <div className="relative w-full max-w-6xl z-10">
        <div className="flex justify-end items-center mb-4">
          <button
            onClick={toggleThemePreview}
            className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 bg-white/20 dark:bg-zinc-800/20 hover:bg-white/30 dark:hover:bg-zinc-800/30 border border-white/10 dark:border-zinc-700/10 rounded-lg transition-all duration-200 backdrop-blur-sm"
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            <span>{isDark ? copy.themeLight : copy.themeDark}</span>
          </button>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.05fr_1.2fr]">
          <section className="backdrop-blur-xl bg-zinc-950/85 dark:bg-black/60 border border-emerald-500/10 rounded-3xl shadow-2xl shadow-emerald-950/20 p-8 text-zinc-50">
            <div className="inline-flex items-center gap-3 px-4 py-2 rounded-full bg-emerald-500/10 border border-emerald-400/20 text-emerald-200 text-sm">
              <ShieldCheck className="w-4 h-4" />
              <span>{copy.setupOnlyOnce}</span>
            </div>

            <div className="mt-6">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-white/10 border border-white/10 mb-5">
                <img src="/logo-md.webp" alt="LinX Logo" className="w-10 h-10 object-contain" />
              </div>
              <h1 className="text-4xl font-semibold tracking-tight">{copy.title}</h1>
              <p className="mt-3 text-zinc-300 leading-7">{copy.subtitle}</p>
            </div>

            <div className="mt-8 space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
                <div className="flex items-center gap-3">
                  <LockKeyhole className="w-5 h-5 text-emerald-300" />
                  <h2 className="text-lg font-medium">{copy.adminCardTitle}</h2>
                </div>
                <p className="mt-3 text-sm leading-6 text-zinc-300">{copy.adminCardBody}</p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
                <div className="flex items-center gap-3">
                  <Globe2 className="w-5 h-5 text-emerald-300" />
                  <h2 className="text-lg font-medium">{copy.platformCardTitle}</h2>
                </div>
                <p className="mt-3 text-sm leading-6 text-zinc-300">{copy.platformCardBody}</p>
              </div>
            </div>

            <div className="mt-8 rounded-2xl border border-white/10 bg-emerald-500/10 p-5">
              <h3 className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-200">
                {copy.timelineTitle}
              </h3>
              <ul className="mt-4 space-y-3">
                {copy.timelineItems.map((item) => (
                  <li key={item} className="flex items-start gap-3 text-sm text-zinc-100">
                    <CheckCircle2 className="w-4 h-4 mt-0.5 text-emerald-300" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className="backdrop-blur-xl bg-white/85 dark:bg-zinc-900/85 border border-zinc-200/60 dark:border-zinc-800/60 rounded-3xl shadow-2xl shadow-zinc-950/10 p-8">
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="grid gap-5 md:grid-cols-2">
                <div>
                  <label htmlFor="account" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                    {copy.accountLabel}
                  </label>
                  <input
                    id="account"
                    value={defaultAdminUsername}
                    disabled
                    className="w-full px-4 py-3 rounded-xl border border-zinc-200 dark:border-zinc-700 bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400"
                  />
                </div>

                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                    {copy.emailLabel}
                  </label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    value={formData.email}
                    onChange={handleTextChange}
                    disabled={isLoading}
                    className={`w-full px-4 py-3 rounded-xl border ${
                      errors.email ? 'border-red-500 dark:border-red-400' : 'border-zinc-300 dark:border-zinc-700'
                    } bg-white/80 dark:bg-zinc-800/70 text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all`}
                    placeholder={copy.emailPlaceholder}
                    autoComplete="email"
                  />
                  {errors.email ? <p className="mt-1 text-sm text-red-500">{errors.email}</p> : null}
                </div>
              </div>

              <div className="grid gap-5 md:grid-cols-2">
                <div>
                  <label htmlFor="password" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                    {copy.passwordLabel}
                  </label>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    value={formData.password}
                    onChange={handleTextChange}
                    disabled={isLoading}
                    className={`w-full px-4 py-3 rounded-xl border ${
                      errors.password ? 'border-red-500 dark:border-red-400' : 'border-zinc-300 dark:border-zinc-700'
                    } bg-white/80 dark:bg-zinc-800/70 text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all`}
                    placeholder={copy.passwordPlaceholder}
                    autoComplete="new-password"
                  />
                  <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">{copy.passwordHint}</p>
                  {errors.password ? <p className="mt-1 text-sm text-red-500">{errors.password}</p> : null}
                </div>

                <div>
                  <label htmlFor="confirmPassword" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                    {copy.confirmPasswordLabel}
                  </label>
                  <input
                    id="confirmPassword"
                    name="confirmPassword"
                    type="password"
                    value={formData.confirmPassword}
                    onChange={handleTextChange}
                    disabled={isLoading}
                    className={`w-full px-4 py-3 rounded-xl border ${
                      errors.confirmPassword ? 'border-red-500 dark:border-red-400' : 'border-zinc-300 dark:border-zinc-700'
                    } bg-white/80 dark:bg-zinc-800/70 text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all`}
                    placeholder={copy.confirmPasswordPlaceholder}
                    autoComplete="new-password"
                  />
                  {errors.confirmPassword ? (
                    <p className="mt-1 text-sm text-red-500">{errors.confirmPassword}</p>
                  ) : null}
                </div>
              </div>

              <div className="grid gap-5 md:grid-cols-3">
                <div>
                  <label htmlFor="language" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                    {copy.languageLabel}
                  </label>
                  <select
                    id="language"
                    name="language"
                    value={formData.language}
                    onChange={handleSelectChange}
                    disabled={isLoading}
                    className="w-full px-4 py-3 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/80 dark:bg-zinc-800/70 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                  >
                    <option value="zh">{copy.languageChinese}</option>
                    <option value="en">{copy.languageEnglish}</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="timezone" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                    {copy.timezoneLabel}
                  </label>
                  <select
                    id="timezone"
                    name="timezone"
                    value={formData.timezone}
                    onChange={handleSelectChange}
                    disabled={isLoading}
                    className={`w-full px-4 py-3 rounded-xl border ${
                      errors.timezone ? 'border-red-500 dark:border-red-400' : 'border-zinc-300 dark:border-zinc-700'
                    } bg-white/80 dark:bg-zinc-800/70 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all`}
                  >
                    {timezoneOptions.map((zone) => (
                      <option key={zone} value={zone}>
                        {zone}
                      </option>
                    ))}
                  </select>
                  {errors.timezone ? <p className="mt-1 text-sm text-red-500">{errors.timezone}</p> : null}
                </div>

                <div>
                  <label htmlFor="theme" className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2">
                    {copy.themeLabel}
                  </label>
                  <select
                    id="theme"
                    name="theme"
                    value={formData.theme}
                    onChange={handleSelectChange}
                    disabled={isLoading}
                    className="w-full px-4 py-3 rounded-xl border border-zinc-300 dark:border-zinc-700 bg-white/80 dark:bg-zinc-800/70 text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
                  >
                    <option value="light">{copy.themeLight}</option>
                    <option value="dark">{copy.themeDark}</option>
                    <option value="system">{copy.themeSystem}</option>
                  </select>
                </div>
              </div>

              {errors.submit ? (
                <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/30 rounded-xl transition-colors">
                  <p className="text-sm text-red-600 dark:text-red-400">{errors.submit}</p>
                </div>
              ) : null}

              <button
                type="submit"
                disabled={isLoading}
                className={`w-full py-3.5 px-4 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white font-medium rounded-xl transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/20 ${
                  isLoading ? 'opacity-75 cursor-not-allowed scale-[0.98]' : 'hover:scale-[1.01] active:scale-[0.98]'
                }`}
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    {copy.submitting}
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-5 h-5" />
                    {copy.submit}
                  </>
                )}
              </button>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
