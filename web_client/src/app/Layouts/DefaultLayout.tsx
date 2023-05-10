import '../App.css';
import * as React from 'react';
import '@patternfly/react-core/dist/styles/base.css';
import {
  Page,
  PageHeader,
  PageSidebar,
  ToolbarItem,
  SearchInput,
  Select,
  SelectOption,
  Divider,
  SelectVariant,
  Label,
  PageSection,
  AlertProps,
  BackToTop,
  Tooltip,
  Button,
  ModalVariant,
  Modal,
  Form,
  FormGroup,
  TextInput,
  Text,
  TextVariants,
  Switch
} from '@patternfly/react-core';
import InfoCircleIcon from '@patternfly/react-icons/dist/esm/icons/info-circle-icon';
import { addData, getDataLength, getNotDetect, isTermsAccepted, getToken, setCurrentResultID, UseDocumentTitle, acceptTerms, setToken } from "../Utils/Helpers";
import { getAPIGroups, getAPIServicesMore, getAPIUser, getAPIUserList } from "../Utils/API";

import { getDarkTheme } from "../Utils/Helpers";
import HeaderTools from "../Components/HeaderTools";
import History from "../Components/History";
import Result from "../Components/Result";
import Alerts from "../Components/Alerts";
import i18next from 'i18next';


