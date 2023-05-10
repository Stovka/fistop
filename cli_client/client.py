# client.py requires Python3.9 standard library
import argparse
import getpass
import json
import urllib.request
import urllib.parse
from dataclasses import dataclass, field, asdict
from typing import Union

DEFAULT_API = "http://127.0.0.1:80"
DEFAULT_TOKEN = "xxxxxxxadmin2xxxxxx"


@dataclass
class Tokens:
    group: str = ""
    group_services: list[int] = field(default_factory=list)
    user: str = ""
    user_services: list[Union[str, int]] = field(default_factory=list)
    superuser: str = ""
    admin: str = ""


class Client:

    def __init__(self, url: str = DEFAULT_API, token: str = DEFAULT_TOKEN):
        self.base_url = self._validate_url(url)
        self.token = token
        self._api_prefix = "/api/v1/"
        self._api_url = self.urljoin(self.base_url, self._api_prefix)
        self._info_services = self.urljoin(self._api_url, "/server/info/services/")
        self._info_services2 = self.urljoin(self._api_url, "/server/info/services2/")
        self._info_groups = self.urljoin(self._api_url, "/server/info/groups/")
        self._info_tokens = self.urljoin(self._api_url, "/server/info/tokens/")
        self._info_server = self.urljoin(self._api_url, "/server/info/server/")
        self._info_version = self.urljoin(self._api_url, "/server/info/version/")
        self._server_start = self.urljoin(self._api_url, "/server/start/")
        self._server_stop = self.urljoin(self._api_url, "/server/stop/")
        self._server_restart = self.urljoin(self._api_url, "/server/restart/")
        self._server_reload_tokens = self.urljoin(self._api_url, "/server/reload_tokens/")
        self._put_tokens = self.urljoin(self._api_url, "/server/tokens/")
        self._del_tokens = self.urljoin(self._api_url, "/server/tokens/")

    @staticmethod
    def _validate_url(url: str) -> str:
        if not isinstance(url, str):
            raise Exception(f"Invalid URL: {url}")
        url = url.lower()
        if not url.startswith("http://") and not url.startswith("https://"):
            raise Exception(f"Invalid URL: {url} It has to starts with http:// or https://")
        if "localhost" in url:
            url = url.replace("localhost", "127.0.0.1")
        return url

    @staticmethod
    def urljoin(*parts: str):
        new_url = ""
        for part in parts:
            new_url = new_url.strip("/")
            new_url += "/"+part.lstrip("/")  # Not stripping right
        return new_url

    def _get_api(self, url: str) -> dict:
        req = urllib.request.Request(url, method="GET")
        req.add_header("token", self.token)
        resp = urllib.request.urlopen(req).read().decode("utf-8")
        return json.loads(resp)

    def _post_api(self, url: str, data: list) -> dict:
        req = urllib.request.Request(url, method="POST", data=json.dumps(data).encode())
        req.add_header("token", self.token)
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req).read().decode("utf-8")
        return json.loads(resp)

    def _put_api(self, url: str, data: dict) -> dict:
        req = urllib.request.Request(url, method="PUT", data=json.dumps(data).encode())
        req.add_header("token", self.token)
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req).read().decode("utf-8")
        return json.loads(resp)

    def _del_api(self, url: str, data: dict) -> dict:
        req = urllib.request.Request(url, method="DELETE", data=json.dumps(data).encode())
        req.add_header("token", self.token)
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req).read().decode("utf-8")
        return json.loads(resp)

    def get_services_info(self) -> dict:
        """Returns available services."""
        return self._get_api(self._info_services)

    def get_services_info_more(self) -> dict:
        """Returns available services with additional info."""
        return self._get_api(self._info_services2)

    def get_groups_info(self) -> dict:
        """Returns available groups."""
        return self._get_api(self._info_groups)

    def get_tokens_info(self) -> dict:
        """Returns tokens."""
        return self._get_api(self._info_tokens)

    def get_server_info(self) -> dict:
        """Returns running and static info about server."""
        return self._get_api(self._info_server)

    def get_version(self) -> dict:
        """Returns version of API."""
        return self._get_api(self._info_version)

    def get_server_start(self) -> dict:
        """Start not running services. Returns status code."""
        return self._get_api(self._server_start)

    def get_server_stop(self) -> dict:
        """Stop all running services. Returns status code."""
        return self._get_api(self._server_stop)

    def get_server_restart(self) -> dict:
        """Restart all services. Returns status code."""
        return self._get_api(self._server_restart)

    def get_server_reload_tokens(self) -> dict:
        """Reload tokens from file. Returns status code."""
        return self._get_api(self._server_reload_tokens)

    def put_tokens(self, tokens: Tokens) -> dict:
        """Add or update from tokens. Tokens must follow structure of dataclass Tokens.

        Args:
            tokens (Tokens): Tokens object with attributes that should be added or updated.

        Returns:
            (dict): Dictionary with status
        """
        return self._put_api(self._put_tokens, asdict(tokens))

    def del_tokens(self, tokens: Tokens) -> dict:
        """Delete from tokens. Tokens must follow structure of dataclass Tokens.

        Args:
            tokens (Tokens): Tokens object with attributes that should be deleted.

        Returns:
            (dict): Dictionary with status
        """
        return self._del_api(self._del_tokens, asdict(tokens))

    def get(self, service_id_group_name: Union[int, str], request: str) -> dict:
        """Get result for single request.

        Args:
            service_id_group_name (int | str): Service ID or group name that should be executed.
            request (list[str]): String request.

        Returns:
            (dict): Dictionary with result.
        """
        request_url = self.urljoin(self._api_url,
                                   urllib.parse.quote(str(service_id_group_name)),
                                   urllib.parse.quote(request))
        return self._get_api(request_url)

    def get_list(self, service_id_group_name: Union[int, str], requests: list[str]) -> dict:
        """Get results for multiple requests.

        Args:
            service_id_group_name (int | str): Service ID or group name that should be executed.
            requests (list[str]): List of string requests.

        Returns:
            (dict): Dictionary with results.
        """
        request_url = self.urljoin(self._api_url, urllib.parse.quote(str(service_id_group_name)), "/")
        return self._post_api(request_url, requests)


