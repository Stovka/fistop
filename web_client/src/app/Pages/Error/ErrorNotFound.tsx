import * as React from 'react';
import { NavLink } from 'react-router-dom';
import { EmptyState, EmptyStateBody, EmptyStateIcon, Title, PageSection } from '@patternfly/react-core';
import ExclamationTriangleIcon from '@patternfly/react-icons/dist/js/icons/exclamation-triangle-icon';

import i18next from '../../Translations/i18n';

const ErrorNotFound: React.FunctionComponent = () => (
    <PageSection>
        <EmptyState>
            <EmptyStateIcon icon={ExclamationTriangleIcon} />
            <Title headingLevel="h4" size="lg">{i18next.t('error.not_found')}</Title>
            <EmptyStateBody>{i18next.t('error.not_found_description')}</EmptyStateBody>
            <br />
            <br />
            <NavLink to="/" className="pf-c-button">{i18next.t('error.return')}</NavLink>
        </EmptyState>
    </PageSection>
);

export default ErrorNotFound;
