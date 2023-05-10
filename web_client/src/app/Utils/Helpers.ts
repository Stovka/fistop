import * as React from 'react';
import { useLocation } from 'react-router-dom';

export const localNames = {
    currentResult: "current",
    ascOrder: "ascOrder",
    notDetect: "notDetect",
    settings: "settings",
    darkTheme: "darkTheme",
    baseURL: "baseURL",
    token: "token",
    terms: "termsAccepted"
}

export const UseDocumentTitle = (title: string) => {
    React.useEffect(() => {
        const originalTitle = document.title;
        document.title = title;
        return () => {
            document.title = originalTitle;
        };
    }, [title]);
};

export const GetPreviousLocation = (): string => {
    const location = useLocation();
    const locationState = location.state === undefined || location.state === null ? undefined : (location.state as { from: Location });
    const locationFrom = locationState === undefined || location.state === null ? '/' : locationState.from.pathname;
    return locationFrom;
};

export const getData = () => {
    const data = [];
    // Retrieve the ordered keys of the results from localStorage
    let keys = Object.keys(localStorage).filter(key => !isNaN(Number(key))).sort((a, b) => Number(a) - Number(b));
    // Fix gaps if exists (User deleted result in localStorage)
    const modified = fixGaps()
    if (modified) {
        console.log("Fixing gap in result ordering")
        // Update keys
        keys = Object.keys(localStorage).filter(key => !isNaN(Number(key))).sort((a, b) => Number(a) - Number(b));
    }
    // Parse results
    for (const key of keys) {
        try {
            // Trust in value -> potential injection point
            // Value should be validated so that it is valid result
            const localValue = localStorage.getItem(key)
            if (localValue !== null) {
                const value = JSON.parse(localValue);
                data.push(value);
            } else {
                localStorage.removeItem(key);
            }
        } catch (e) {
            // Remove not valid result
            console.log("Error in key:", key, "removing this item. Error:");
            console.log(e);
            localStorage.removeItem(key);
        }
    }
    return data;
}

export const addData = (newData: Object): Number => {
    // Retrieve the ordered keys of the results from localStorage
    const keys = Object.keys(localStorage).filter(key => !isNaN(Number(key))).sort((a, b) => Number(a) - Number(b));
    // Create index
    const newIndex = Number(keys.slice(-1)) + 1;
    //Save result
    localStorage.setItem(newIndex.toString(), JSON.stringify(newData))
    return newIndex
}

export const getDataLength = (): number => {
    return Object.keys(localStorage).filter(key => !isNaN(Number(key))).length;
}

export const getDataByIndex = (index: Number): Object => {
    // Assuming that indexes did not change
    // Returns {} if result does not exist
    const localItem = localStorage.getItem(index.toString())
    if (localItem == null) {
        return {}
    }
    return JSON.parse(localItem)
}

export const removeDataByIndex = (index: Number) => {
    // Assuming that indexes did not change and index exists
    localStorage.removeItem(index.toString())
    // Fix gaps after removal
    fixGaps()
}

export const removeData = () => {
    const keys = Object.keys(localStorage).filter(key => !isNaN(Number(key)));
    for (const key of keys) {
        localStorage.removeItem(key);
    }
}

export const wipeMemory = () => {
    // Delete everything in localStorage and sessionStorage
    const keys = Object.keys(localStorage);
    for (const key of keys) {
        localStorage.removeItem(key);
    }
    // Token could be in sessionStorage
    sessionStorage.removeItem(localNames.token);
}

export const wipeSettings = () => {
    // Delete everything in localStorage and sessionStorage except search results
    const keys = Object.keys(localStorage);
    for (const key of keys) {
        if (isNaN(Number(key))){
            localStorage.removeItem(key);
        }
    }
    // Token could be in sessionStorage
    sessionStorage.removeItem(localNames.token);
}

const fixGaps = () => {
    // Get ordered result keys
    const keys = Object.keys(localStorage).filter((key: string) => !isNaN(Number(key))).sort((a, b) => Number(a) - Number(b))
    let modified = false
    let previousKey = -1;
    const currentResultID = getCurrentResultID()
    for (const key of keys) {
        if (Number(key) !== previousKey + 1) {
            // Fix gap
            let localItem = localStorage.getItem(key.toString())
            if (localItem == null) {
                localItem = ""
            }
            localStorage.setItem((previousKey + 1).toString(), localItem);
            localStorage.removeItem(key.toString())
            // Fix currentResultID if affected
            if (Number(key) === currentResultID) {
                console.log("curr result affected new resID:", (previousKey + 1), "old resID:", key)
                setCurrentResultID(previousKey + 1)
            }
            modified = true
        }
        previousKey = previousKey + 1
    }
    return modified
}

