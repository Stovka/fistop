import { getBaseURL } from "./Helpers";

export const apiPrefix = "/api/v1/";

export interface IEndpoints {
    name: string;
    path: string;
    type: string;
    isDanger: boolean;
}

export const endpoints: IEndpoints[] = [
    {
        name: "services",
        path: urlJoin(apiPrefix, "/server/info/services/"),
        type: "GET",
        isDanger: false
    },
    {
        name: "services2",
        path: urlJoin(apiPrefix, "/server/info/services2/"),
        type: "GET",
        isDanger: false
    },
    {
        name: "groups",
        path: urlJoin(apiPrefix, "/server/info/groups/"),
        type: "GET",
        isDanger: false
    },
    {
        name: "tokens",
        path: urlJoin(apiPrefix, "/server/info/tokens/"),
        type: "GET",
        isDanger: false
    },
    {
        name: "server",
        path: urlJoin(apiPrefix, "/server/info/server/"),
        type: "GET",
        isDanger: false
    },
    {
        name: "version",
        path: urlJoin(apiPrefix, "/server/info/version/"),
        type: "GET",
        isDanger: false
    },
    {
        name: "start",
        path: urlJoin(apiPrefix, "/server/start/"),
        type: "GET",
        isDanger: true
    },
    {
        name: "stop",
        path: urlJoin(apiPrefix, "/server/stop/"),
        type: "GET",
        isDanger: true
    },
    {
        name: "restart",
        path: urlJoin(apiPrefix, "/server/restart/"),
        type: "GET",
        isDanger: true
    },
    {
        name: "reload_tokens",
        path: urlJoin(apiPrefix, "/server/reload_tokens/"),
        type: "GET",
        isDanger: true
    },
    {
        name: "put_tokens",
        path: urlJoin(apiPrefix, "/server/tokens/"),
        type: "PUT",
        isDanger: true
    },
    {
        name: "del_tokens",
        path: urlJoin(apiPrefix, "/server/tokens/"),
        type: "DEL",
        isDanger: true
    }
];

export function urlJoin(...parts: string[]) {
    const sep = "/";
    parts = parts.map((part, index) => {
        if (index) {
            part = part.replace(new RegExp('^' + sep), '');
        }
        if (index !== parts.length - 1) {
            part = part.replace(new RegExp(sep + '$'), '');
        }
        return part;
    })
    return parts.join(sep);
}

export const DefaultGetParams = (token: string): RequestInit => ({
    method: 'GET', // *GET, POST, PUT, DELETE, etc.
    mode: 'cors', // no-cors, *cors, same-origin
    cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
    credentials: 'same-origin', // include, *same-origin, omit
    headers: {
        'Content-Type': 'application/json',
        'token': token,
    },
    redirect: 'follow', // manual, *follow, error
    referrerPolicy: 'no-referrer', // no-referrer, *no-referrer-when-downgrade, origin, origin-when-cross-origin, same-origin, strict-origin, strict-origin-when-cross-origin, unsafe-url
});

export const DefaultPutParams = (token: string, requestBody: string): RequestInit => ({
    method: 'PUT', // *GET, POST, PUT, DELETE, etc.
    mode: 'cors', // no-cors, *cors, same-origin
    cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
    credentials: 'same-origin', // include, *same-origin, omit
    headers: {
        'Content-Type': 'application/json',
        'token': token,
    },
    redirect: 'follow', // manual, *follow, error
    referrerPolicy: 'no-referrer', // no-referrer, *no-referrer-when-downgrade, origin, origin-when-cross-origin, same-origin, strict-origin, strict-origin-when-cross-origin, unsafe-url
    body: requestBody, // body data type must match "Content-Type" header
});

export const DefaultPostParams = (token: string, requestBody: string): RequestInit => ({
    method: 'POST', // *GET, POST, PUT, DELETE, etc.
    mode: 'cors', // no-cors, *cors, same-origin
    cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
    credentials: 'same-origin', // include, *same-origin, omit
    headers: {
        'Content-Type': 'application/json',
        'token': token,
    },
    redirect: 'follow', // manual, *follow, error
    referrerPolicy: 'no-referrer', // no-referrer, *no-referrer-when-downgrade, origin, origin-when-cross-origin, same-origin, strict-origin, strict-origin-when-cross-origin, unsafe-url
    body: requestBody, // body data type must match "Content-Type" header
});

