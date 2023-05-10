import React from 'react';
import { Nav, NavItem, NavList, Button, Flex, FlexItem, Toolbar, Tooltip, Title, Popover, TextInput, ValidatedOptions, ListItem, List } from '@patternfly/react-core';
import { getDescOrder, toggleDescOrder, getData, removeData, removeDataByIndex, getCurrentResultID, setCurrentResultID, addData } from "../Utils/Helpers";
import SortNumericDownAltIcon from '@patternfly/react-icons/dist/esm/icons/sort-numeric-down-alt-icon';
import SortNumericUpAltIcon from '@patternfly/react-icons/dist/esm/icons/sort-numeric-up-alt-icon';
import TrashIcon from '@patternfly/react-icons/dist/esm/icons/trash-icon';
import SaveIcon from '@patternfly/react-icons/dist/esm/icons/save-icon';
import ImportIcon from '@patternfly/react-icons/dist/esm/icons/import-icon';
import i18next from "../Translations/i18n";

function HistoryItem(props: any) {
    
    const inputMaxLength = 25;
    const inputColLength = 22;  // Space for delete button
    const isActive = (getCurrentResultID() === props.resID)
    let inputLength = inputMaxLength
    if (getCurrentResultID() === props.resID) {
        inputLength = inputColLength
    }
    function createPreview(input: string) {
        if (input !== null && input !== undefined && input.length > inputLength) {
            return input.slice(0, inputLength) + "...";
        } else {
            return input
        }
    }
    function handleOnClickRemove() {
        props.remove()
    }
    function handleOnClickOpen() {
        // Ignore click if isActive
        if (!isActive) {
            props.setCurrent()
        }
    }
    const deleteButton = (
        <FlexItem align={{ default: "alignRight" }} alignSelf={{ default: "alignSelfCenter" }}>
            <Tooltip aria-live="polite" exitDelay={100} content={i18next.t("dashboard.delete_result")}>
                <Button variant="plain" onClick={handleOnClickRemove} icon={<TrashIcon />} id="history-delete-button" isSmall></Button>
            </Tooltip>
        </FlexItem>
    )
    // Create search input preview -> accept invalid results
    let searchPreview = "Invalid result"
    let searchFull = "Invalid result"
    let serviceName = ""
    
    if (props.result["server"] !== undefined && props.result.server["input"] !== undefined) {
        if (Array.isArray(props.result.server.input)) {
            searchPreview = createPreview(props.result.server.input.join(" "))
            searchFull = i18next.t("dashboard.input") + ": " + props.result.server.input.join(" ")
        } else if (typeof props.result.server.input === "string") {
            searchPreview = createPreview(props.result.server.input)
            searchFull = i18next.t("dashboard.input") + ": " + props.result.server.input
        }
        if (props.result.server["service_name"] !== undefined){
            serviceName = i18next.t("dashboard.service") + ": " + props.result.server.service_name
        } else if (props.result.server["service_names"] !== undefined){
            serviceName = i18next.t("dashboard.services") + ": " + props.result.server.service_names
        }
    }
    const historyTooltip = (
        <List isPlain id="history-tooltip">
            <ListItem>{serviceName}</ListItem>
            <ListItem>{searchFull}</ListItem>
        </List>  
    )
    return (
        <NavItem preventDefault itemId={props.resID} onClick={handleOnClickOpen} isActive={isActive}>
            <Flex spaceItems={{ default: "spaceItemsNone" }} id="history-item">
                <FlexItem>
                    <Tooltip content={historyTooltip} maxWidth="50vw">
                        <Title headingLevel="h6" id="history-item-header">{searchPreview}</Title>
                    </Tooltip>
                </FlexItem>
                {isActive && deleteButton}
            </Flex>
        </NavItem>
    )
}