export const getCurrentResultID = (): number => {
    const localCurrResult = localStorage.getItem(localNames.currentResult)
    if (!isNaN(Number(localCurrResult)) && Number(localCurrResult) > 0) {
        return Number(localCurrResult)
    }
    return 0
}

export const setCurrentResultID = (newCurrResult: number): number => {
    if (!isNaN(Number(newCurrResult)) && Number(newCurrResult) > 0) {
        localStorage.setItem(localNames.currentResult, newCurrResult.toString())
        return newCurrResult
    } else {
        localStorage.setItem(localNames.currentResult, newCurrResult.toString())
        return 0
    }
}

export const getDescOrder = (): boolean => {
    // If localNames.ascOrder is present and = true -> asc (false) else desc (true)
    const localAscOrder = localStorage.getItem(localNames.ascOrder)
    if (localAscOrder !== null && (localAscOrder === true.toString())) {
        return false
    } else {
        return true
    }
}

export const toggleDescOrder = (): boolean => {
    if (getDescOrder() === true) {
        // Desc order -> switch to asc
        localStorage.setItem(localNames.ascOrder, true.toString())
        return false
    } else {
        localStorage.removeItem(localNames.ascOrder)
        return true
    }
}

export const getNotDetect = (): boolean => {
    const localNotDetect = localStorage.getItem(localNames.notDetect)
    if (localNotDetect !== null && (localNotDetect === true.toString())) {
        return true
    } else {
        return false
    }
}

export const toggleNotDetect = (): boolean => {
    if (getNotDetect() === true) {
        localStorage.removeItem(localNames.notDetect)
        return false
    } else {
        localStorage.setItem(localNames.notDetect, true.toString())
        return true
    }
}

export const getBaseURL = (): string => {
    const localBaseURL = localStorage.getItem(localNames.baseURL)
    if (localBaseURL !== null && localBaseURL !== "") {
        return localBaseURL
    } else {
        return window.location.origin;
    }
}

export const setBaseURL = (newBaseURL: string): string => {
    localStorage.setItem(localNames.baseURL, newBaseURL)
    return getBaseURL()
}

export const getToken = (): string => {
    const localToken = localStorage.getItem(localNames.token);
    const sessionToken = sessionStorage.getItem(localNames.token)
    //Local token has priority
    if (localToken !== null && localToken !== "") {
        return localToken
    } else if (sessionToken !== null && sessionToken !== "") {
        return sessionToken
    } else {
        return ""
    }
}

export const isTokenPersistent = (): boolean => {
    const localToken = localStorage.getItem(localNames.token);
    if (localToken !== null && localToken !== "") {
        return true
    } else {
        return false
    }
}

export const setToken = (newToken: string): string => {
    sessionStorage.setItem(localNames.token, newToken)
    return newToken
}

export const setTokenPersistent = (newToken: string): string => {
    localStorage.setItem(localNames.token, newToken)
    return newToken
}

export const deleteToken = (): boolean => {
    localStorage.removeItem(localNames.token)
    sessionStorage.removeItem(localNames.token)
    return true
}

export const getDarkTheme = () => {
    const darkTheme = localStorage.getItem(localNames.darkTheme);
    if (darkTheme !== null && (darkTheme === true.toString())) {
        document.documentElement.setAttribute("data-theme", "dark");
        return true
    } else {
        document.documentElement.setAttribute("data-theme", "light");
        return false
    }
}

export const toggleTheme = () => {
    if (getDarkTheme() === true) {
        //Switch to light
        localStorage.removeItem(localNames.darkTheme)
        document.documentElement.setAttribute("data-theme", "light");
        return false
    } else {
        //Switch to dark
        localStorage.setItem(localNames.darkTheme, true.toString())
        document.documentElement.setAttribute("data-theme", "dark");
        return true
    }
}

export const isTermsAccepted = (): boolean => {
    const localTerms = localStorage.getItem(localNames.terms);
    if (localTerms === true.toString()) {
        return true
    } else {
        return false
    }
}

export const acceptTerms = (): boolean => {
    localStorage.setItem(localNames.terms, true.toString());
    return true
}
