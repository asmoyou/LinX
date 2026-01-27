import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import zh from './locales/zh.json';

i18n
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      zh: { translation: zh },
    },
    lng: localStorage.getItem('language') || 'zh', // 默认中文
    fallbackLng: 'zh',
    interpolation: {
      escapeValue: false,
    },
  });

// Listen for language changes and persist to localStorage
i18n.on('languageChanged', (lng) => {
  localStorage.setItem('language', lng);
});

export default i18n;