def main():
    parser = argparse.ArgumentParser(
        description=f"CLI client for DPv5 \nUsage:\npython client.py -r \"8.8.8.8\" -g 0\n"
                    f"python client.py -r \"8.8.8.8 8.8.4.4\" -g \"domain\"\n"
                    f"python client.py -r \"8.8.8.8,8.8.8.8\" -s \",\" -g 6 --raw\n"
                    f"python client.py -r \"1.1.1.1\" -t -a \"https://address.api\"\n"
                    f"python client.py -i services/groups/server/tokens/version\n"
                    f"python client.py -x start/stop/restart/reload_tokens\n",
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("-a", "--api", help=f"API address (default {DEFAULT_API}).", default=DEFAULT_API)
    parser.add_argument("-t", "--token", action="store_true", help="Request API token.")
    parser.add_argument("-r", "--request", help="Request or requests (eg. 8.8.8.8 or '8.8.8.8 8.8.4.4').")
    parser.add_argument("-s", "--separator", help="Separator between requests (default is white space).", default=" ")
    parser.add_argument("-g", "--group", help="Group name or service ID.", default="0")
    parser.add_argument("-i", "--info", help="Request info, options: services, services_more, "
                                             "groups, server, tokens, version")
    parser.add_argument("-x", "--exec", help="Send command, options: start, stop, restart, reload_tokens")
    parser.add_argument("--raw", action="store_true", help="Show only raw output.")
    args = vars(parser.parse_args())

    # Parse/Request token
    if args["token"] is True:
        token = getpass.getpass(prompt="Enter token: ", stream=None)
    else:
        token = DEFAULT_TOKEN
    if token == "" and args["raw"] is False:
        print("You did not provide token.")

    # Parse request/requests
    request = None
    requests = None
    if args["request"] is not None:
        requests = args["request"].split(args["separator"])
        if len(requests) == 1:
            request = requests[0]
            requests = None

    # Print parameters
    if args["raw"] is False:
        print(f"API address: {args['api']}")
        if args["info"] is not None:
            print(f"Info: {args['info']}")
        elif request is not None:
            print(f"Request: {request}")
        elif requests is not None:
            print(f"Requests: {requests}")

    # Initialize client
    client = Client(args["api"], token)

    # Function for printing results
    def print_dict(data: dict, inline: bool = False):
        if inline is True:
            print(json.dumps(data))
        else:
            print(json.dumps(data, indent=2))

    # Handle info
    if args["info"] is not None:
        info_dict = {
            "services": client.get_services_info,
            "services_more": client.get_services_info_more,
            "groups": client.get_groups_info,
            "server": client.get_server_info,
            "tokens": client.get_tokens_info,
            "version": client.get_version
        }
        if args["info"] not in info_dict.keys():
            print(f"Invalid info request. Available options are: {list(info_dict.keys())}")
            return

        print_dict(info_dict[args["info"]](), args["raw"])
        return

    # Handle exec
    if args["exec"] is not None:
        exec_dict = {
            "start": client.get_server_start,
            "stop": client.get_server_stop,
            "restart": client.get_server_restart,
            "reload_tokens": client.get_server_reload_tokens
        }
        if args["exec"] not in exec_dict.keys():
            print(f"Invalid info request. Available options are: {list(exec_dict.keys())}")
            return

        print_dict(exec_dict[args["exec"]](), args["raw"])
        return

    # Handle request/requests
    if request is not None:
        response = client.get(args["group"], request)
    elif requests is not None:
        response = client.get_list(args["group"], requests)
    else:
        print(f"You have to provide request eg.: -r 8.8.8.8 or -r '8.8.8.8 8.8.4.4' "
              f"or specify info request eg.: -i services")
        return
    print_dict(response, args["raw"])


if __name__ == "__main__":
    main()
