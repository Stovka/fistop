import React from 'react';
import {
    CodeBlock,
    CodeBlockAction,
    CodeBlockCode,
    ClipboardCopyButton,
    Button,
    Tooltip
} from '@patternfly/react-core';

import { getDataByIndex, getCurrentResultID } from "../Utils/Helpers";
import SearchIcon from '@patternfly/react-icons/dist/esm/icons/search-icon';
import PlusCircleIcon from '@patternfly/react-icons/dist/esm/icons/plus-circle-icon';
import MinusCircleIcon from '@patternfly/react-icons/dist/esm/icons/minus-circle-icon';
import i18next from "../Translations/i18n";
import ReactJson from 'react-json-view'


const Result: React.FunctionComponent<{ toggleChange: any, searchInput: any }> = ({ toggleChange, searchInput }) => {
    const [isCollapsed, setIsCollapsed] = React.useState(true);
    const [copied, setCopied] = React.useState(false);

    const defaultCollapse = 3;
    const result = getDataByIndex(getCurrentResultID());
    const handleCopyClick = (event: Object, text: Object) => {
        navigator.clipboard.writeText(text.toString());
        setCopied(true);
    };
    function handleAddToSearch() {
        type ObjectKey = keyof typeof result;
        const input = result["server" as ObjectKey]["input" as ObjectKey]
        if (input !== undefined) {
            const listValues = input.toString().split(",")
            if (listValues.length === 1) {
                searchInput.current = input.toString()
            } else {
                searchInput.current = listValues.join(" ")
            }
            toggleChange()
        }
    }
    function handleExpand() {
        // Wil not work sometimes: https://github.com/mac-s-g/react-json-view/issues/166
        setIsCollapsed(false);
    }
    function handleCollapse() {
        // Wil not work sometimes: https://github.com/mac-s-g/react-json-view/issues/166
        setIsCollapsed(true);
    }
    const actions = (
        <React.Fragment>
            <CodeBlockAction >
                <Tooltip aria-live="polite" exitDelay={100} content={i18next.t("result.add")}>
                    <Button variant="control" onClick={handleAddToSearch} icon={<SearchIcon />} id="result-action-buttons"></Button>
                </Tooltip>

                <Tooltip aria-live="polite" exitDelay={100} content={i18next.t("result.collapse")}>
                    <Button variant="control" onClick={handleCollapse} icon={<MinusCircleIcon />} id="result-action-buttons"></Button>
                </Tooltip>

                <Tooltip aria-live="polite" exitDelay={100} content={i18next.t("result.expand")}>
                    <Button variant="control" onClick={handleExpand} icon={<PlusCircleIcon />} id="result-action-buttons"></Button>
                </Tooltip>

                <ClipboardCopyButton
                    id="result-action-buttons"
                    textId="code-content"
                    aria-label="Copy to clipboard"
                    onClick={e => handleCopyClick(e, JSON.stringify(result))}
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
    // Modified google theme -> remove background, change base07 depending on app theme
    const modColor = {
        base00: "rgba(0, 0, 0, 0)",
        base01: "#282a2e",
        base02: "#373b41",
        base03: "#969896",
        base04: "#b4b7b4",
        base05: "#c5c8c6",
        base06: "#e0e0e0",
        base07: "var(--text-color)",
        base08: "#CC342B",
        base09: "#F96A38",
        base0A: "#FBA922",
        base0B: "#198844",
        base0C: "#3971ED",
        base0D: "#3971ED",
        base0E: "#A36AC7",
        base0F: "#3971ED"
    }

    return (
        <React.Fragment>
            <CodeBlock actions={actions} id="result-window">
                <CodeBlockCode>
                    <ReactJson src={result}
                        displayDataTypes={false}
                        displayObjectSize={false}
                        collapseStringsAfterLength={50}
                        collapsed={(isCollapsed ? defaultCollapse : false)}
                        name={false}
                        theme={modColor} />
                </CodeBlockCode>
            </CodeBlock>
        </React.Fragment>
    );
};

export default Result;