const DefaultLayout: React.FunctionComponent<{ title: any }> = ({ title }) => {
  const searchInput = React.useRef("");
  const searchDetectedType = React.useRef("");
  const searchType = React.useRef("auto");
  const [isNavOpen, setIsNavOpen] = React.useState(true);
  const [services, setServices] = React.useState({})
  const [groups, setGroups] = React.useState({})
  const [change, toggleChange] = React.useState(true);
  const [alerts, setAlerts] = React.useState<{ title: string, comment: string, variant: AlertProps["variant"], key: number }[]>([]);

  getDarkTheme(); // set data-theme to html
  UseDocumentTitle(title);
  function handleToggleChange() {
    toggleChange(!change);
  }
  function handleAcceptTerms() {
    acceptTerms()
    handleToggleChange()
  }
  const addAlert = (title: string, comment: string, variant: AlertProps["variant"], key: number) => {
    setAlerts(prevAlerts => [...prevAlerts, { title, comment, variant, key }]);
  };
  /*
  const addSuccessAlert = (title: string, comment: string) => {
    addAlert(title, comment, "success", alerts.length);
  };
  const addInfoAlert = (title: string, comment: string) => {
    addAlert(title, comment, "info", alerts.length);
  };
  */
  const addDangerAlert = (title: string, comment: string) => {
    addAlert(title, comment, "danger", alerts.length);
  };
  const removeAlert = (key: number) => {
    setAlerts(prevAlerts => {
      const newAlerts: any[] = []
      for (const alert of prevAlerts) {
        if (alert.key !== key) {
          alert.key = newAlerts.length
          newAlerts.push(alert)
        }
      }
      return newAlerts;
    })
  };
  // Get groups once
  React.useEffect(() => {
    const getGroupsOptions = async () => {
      const data = await getAPIGroups(getToken());
      if (data === null || data === undefined) {
        addDangerAlert(i18next.t("error.fetch"), i18next.t("error.fetch_groups"))
        return;
      }
      setGroups(data);
    }
    getGroupsOptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Get services once
  React.useEffect(() => {
    const getServicesOptions = async () => {
      const data = await getAPIServicesMore(getToken());
      if (data === null || data === undefined) {
        addDangerAlert(i18next.t("error.fetch"), i18next.t("error.fetch_services"))
        return;
      }
      setServices(data);
    }
    getServicesOptions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const SelectSearch: React.FunctionComponent<{ selectedType: any, setSelectedType: any }> = ({ selectedType, setSelectedType }) => {
    const [isOpen, setIsOpen] = React.useState(false);
    // Auto option
    const options: JSX.Element[] = [];
    const names: string[] = []
    if (getNotDetect()) {
      options.push(<SelectOption key={"default_value"} value={"auto"}>{i18next.t("dashboard.select")}</SelectOption>)
    } else {
      options.push(<SelectOption key={"default_value"} value={"auto"}>Auto</SelectOption>)
    }
    names.push("auto")
    //Group options
    for (const [key, value] of Object.entries(groups)) {
      // Try to translate the key
      let translation = i18next.t(`api.${key}`)
      if (!i18next.exists(`api.${key}`)) {
        translation = key
      }
      names.push(translation)
      options.push(
        <SelectOption key={key} value={key}>{translation}</SelectOption>
      )
    }
    //Services options
    options.push(<Divider component="li" key={"divider"} />)
    names.push("divider")
    for (const [key, value] of Object.entries(services)) {
      if (Array.isArray(value)) {
        names.push(key + ". " + value[0])
        options.push(
          <SelectOption key={key} value={key}>{<Tooltip content={<div>{value[1]}</div>}><div>{key + ". " + value[0]}</div></Tooltip>}</SelectOption>
        )
      }
    }
    const onSelect = (event: any, selection: any) => {
      setSelectedType(selection);
      setIsOpen(false);
    };
    const customFilter = (_: any, value: string) => {
      if (!value) {
        return options
      }
      const input = new RegExp(value, 'i');
      const filteredOptions = []
      for (let i = 0; i < options.length; i++) {
        if (names[i] === "divider") {
          filteredOptions.push(options[i])
          continue
        }
        if (input.test(names[i])) {
          filteredOptions.push(options[i])
        }
      }
      return filteredOptions
    };

    return (
      <Select
        variant={SelectVariant.typeahead}
        isOpen={isOpen}
        onToggle={() => setIsOpen(!isOpen)}
        onSelect={onSelect}
        onFilter={customFilter}
        selections={selectedType}
        id="option-items"
        maxHeight="75vh"
      >
        {options}
      </Select>
    );
  };

  const SearchBar: React.FunctionComponent<{ setDetectedType: any, setIsList: any, handleSearch: any }> = ({ setDetectedType, setIsList, handleSearch }) => {
    const [value, setValue] = React.useState(searchInput.current);
    const [isDisabled, setIsDisabled] = React.useState(false);

    const regexIPv4 = /^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$/i;
    const regexIPv6 = /(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))/i;
    const regexSHA256 = /^[a-f0-9]{64}$/i;
    const regexMD5 = /^[a-f0-9]{32}$/i;
    const regexDomain = /\b((?=[a-z0-9-]{1,63}\.)(xn--)?[a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,63}\b/i;
    const disableDetection = getNotDetect();
    function testValue(val: string) {
      if (disableDetection) {
        return ""
      }
      if (regexIPv4.test(val)) {
        return "ipv4"
      } else if (regexIPv6.test(val)) {
        return "ipv6"
      } else if (regexSHA256.test(val)) {
        return "sha256"
      } else if (regexMD5.test(val)) {
        return "md5"
      } else if (regexDomain.test(val)) {
        return "domain"
      } else {
        return "other"
      }
    }
    React.useEffect(() => {
      if (value === "") {
        setDetectedType("")
        setIsList(false)
        return
      }
      const listValues = value.split(" ")
      if (listValues.length === 1) {
        setDetectedType(testValue(value))
        setIsList(false)
        return
      }
      let detected = testValue(listValues[0])
      for (const val of listValues) {
        if (val === "") {
          continue
        }
        if (detected !== testValue(val)) {
          setDetectedType("other");
          setIsList(true)
          return
        }
      }
      setDetectedType(detected);
      setIsList(true);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [value]);
    function handleSetValue(new_value: string) {
      searchInput.current = new_value;
      setValue(new_value)
    }
    function handleSearchSubmit() {
      setIsDisabled(true);
      handleSearch();
    }

    return (
      <SearchInput
        placeholder="8.8.8.8"
        value={value}
        onChange={handleSetValue}
        onSearch={handleSearchSubmit}
        isDisabled={isDisabled}
        onClear={() => handleSetValue("")}
      />
    );
  };

  const Search: React.FunctionComponent = () => {
    const [detectedType, setDetectedType] = React.useState(searchDetectedType.current)
    const [selectedType, setSelectedType] = React.useState(searchType.current)
    const [searchIsListS, setSearchIsListS] = React.useState(false)
    searchType.current = selectedType;
    searchDetectedType.current = detectedType;

    async function handleSearch() {
      if (getToken() === "") {
        addDangerAlert(i18next.t("error.token"), i18next.t("error.token_comment"))
        return
      }
      try {
        let resp: any;
        if (selectedType.toLowerCase() === "auto" && detectedType === "") {
          // Should not happen
          addDangerAlert(i18next.t("error.detect"), i18next.t("error.detect_comment"))
          return
        }
        if (selectedType === "" && detectedType === "") {
          addDangerAlert(i18next.t("error.error"), "")
          return
        }
        let searchType = detectedType
        if (selectedType.toLowerCase() !== "auto") {
          searchType = selectedType
        }
        if (searchIsListS === true) {
          const requests = searchInput.current.split(" ")
          const filteredRequests = requests.filter(n => n)
          resp = await getAPIUserList(filteredRequests, searchType, getToken());
        } else {
          resp = await getAPIUser(searchInput.current, searchType, getToken());
        }
        if (resp !== null) {
          addData(resp)
        } else {
          addDangerAlert(i18next.t("error.fetch"), "Null")
        }
      } catch (err) {
        if (err instanceof Error) {
          addDangerAlert(i18next.t("error.fetch"), err.stack as string)
        } else {
          console.log(err)
          addDangerAlert(i18next.t("error.fetch"), "")
        }
      }
      setCurrentResultID(getDataLength() - 1)
      handleToggleChange()
    }
    let typeLabel;
    if (detectedType !== "" && selectedType.toLowerCase() === "auto") {
      let localeType = i18next.t(`api.${detectedType}`)
      if (searchIsListS === true) {
        localeType = i18next.t("dashboard.list") + " " + i18next.t(`api.${detectedType}`)
      }
      typeLabel = (
        <Label color={detectedType === "other" ? "blue" : "green"} icon={<InfoCircleIcon />} id="DashboardLabel">
          {localeType}
        </Label>
      )
    } else if (searchIsListS === true) {
      typeLabel = (
        <Label color="green" icon={<InfoCircleIcon />} id="DashboardLabel">
          {i18next.t("dashboard.list")}
        </Label>
      )
    } else {
      typeLabel = ""
    }

    return (
      <>
        <ToolbarItem>
          <SearchBar setDetectedType={setDetectedType} setIsList={setSearchIsListS} handleSearch={handleSearch} />
        </ToolbarItem>
        <ToolbarItem>
          <SelectSearch selectedType={selectedType} setSelectedType={setSelectedType} />
        </ToolbarItem>
        <ToolbarItem>
          {typeLabel}
        </ToolbarItem>
      </>
    )
  }
  const TermsModal: React.FunctionComponent = () => {
    const [tokenVal, setTokenVal] = React.useState(getToken());

    const handleSetTokenVal = (value: string) => {
      setTokenVal(value)
    }
    const handleSubmit = () => {
      setToken(tokenVal)
      handleAcceptTerms()
      const loadServicesGroups = async () => {
        const APIGroups = await getAPIGroups(getToken());
        if (APIGroups === null || APIGroups === undefined) {
          return; // If getAPIGroups failed than getAPIServicesMore will also fail
        }
        setGroups(APIGroups);
        const APIServices = await getAPIServicesMore(getToken());
        if (APIServices === null || APIServices === undefined) {
          return;
        }
        setServices(APIServices);
      }
      loadServicesGroups();
    }

    return (
      <Modal
        id="always-black"
        variant={ModalVariant.medium}
        title={i18next.t("dashboard.welcome")}
        isOpen={!isTermsAccepted()}
        onClose={handleAcceptTerms}
        actions={[
          <Button key="save_token" variant="primary" onClick={handleSubmit}>
            {i18next.t("dashboard.save_close")}
          </Button>, <Switch
            id="reversed-switch"
            label={<span style={{ color: "grey" }}>CZ</span>}
            labelOff={<span style={{ color: "grey" }}>EN</span>}
            aria-label="CZ"
            isChecked={i18next.language === "cz"}
            onChange={() => {
              if (i18next.language === "en") {
                i18next.changeLanguage("cz");
                window.location.reload(); // Fix title
              } else {
                i18next.changeLanguage("en");
                window.location.reload(); // Fix title
              }
            }}
            isReversed
          />
        ]}
      >
        <Text component={TextVariants.p}>
          {i18next.t("dashboard.welcome_text1")}
        </Text>
        <Text component={TextVariants.p}>
          {i18next.t("dashboard.welcome_text2")}
        </Text>
        <Form>
          <FormGroup
            label={i18next.t("settings.token")}
          >
            <TextInput
              aria-label="welcome-token-input"
              type="text"
              value={tokenVal}
              onChange={handleSetTokenVal}
              placeholder={i18next.t("dashboard.token_enter")}
            />
          </FormGroup>
        </Form>
      </Modal>
    )
  }
  const Header = (
    <PageHeader
      logo={<Search />}
      headerTools={<HeaderTools toggleChange={handleToggleChange} />}
      showNavToggle
      isNavOpen={isNavOpen}
      onNavToggle={() => setIsNavOpen(!isNavOpen)}
    />
  );
  const Navigation = (
    <History toggleChange={handleToggleChange} />
  );

  return (
    <Page
      mainContainerId="primary-app-container"
      header={Header}
      sidebar={<PageSidebar nav={Navigation} isNavOpen={isNavOpen} id="page-sidebar" theme={getDarkTheme() ? "dark" : "light"} />}
    >
      <Alerts alerts={alerts} removeAlert={removeAlert} />
      <PageSection>
        <Result toggleChange={handleToggleChange} searchInput={searchInput} />
        <BackToTop id="BackToTopButton" title={i18next.t("dashboard.back_to_top")} />
        <TermsModal />
      </PageSection>
    </Page>
  );
};

export default DefaultLayout;
