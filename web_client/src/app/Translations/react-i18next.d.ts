import 'react-i18next';
import { resources } from '@app/Translations/i18n';

declare module 'react-i18next' {
    interface CustomTypeOptions {
        defaultNS: 'common';
        resources: {
            en: (typeof resources)['en']['translation'];
            cz: (typeof resources)['cz']['translation'];
        };
    }
}