export const DefaultDelParams = (token: string, requestBody: string): RequestInit => ({
    method: 'DELETE', // *GET, POST, PUT, DELETE, etc.
    mode: 'cors', // no-cors, *cors, same-origin
    cache: 'no-cache', // *default, no-cache, reload, force-cache, only-if-cached
    credentials: 'same-origin', // include, *same-origin, omit
    headers: {
        'Content-Type': 'application/json',
        'token': token,
    },
    redirect: 'follow', // manual, *follow, error
    referrerPolicy: 'no-referrer', // no-referrer, *no-referrer-when-downgrade, origin, origin-when-cross-origin, same-origin, strict-origin, strict-origin-when-cross-origin, unsafe-url
    body: requestBody, // body data type must match "Content-Type" header
});

export async function fetchAPI<T>(url: string, params: RequestInit): Promise<T> {
    console.log(url)
    const response = await fetch(url, params);
    if (!response.ok) {
        throw new Error(JSON.stringify({ "FetchAPI": "Request failed", "URL": url, "status": response.statusText }));
    }
    return await (response.json() as Promise<T>);
}

export function getAPIUser(request: string, group_name: string, token: string) {
    const url = urlJoin(getBaseURL(), apiPrefix, group_name, encodeURIComponent(request))
    return fetchAPI(url, DefaultGetParams(token))
}

// This is POST under the hood 
export function getAPIUserList(requests: string[], group_name: string, token: string) {
    const url = urlJoin(getBaseURL(), apiPrefix, group_name) + "/"
    return fetchAPI(url, DefaultPostParams(token, JSON.stringify(requests)))
}

export function getAPIGroups(token: string) {
    let url = "";
    for (const endpoint of endpoints) {
        if ("groups" === endpoint.name) {
            url = getBaseURL() + endpoint.path
        }
    }
    if (url !== "") {
        return fetchAPI(url, DefaultGetParams(token))
    } else {
        return null
    }
}

export function getAPIServices(token: string) {
    let url = "";
    for (const endpoint of endpoints) {
        if ("services" === endpoint.name) {
            url = getBaseURL() + endpoint.path
        }
    }
    if (url !== "") {
        return fetchAPI(url, DefaultGetParams(token))
    } else {
        return null
    }
}

export function getAPIServicesMore(token: string) {
    let url = "";
    for (const endpoint of endpoints) {
        if ("services2" === endpoint.name) {
            url = getBaseURL() + endpoint.path
        }
    }
    if (url !== "") {
        return fetchAPI(url, DefaultGetParams(token))
    } else {
        return null
    }
}

export function getAPIAdmin(request: string, type: string, token: string) {
    let url = "";
    for (const endpoint of endpoints) {
        if (type === endpoint.name) {
            if (request !== "") {
                url = getBaseURL() + endpoint.path + request
            } else {
                url = getBaseURL() + endpoint.path
            }
        }
    }
    if (url !== "") {
        return fetchAPI(url, DefaultGetParams(token))
    } else {
        return null
    }
}

export interface IPutAdmin {
    group: string | undefined;
    group_services: string[] | number[] | undefined;
    user: string | undefined;
    user_services: string[] | number[] | undefined;
    superuser: string | undefined;
    admin: string | undefined;
}

export function putAPIAdmin(data: IPutAdmin, token: string) {
    let url = "";
    for (const endpoint of endpoints) {
        if ("put_tokens" === endpoint.name) {
            url = getBaseURL() + endpoint.path
        }
    }
    if (url !== "") {
        return fetchAPI(url, DefaultPutParams(token, JSON.stringify(data)))
    } else {
        return null
    }
}

export function delAPIAdmin(data: IPutAdmin, token: string) {
    let url = "";
    for (const endpoint of endpoints) {
        if ("del_tokens" === endpoint.name) {
            url = getBaseURL() + endpoint.path
        }
    }
    if (url !== "") {
        return fetchAPI(url, DefaultDelParams(token, JSON.stringify(data)))
    } else {
        return null
    }
}