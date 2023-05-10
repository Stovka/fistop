import * as React from 'react';
import { Route } from 'react-router-dom';

import ErrorNotFound from '../Pages/Error/ErrorNotFound';
import Settings from "../Pages/Settings"
import Admin from "../Pages/Admin";
import EmptyLayout from "../Layouts/EmptyLayout";
import DefaultLayout from "../Layouts/DefaultLayout";

import i18next from '../Translations/i18n';

export interface IAppRoute {
    component: React.FunctionComponent<{ title: any }>;
    title: string;
    label: string;
    path: string;
    subRoutes: IAppRoute[];
}

export const routes: IAppRoute[] = [
    {
        component: DefaultLayout,
        title: i18next.t('routes.dashboard'),
        label: i18next.t('routes.dashboard'),
        path: '/',
        subRoutes: [] as IAppRoute[],
    },
    {
        component: Settings,
        title: i18next.t('routes.settings'),
        label: i18next.t('routes.settings'),
        path: '/settings',
        subRoutes: [] as IAppRoute[],
    },
    {
        component: Admin,
        title: i18next.t('routes.admin'),
        label: i18next.t('routes.admin'),
        path: '/admin',
        subRoutes: [] as IAppRoute[],
    },
    {
        component: ErrorNotFound,
        title: i18next.t('routes.error_not_found'),
        label: i18next.t('routes.error_not_found'),
        path: '*',
        subRoutes: [] as IAppRoute[],
    }
];

const FlattenRoutes = (rts: IAppRoute[]) => {
    let flattened: Array<IAppRoute> = [] as Array<IAppRoute>;
    for (const r of rts) {
        flattened.push(r);
        const tmp = FlattenRoutes(r.subRoutes);
        flattened = flattened.concat(tmp);
    }
    return flattened;
};

export const GetRoutes = (): React.ReactElement[] => {
    const generatedRoutes: React.ReactElement[] = [];
    const flatRoutes = FlattenRoutes(routes);
    for (const r of flatRoutes) {
        let component: React.ReactElement;
        if (r.path === "/") {
            component = (
                <DefaultLayout title={r.title} />
            );
        } else {
            component = (
                <EmptyLayout title={r.title}>
                    <r.component title={r.title} />
                </EmptyLayout>
            );
        }
        generatedRoutes.push(<Route path={r.path} element={component} key={r.title} />);
    }
    return generatedRoutes;
};
