import { Flex, FlexItem, Icon, PageHeaderTools, PageHeaderToolsItem, Switch, Tooltip } from "@patternfly/react-core";
import { NavLink, useLocation } from "react-router-dom";
import i18n from "../Translations/i18n";
import { getDarkTheme, toggleTheme } from "../Utils/Helpers";
import CogIcon from '@patternfly/react-icons/dist/esm/icons/cog-icon';
import LockIcon from '@patternfly/react-icons/dist/esm/icons/lock-icon';
import React from "react";


const HeaderTools: React.FunctionComponent<{ toggleChange: any }> = ({ toggleChange }) => {
  const [isDark, setIsDark] = React.useState(getDarkTheme())
  
  const location = useLocation();
  function handleSwitchTheme() {
    setIsDark(toggleTheme())
    toggleChange()
  }

  return (
    <PageHeaderTools>
      <Flex>
        <FlexItem>
          <PageHeaderToolsItem>
            <Switch
              isChecked={isDark}
              onChange={handleSwitchTheme}
              id="dark-mode-toggle"
              aria-label="Dark mode toggle"
              label={<span style={{ color: "grey" }}>{i18n.t("dashboard.dark")}</span>}
              labelOff={<span style={{ color: "grey" }}>{i18n.t("dashboard.light")}</span>}
              isReversed
            />
          </PageHeaderToolsItem>
        </FlexItem>
        <FlexItem>
          <PageHeaderToolsItem>
            <Switch
              id="reversed-switch"
              label={<span style={{ color: "grey" }}>CZ</span>}
              labelOff={<span style={{ color: "grey" }}>EN</span>}
              aria-label="CZ"
              isChecked={i18n.language === "cz"}
              onChange={() => {
                if (i18n.language === "en") {
                  i18n.changeLanguage("cz");
                  window.location.reload(); // Fix title
                } else {
                  i18n.changeLanguage("en");
                  window.location.reload(); // Fix title
                }
              }}
              isReversed
            />
          </PageHeaderToolsItem>
        </FlexItem>
        <FlexItem>
          <PageHeaderToolsItem>
            <Tooltip exitDelay={100} content={i18n.t("dashboard.admin")}>
              <NavLink to={location.pathname === "/admin" ? "/" : "/admin"}>
                <Icon status="info">
                  <LockIcon />
                </Icon>
              </NavLink>
            </Tooltip>
          </PageHeaderToolsItem>
        </FlexItem>
        <FlexItem>
          <PageHeaderToolsItem>
            <Tooltip exitDelay={100} content={i18n.t("dashboard.settings")}>
              <NavLink to={location.pathname === "/settings" ? "/" : "/settings"}>
                <Icon status="info">
                  <CogIcon />
                </Icon>
              </NavLink>
            </Tooltip>
          </PageHeaderToolsItem>
        </FlexItem>
        <FlexItem>
        </FlexItem>
      </Flex>
    </PageHeaderTools>
  );
}

export default HeaderTools;