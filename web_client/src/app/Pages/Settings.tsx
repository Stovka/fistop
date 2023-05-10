import * as React from 'react';
import {
    PageSection, Form,
    FormGroup,
    TextInput,
    Tooltip,
    Checkbox,
    ActionGroup,
    Button,
    Flex,
    FlexItem,
    Title,
    Popover,
} from '@patternfly/react-core';

import { getBaseURL, getToken, setBaseURL, setToken, setTokenPersistent, deleteToken, isTokenPersistent, wipeMemory, wipeSettings, getNotDetect, toggleNotDetect } from "../Utils/Helpers";
import { Link } from "react-router-dom";
import i18next from '../Translations/i18n';
import { getAPIAdmin } from '../Utils/API';

const Settings: React.FunctionComponent = () => {
    const [token, setTokenS] = React.useState(getToken());
    const [baseURL, setBaseURLS] = React.useState(getBaseURL());
    const [checkToken, setCheckToken] = React.useState<boolean>(isTokenPersistent());
    const [checkNotDetect, setCheckNotDetect] = React.useState<boolean>(getNotDetect());
    const [apiVersion, setApiVersion] = React.useState<string>("");

    const handleCheckTokenChange = (checked: boolean, event: React.FormEvent<HTMLInputElement>) => {
        setCheckToken(checked);
    };
    const handleCheckNotDetect = (checked: boolean, event: React.FormEvent<HTMLInputElement>) => {
        setCheckNotDetect(checked);
    };
    const handleTokenChange = (token: string) => {
        setTokenS(token);
    };
    const handleBaseURLChange = (baseURL: string) => {
        setBaseURLS(baseURL);
    };
    // Get API version once
    React.useEffect(() => {
        const getGroupsOptions = async () => {
            const data = await getAPIAdmin("", "version", getToken());
            if (data === null || data === undefined) {
                setApiVersion("");
                return;
            }
            type ObjectKey = keyof typeof data;
            const version = data["version" as ObjectKey]
            if (version !== undefined) {
                setApiVersion(version);
                return
            }
            const message = data["server" as ObjectKey]
            if (message !== undefined) {
                setApiVersion(message);
                return
            }
            console.log("Invalid API response for get version: " + JSON.stringify(data))
        }
        getGroupsOptions();
    }, []);
    function handleSubmit() {
        if (token === "") {
            deleteToken()
            setTokenS(getToken())
        } else if (checkToken === true) {
            deleteToken()
            setTokenPersistent(token)
        } else {
            deleteToken()
            setToken(token)
        }
        if (baseURL === "") {
            setBaseURLS(setBaseURL(""));
        } else {
            setBaseURL(baseURL)
        }
        if (getNotDetect() !== checkNotDetect) {
            toggleNotDetect()
        }
    };
    const deletePrompt = (
        <Flex direction={{ default: "column" }}>
            <FlexItem>
                <Title headingLevel="h3" id="always-black">{i18next.t("settings.wipe_prompt")}</Title>
            </FlexItem>
            <FlexItem>
                <Tooltip content={<div>{i18next.t("settings.wipe_comment")}</div>}>
                    <Button variant="danger" isDanger onClick={wipeMemory} component={(props: any) => <Link {...props} to="/" />}>{i18next.t("settings.wipe")}</Button>
                </Tooltip>
            </FlexItem>
        </Flex>
    )
    const restorePrompt = (
        <Flex direction={{ default: "column" }}>
            <FlexItem>
                <Title headingLevel="h3" id="always-black">{i18next.t("settings.default_settings_prompt")}</Title>
            </FlexItem>
            <FlexItem>
                <Tooltip content={<div>{i18next.t("settings.default_settings_comment")}</div>}>
                    <Button variant="danger" isDanger onClick={wipeSettings} component={(props: any) => <Link {...props} to="/" />}>{i18next.t("settings.default_settings")}</Button>
                </Tooltip>
            </FlexItem>
        </Flex>
    )

    return (
        <PageSection>
            <Form isHorizontal>
                <FormGroup
                    label={i18next.t("settings.token")}
                    fieldId="horizontal-form-token"
                    helperText={i18next.t("settings.token_comment")}
                >
                    <TextInput
                        value={token}
                        type="text"
                        id="horizontal-form-token"
                        aria-describedby="horizontal-form-token-helper"
                        name="horizontal-form-token"
                        placeholder={i18next.t("settings.token_placeholder")}
                        onChange={handleTokenChange}
                    />
                </FormGroup>
                <FormGroup
                    label={i18next.t("settings.persistent")}
                    isStack
                    fieldId="horizontal-form-checkbox-group"
                    hasNoPaddingTop
                    role="group"
                    helperText={i18next.t("settings.persistent_comment")}
                >
                    <Checkbox label={i18next.t("settings.persistent_label")}
                        id="alt-form-checkbox-1"
                        name="alt-form-checkbox-1"
                        isChecked={checkToken}
                        onChange={handleCheckTokenChange} />
                </FormGroup>
                <FormGroup
                    label={i18next.t("settings.base_url")}
                    fieldId="horizontal-form-baseUrl"
                    helperText={i18next.t("settings.base_url_comment")}>
                    <TextInput
                        value={baseURL}
                        type="text"
                        id="horizontal-form-baseUrl"
                        name="horizontal-form-baseUrl"
                        onChange={handleBaseURLChange}
                    />
                </FormGroup>
                <FormGroup
                    label={i18next.t("settings.not_detect")}
                    isStack
                    fieldId="horizontal-form-checkbox-group"
                    hasNoPaddingTop
                    role="group"
                    helperText={i18next.t("settings.not_detect_comment")}
                >
                    <Checkbox label={i18next.t("settings.not_detect_label")}
                        id="alt-form-checkbox-2"
                        name="alt-form-checkbox-2"
                        isChecked={checkNotDetect}
                        onChange={handleCheckNotDetect} />
                </FormGroup>
                <FormGroup
                    label={i18next.t("settings.api_version")}
                    fieldId="horizontal-form-api_ver"
                    helperText={i18next.t("settings.api_version_comment")}>
                    <TextInput
                        value={apiVersion}
                        isDisabled={true}
                        type="text"
                        id="horizontal-form-api_ver"
                        name="horizontal-form-api_ver"
                    />
                </FormGroup>
                <ActionGroup>
                    <Button variant="primary" onClick={handleSubmit} component={(props: any) => <Link {...props} to="/" />}>{i18next.t("settings.save")}</Button>
                    <Tooltip aria-live="polite" exitDelay={100} content={i18next.t("settings.default_settings_comment")}>
                        <Popover hasAutoWidth bodyContent={() => restorePrompt}>
                            <Button variant="danger" title="default settings">{i18next.t("settings.default_settings")}</Button>
                        </Popover>
                    </Tooltip>
                    <Tooltip aria-live="polite" exitDelay={100} content={i18next.t("settings.wipe_comment")}>
                        <Popover hasAutoWidth bodyContent={() => deletePrompt}>
                            <Button variant="danger" title="Delete results">{i18next.t("settings.wipe")}</Button>
                        </Popover>
                    </Tooltip>
                </ActionGroup>
            </Form>
        </PageSection>
    );
};

export default Settings;