const History: React.FunctionComponent<{ toggleChange: any }> = ({ toggleChange }) => {
    const [descOrder, setDescOrder] = React.useState(getDescOrder())
    const [jsonValue, setJsonValue] = React.useState("");
    const [jsonNotValid, setJsonNotValid] = React.useState(true);

    const data = getData()
    function toggleOrder() {
        setDescOrder(toggleDescOrder())
    }
    function handleRemoveData() {
        removeData()
        toggleChange()
    }
    function handleRemoveDataByIndex(index: number) {
        removeDataByIndex(index)
        setCurrentResultID(index - 1)  // -1 is ok
        toggleChange()
    }
    function handleSetCurrentResult(index: number) {
        setCurrentResultID(index)
        toggleChange()
    }
    function handleAddResult() {
        addData(JSON.parse(jsonValue))
        toggleChange()
    }
    function handleSetJsonValue(value: string) {
        try {
            JSON.parse(value);
            setJsonNotValid(false);
        } catch (e) {
            setJsonNotValid(true);
        }
        setJsonValue(value)
    }
    const historyItems = []
    for (let i = 0; i < data.length; i++) {
        historyItems.push(
            <HistoryItem key={i}
                resID={i}
                result={data[i]}
                isSelected={getCurrentResultID() === i ? true : false}
                currentResultID={() => getCurrentResultID}
                setCurrent={() => handleSetCurrentResult(i)}
                remove={() => handleRemoveDataByIndex(i)}
            />
        )
    }
    let sortButton;
    if (descOrder === false) {
        // Asc order
        sortButton = (
            <Tooltip aria-live="polite" exitDelay={100} content={i18next.t("dashboard.sort_asc")}>
                <Button variant="secondary" onClick={toggleOrder} icon={<SortNumericDownAltIcon />} isSmall></Button>
            </Tooltip>
        )
    } else {
        // Desc/Default order
        historyItems.reverse();
        sortButton = (
            <Tooltip aria-live="polite" exitDelay={100} content={i18next.t("dashboard.sort_desc")}>
                <Button variant="secondary" onClick={toggleOrder} icon={<SortNumericUpAltIcon />} isSmall></Button>
            </Tooltip>

        )
    }
    if (historyItems.length === 0) {
        historyItems.push(
            <div key={0}></div>
        )
    }
    let validationError = ValidatedOptions.error
    if (jsonNotValid === false) {
        validationError = ValidatedOptions.success
    }
    const jsonInput = (
        <Flex direction={{ default: "column" }}>
            <Flex>
                <Title headingLevel="h3" id="always-black">{i18next.t("dashboard.json_prompt")}</Title>
            </Flex>
            <Flex spaceItems={{ default: "spaceItemsNone" }}>
                <FlexItem>
                    <TextInput value={jsonValue}
                        type="text"
                        onChange={value => handleSetJsonValue(value)}
                        validated={validationError}
                        aria-label="input for json" />
                </FlexItem>
                <FlexItem>
                    <Button variant="control" disabled={jsonNotValid} onClick={handleAddResult} icon={<SaveIcon />}>{i18next.t("dashboard.save")}</Button>
                </FlexItem>
            </Flex>
        </Flex>
    )
    const deletePrompt = (
        <Flex direction={{ default: "column" }}>
            <FlexItem>
                <Title headingLevel="h3" id="always-black">{i18next.t("dashboard.delete_prompt")}</Title>
            </FlexItem>
            <FlexItem>
                <Tooltip aria-live="polite" exitDelay={100} content={i18next.t("dashboard.delete_all")}>
                    <Button variant="danger" isDanger onClick={handleRemoveData} title="Delete results">{i18next.t("dashboard.delete_all")}</Button>
                </Tooltip>
            </FlexItem>
        </Flex>
    )

    return (
        <>
            <Toolbar id="history-toolbar" isSticky>
                <Flex id="history-item" spaceItems={{ default: "spaceItemsXs" }}>
                    <FlexItem>
                        <Title headingLevel="h2" id="history-header">{i18next.t("dashboard.history")}</Title>
                    </FlexItem>
                    <FlexItem align={{ default: "alignRight" }}>
                        <Tooltip aria-live="polite" exitDelay={100} content={i18next.t("dashboard.delete_all")}>
                            <Popover
                                aria-label="Popover with auto-width"
                                hasAutoWidth
                                bodyContent={() => deletePrompt}
                            >
                                <Button variant="secondary" title="Delete results" icon={<TrashIcon />} id="history-toolbar-delete-button" isSmall></Button>
                            </Popover>
                        </Tooltip>
                    </FlexItem>
                    <FlexItem>
                        <Tooltip aria-live="polite" exitDelay={100} content={i18next.t("dashboard.add_result")}>
                            <Popover
                                aria-label="Popover with auto-width"
                                hasAutoWidth
                                bodyContent={() => jsonInput}
                            >
                                <Button variant="secondary" icon={<ImportIcon />} isSmall></Button>
                            </Popover>
                        </Tooltip>
                    </FlexItem>
                    <FlexItem>
                        {sortButton}
                    </FlexItem>
                </Flex>
            </Toolbar>
            <Nav style={{ minHeight: "100%" }}>
                <NavList className="pf-c-nav__subnav" id="history-nav-list">
                    {historyItems}
                </NavList>
            </Nav>
        </>
    );
};

export default History;