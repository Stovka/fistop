import React from 'react';
import {
  Alert,
  AlertGroup,
  AlertActionCloseButton,
} from '@patternfly/react-core';

const Alerts: React.FunctionComponent<{ alerts: any, removeAlert: any }> = ({ alerts, removeAlert }) => {
  
  const alertsElements = []
  for (let i = 0; i < alerts.length; i++) {
    alertsElements.push(
      <Alert
        isExpandable={alerts[i].comment === "" ? false : true}
        variant={alerts[i].variant}
        title={alerts[i].title}
        actionClose={
          <AlertActionCloseButton
            title={alerts[i].title as string}
            variantLabel={`${alerts[i].variant} alert`}
            onClose={() => removeAlert(i)}
          />
        }
        key={i}
      >
        <p>{alerts[i].comment}</p>
      </Alert>
    )
  }

  return (
    <React.Fragment>
      <AlertGroup isToast isLiveRegion>
        {alertsElements}
      </AlertGroup>
    </React.Fragment>
  );
};
export default Alerts;