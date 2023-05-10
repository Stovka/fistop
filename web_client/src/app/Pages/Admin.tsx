import * as React from 'react';
import {
    CodeBlock,
    CodeBlockAction,
    CodeBlockCode,
    ClipboardCopyButton,
    Button,
    PageSection,
    AlertProps,
    FormGroup,
    TextInput,
    Tooltip,
    Flex,
    FlexItem,
    Title,
    BackToTop,
    Tabs,
    Tab,
    TabTitleText,
} from '@patternfly/react-core';

import { getToken } from "../Utils/Helpers";
import TrashIcon from '@patternfly/react-icons/dist/esm/icons/trash-icon';
import { endpoints, getAPIAdmin, putAPIAdmin, IPutAdmin, delAPIAdmin } from "../Utils/API";
import Alerts from "../Components/Alerts";
import i18next from '../Translations/i18n';

//Bug fix CustomTypeOptions t as placeholder -> return false
//https://www.i18next.com/overview/typescript#argument-of-type-defaulttfuncreturn-is-not-assignable-to-parameter-of-type-xyz
declare module 'i18next' {
    interface CustomTypeOptions {
        returnNull: false;
    }
}

const Admin: React.FunctionComponent = () => {
    const [copied, setCopied] = React.useState(false);
    const [message, setMessage] = React.useState("")
    const [putInput, setPutInput] = React.useState("");
    const [putServices, setPutServices] = React.useState("");
    const [delInput, setDelInput] = React.useState("");
    const [activeTabKey, setActiveTabKey] = React.useState<string | number>(0);
    const [alerts, setAlerts] = React.useState<{ title: string, comment: string, variant: AlertProps['variant'], key: number }[]>([]);

    const handleTabClick = (
        event: React.MouseEvent<any> | React.KeyboardEvent | MouseEvent,
        tabIndex: string | number
    ) => {
        setActiveTabKey(tabIndex);
    };
    const handlePutInputChange = (newPutInput: string) => {
        setPutInput(newPutInput);
    };
    const handlePutServicesChange = (newPutServices: string) => {
        setPutServices(newPutServices);
    };
    const handleDelInputChange = (newDelInput: string) => {
        setDelInput(newDelInput);
    }
    const clipboardCopyFunc = (event: Object, text: Object) => {
        navigator.clipboard.writeText(text.toString());
    };
    const handleCopyClick = (event: Object, text: Object) => {
        clipboardCopyFunc(event, text);
        setCopied(true);
    };
    const addAlert = (title: string, comment: string, variant: AlertProps['variant'], key: number) => {
        setAlerts(prevAlerts => [...prevAlerts, { title, comment, variant, key }]);
    };
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
    async function handleGet(name: string) {
        if (getToken() === "") {
            addDangerAlert(i18next.t("error.token"), i18next.t("error.token_comment"))
            return
        }
        try {
            let resp: any = await getAPIAdmin("", name, getToken())
            setMessage(JSON.stringify(resp, null, 2));
        } catch (err) {
            if (err instanceof Error) {
                addDangerAlert(i18next.t("error.fetch"), err.stack as string)
            } else {
                addDangerAlert(i18next.t("error.fetch"), "")
            }
        }
    }
    async function handlePut(name: string) {
        if (getToken() === "") {
            addDangerAlert(i18next.t("error.token"), i18next.t("error.token_comment"))
            return
        }
        const data: IPutAdmin = {
            group: undefined,
            group_services: undefined,
            user: undefined,
            user_services: undefined,
            superuser: undefined,
            admin: undefined
        }
        if (putInput === "") {
            return
        }
        switch (name) {
            case "put_group":
                data.group = putInput;
                data.group_services = putServices.split(",");
                break;
            case "put_user":
                data.user = putInput;
                data.user_services = putServices.split(",");
                break;
            case "put_superuser":
                data.superuser = putInput
                break;
            case "put_admin":
                data.admin = putInput
                break;
            default:
                console.log("cannot occur");
        }
        try {
            let resp: any = await putAPIAdmin(data, getToken())
            setMessage(JSON.stringify(resp, null, 2));
        } catch (err) {
            if (err instanceof Error) {
                addDangerAlert(i18next.t("error.fetch"), err.stack as string)
            } else {
                addDangerAlert(i18next.t("error.fetch"), "")
            }
        }
    }
    async function handleDel(name: string) {
        if (getToken() === "") {
            addDangerAlert(i18next.t("error.token"), i18next.t("error.token_comment"))
            return
        }
        const data: IPutAdmin = {
            group: undefined,
            group_services: undefined,
            user: undefined,
            user_services: undefined,
            superuser: undefined,
            admin: undefined
        }
        if (delInput === "") {
            return
        }
        switch (name) {
            case "del_group":
                data.group = delInput;
                break;
            case "del_user":
                data.user = delInput;
                break;
            case "del_superuser":
                data.superuser = delInput;
                break;
            case "del_admin":
                data.admin = delInput;
                break;
            default:
                console.log("cannot occur");
        }
        try {
            let resp: any = await delAPIAdmin(data, getToken())
            setMessage(JSON.stringify(resp, null, 2));
        } catch (err) {
            if (err instanceof Error) {
                addDangerAlert(i18next.t("error.fetch"), err.stack as string)
            } else {
                addDangerAlert(i18next.t("error.fetch"), "")
            }
        }
    }
    const getBtnsElements = [];
    //Default endpoints
    for (const endpoint of endpoints) {
        if (endpoint.type === "GET" && endpoint.isDanger === false) {
            getBtnsElements.push(
                <FlexItem>
                    <Button key={endpoint.name} onClick={() => handleGet(endpoint.name)} isDanger={endpoint.isDanger} variant="secondary">{i18next.t(`admin.${endpoint.name}`)}</Button>
                </FlexItem>
            )
        }
    }
    const getDangerBtnsElements = [];
    //Default endpoints
    for (const endpoint of endpoints) {
        if (endpoint.type === "GET" && endpoint.isDanger === true) {
            getDangerBtnsElements.push(
                <FlexItem>
                    <Button key={endpoint.name} onClick={() => handleGet(endpoint.name)} isDanger={endpoint.isDanger} variant="secondary">{i18next.t(`admin.${endpoint.name}`)}</Button>
                </FlexItem>
            )
        }
    }
    const copyBlock = message
    const actions = (
        <React.Fragment>
            <CodeBlockAction >
                
                <Button title="Delete output" id="admin-delete-button" variant="control" onClick={() => setMessage("")} icon={<TrashIcon />}></Button>
                <ClipboardCopyButton
                    id="result-action-buttons"
                    textId="code-content"
                    aria-label="Copy to clipboard"
                    onClick={e => handleCopyClick(e, copyBlock)}
                    exitDelay={copied ? 1500 : 100}
                    maxWidth="110px"
                    variant="control"
                    onTooltipHidden={() => setCopied(false)}
                >
                    {copied ? i18next.t("result.copy_success") : i18next.t("result.copy")}
                </ClipboardCopyButton>
            </CodeBlockAction>
        </React.Fragment>
    );
    const userAdd = (
        <div>
            <Flex>
                <FlexItem>
                    <Tooltip content={<div>{i18next.t("admin.put_group_comment")}</div>}>
                        <Button onClick={() => handlePut("put_group")} variant="secondary">{i18next.t("admin.put_group")}</Button>
                    </Tooltip>
                </FlexItem>
                <FlexItem>
                    <Tooltip content={<div>{i18next.t("admin.put_user_comment")}</div>}>
                        <Button onClick={() => handlePut("put_user")} variant="secondary">{i18next.t("admin.put_user")}</Button>
                    </Tooltip>
                </FlexItem>
                <FlexItem>
                    <Tooltip content={<div>{i18next.t("admin.put_superuser_comment")}</div>}>
                        <Button onClick={() => handlePut("put_superuser")} variant="secondary">{i18next.t("admin.put_superuser")}</Button>
                    </Tooltip>
                </FlexItem>
                <FlexItem>
                    <Tooltip content={<div>{i18next.t("admin.put_admin_comment")}</div>}>
                        <Button onClick={() => handlePut("put_admin")} variant="secondary">{i18next.t("admin.put_admin")}</Button>
                    </Tooltip>
                </FlexItem>
            </Flex>
            <FormGroup
                fieldId="horizontal-form-token"
                helperText={i18next.t("admin.token_input_comment")}
            >
                <TextInput
                    value={putInput}
                    placeholder={"1. " + i18next.t("admin.token_input")}
                    type="text"
                    id="horizontal-form-token"
                    aria-describedby="horizontal-form-token-helper"
                    name="horizontal-form-token"
                    onChange={handlePutInputChange}
                />
            </FormGroup>
            <FormGroup
                fieldId="horizontal-form-services"
                helperText={i18next.t("admin.services_list_comment")}
            >
                <TextInput
                    placeholder={"2. " + i18next.t("admin.services_list")}
                    value={putServices}
                    type="text"
                    id="horizontal-form-token"
                    aria-describedby="horizontal-form-services-helper"
                    name="horizontal-form-services"
                    onChange={handlePutServicesChange}
                />
            </FormGroup>
        </div>
    );
    const userDel = (
        <div>
            <Flex>
                <FlexItem>
                    <Tooltip content={<div>{i18next.t("admin.del_group_comment")}</div>}>
                        <Button onClick={() => handleDel("del_group")} variant="secondary" isDanger>{i18next.t("admin.del_group")}</Button>
                    </Tooltip>
                </FlexItem>
                <FlexItem>
                    <Tooltip content={<div>{i18next.t("admin.del_user_comment")}</div>}>
                        <Button onClick={() => handleDel("del_user")} variant="secondary" isDanger>{i18next.t("admin.del_user")}</Button>
                    </Tooltip>
                </FlexItem>
                <FlexItem>
                    <Tooltip content={<div>{i18next.t("admin.del_superuser_comment")}</div>}>
                        <Button onClick={() => handleDel("del_superuser")} variant="secondary" isDanger>{i18next.t("admin.del_superuser")}</Button>
                    </Tooltip>
                </FlexItem>
                <FlexItem>
                    <Tooltip content={<div>{i18next.t("admin.del_admin_comment")}</div>}>
                        <Button onClick={() => handleDel("del_admin")} variant="secondary" isDanger>{i18next.t("admin.del_admin")}</Button>
                    </Tooltip>
                </FlexItem>
            </Flex>
            <FormGroup
                fieldId="horizontal-form-del_token_input"
            >
                <TextInput
                    placeholder={"3. " + i18next.t("admin.token_input")}
                    value={delInput}
                    type="text"
                    id="horizontal-form-del_token_input"
                    aria-describedby="horizontal-form-del_token_input-helper"
                    name="horizontal-form-del_token_input"
                    onChange={handleDelInputChange}
                />
            </FormGroup>
        </div>
    );

    return (
        <PageSection>
            <Alerts alerts={alerts} removeAlert={removeAlert} />
            <div id="AdminSpacer" >
                <Tabs
                    activeKey={activeTabKey}
                    onSelect={handleTabClick}
                    role="region"
                >
                    <Tab eventKey={0} title={<TabTitleText id="admin-header">{i18next.t("admin.title_show")}</TabTitleText>}>
                        <div id="AdminSpacer" />
                        <Flex>
                            {getBtnsElements}
                        </Flex>
                    </Tab>
                    <Tab eventKey={1} title={<TabTitleText id="admin-header">{i18next.t("admin.title_put")}</TabTitleText>}>
                        <div id="AdminSpacer" />
                        {userAdd}
                    </Tab>
                    <Tab eventKey={2} title={<TabTitleText id="admin-header">{i18next.t("admin.title_del")}</TabTitleText>}>
                        <div id="AdminSpacer" />
                        {userDel}
                    </Tab>
                    <Tab eventKey={3} title={<TabTitleText id="admin-header">{i18next.t("admin.title_maintain")}</TabTitleText>}>
                        <div id="AdminSpacer" />
                        <Flex>
                            {getDangerBtnsElements}
                        </Flex>
                    </Tab>
                </Tabs>
            </div>
            <Title headingLevel="h3">{i18next.t("admin.server_response")}</Title>
            <CodeBlock actions={actions} id="result-window">
                <CodeBlockCode>
                    {message}
                </CodeBlockCode>
            </CodeBlock>
            <BackToTop id="BackToTopButton" title={i18next.t("dashboard.back_to_top")} />
        </PageSection>
    );
};

export default Admin;
