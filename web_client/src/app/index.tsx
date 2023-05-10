import * as React from 'react';
import { BrowserRouter } from 'react-router-dom';
import { withTranslation } from 'react-i18next';
import './Translations/i18n';
import './App.css';

import '@patternfly/react-core/dist/styles/base.css';


import AppRoutes from './Router/Router';


const App: React.FunctionComponent = () => (
    <BrowserRouter basename="/">
      <AppRoutes />
    </BrowserRouter>
);

export default withTranslation()(App);
