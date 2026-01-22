import { useTranslation } from 'react-i18next';
import { Globe } from 'lucide-react';

export const LanguageSwitcher = () => {
  const { i18n } = useTranslation();

  const toggleLanguage = () => {
    const newLang = i18n.language === 'zh' ? 'en' : 'zh';
    i18n.changeLanguage(newLang);
    localStorage.setItem('language', newLang);
  };

  return (
    <button
      onClick={toggleLanguage}
      className="flex items-center gap-2 px-3 py-2 text-sm font-medium text-zinc-700 dark:text-zinc-300 bg-white/20 dark:bg-zinc-800/20 hover:bg-white/30 dark:hover:bg-zinc-800/30 border border-white/10 dark:border-zinc-700/10 rounded-lg transition-all duration-200 backdrop-blur-sm"
      aria-label="Switch language"
      title={i18n.language === 'zh' ? 'Switch to English' : '切换到中文'}
    >
      <Globe className="w-4 h-4" />
      <span>{i18n.language === 'zh' ? '中文' : 'English'}</span>
    </button>
  );
};
