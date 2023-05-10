import '../App.css';
import * as React from 'react';
import '@patternfly/react-core/dist/styles/base.css';
import {
  Page,
  PageHeader,
} from '@patternfly/react-core';
import { UseDocumentTitle } from "../Utils/Helpers";
import HeaderTools from '../Components/HeaderTools';

export interface IAppLayout {
  children: React.ReactNode;
  title: string;
}

const EmptyLayout: React.FunctionComponent<IAppLayout> = ({ children, title }) => {
  UseDocumentTitle(title);
  const [change, toggleChange] = React.useState(true);

  return (
    <Page
      mainContainerId="primary-app-container"
      header={<PageHeader headerTools={<HeaderTools toggleChange={toggleChange} />} />}
    >
      {children}
    </Page>
  );
};

export default EmptyLayout;
