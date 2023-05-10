import i18next from 'i18next';
import { initReactI18next } from 'react-i18next';
import detector from 'i18next-browser-languagedetector';
import Backend from 'i18next-http-backend';

import commonEN from '../Translations/locales/en/common.json';
import commonCZ from '../Translations/locales/cz/common.json';

export const resources = {
    en: {
        translation: commonEN,
    },
    cz: {
        translation: commonCZ,
    },
} as const;

i18next
    .use(Backend)
    .use(detector) // .use(reactI18nextModule)
    .use(initReactI18next)
    .init({
        fallbackLng: 'cz',
        resources,
        interpolation: {
            escapeValue: false,
        },
        react: {
            bindI18n: 'languageChanged',
        },
    });

export default i18next;
