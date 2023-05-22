import sys
import logging
import logging.handlers
import datetime
import os
import urllib.request
import urllib.parse
import json

from splunklib.searchcommands import dispatch, StreamingCommand, Configuration
from splunk.clilib import cli_common as cli


DEFAULT_API = "http://10.8.17.166"
DEFAULT_TOKEN = "xxxxxsuperuserxxxxx"
DEFAULT_LOG_PATH = "."

strftime = "%Y-%m-%dT%H:%M:%S.%fZ"


class SplunkClient:

    def __init__(self, url=DEFAULT_API, token=DEFAULT_TOKEN):
        self.base_url = self._validate_url(url)
        self.token = token
        self._api_prefix = "/api/v1/"
        self._api_url = self.urljoin(self.base_url, self._api_prefix)

    @staticmethod
    def _validate_url(url):
        if not isinstance(url, str):
            raise Exception(f"Invalid URL: {url}")
        url = url.lower()
        if not url.startswith("http://") and not url.startswith("https://"):
            raise Exception(f"Invalid URL: {url} It has to starts with http:// or https://")
        if "localhost" in url:
            url = url.replace("localhost", "127.0.0.1")
        return url

    @staticmethod
    def urljoin(*parts):
        new_url = ""
        for part in parts:
            new_url = new_url.strip("/")
            new_url += "/"+part.lstrip("/")  # Not stripping right
        return new_url

    def _post_api(self, url, data):
        req = urllib.request.Request(url, method="POST", data=json.dumps(data).encode())
        req.add_header("token", self.token)
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req).read().decode("utf-8")
        return json.loads(resp)

    def get_list(self, service_id_group_name, requests):
        """Get results for multiple requests.

        Args:
            service_id_group_name (int | str): Service ID or group name that should be executed.
            requests (list[str]): List of string requests.

        Returns:
            (dict): Dictionary with results.
        """
        request_url = self.urljoin(self._api_url, urllib.parse.quote(str(service_id_group_name)), "/")
        return self._post_api(request_url, requests)

@Configuration()
class FistopCommand(StreamingCommand):

    @staticmethod
    def setup_logger(filename, level):
        try:
            with open("id.txt") as f:
                log_id = int(f.read())
        except FileNotFoundError:
            log_id = 0
        with open("id.txt", "w+") as f:
            f.write(f"{log_id+1}")

        logger = logging.getLogger('splunk.appserver.fistop.customsearch.' + filename + "." + str(log_id))
        logger.propagate = False
        logger.setLevel(level)
        file_handler = logging.handlers.RotatingFileHandler(filename, maxBytes=25000000, backupCount=5)

        formatter = logging.Formatter(f"%(asctime)s {str(log_id)}: %(message)s ")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        return logger

    def stream(self, records):
        t1 = datetime.datetime.now()
        _client = cli.getConfStanza("fistop", "default")
        if "host" in _client:
            # Load fistop.conf from default directory
            host = _client["host"]
            port = _client["port"]
            token = _client["token"]
            log_path = os.path.normpath(_client["log_path"])
        else:
            # Try to load at least default config (distributed)
            host, port = DEFAULT_API.split(":")
            token = DEFAULT_TOKEN
            log_path = os.path.normpath(DEFAULT_LOG_PATH)
        try:
            field = self.fieldnames[0]
            group = self.fieldnames[1]
        except IndexError:
            raise Exception("Invalid syntax. use: fistop field GROUP[ip, 0, ...] PARAMS[-v, -nv, -h, -t]. ")

        records_copy = [record for record in records]
        if len(records_copy) == 0:
            return
        # Params
        p_v = "-v"  # Verbose -> /opt/splunk/etc/apps/splunk-fistop-app/bin/log.fistop
        p_nv = "-nv"  # no logging -> sometimes necessary in distributed system
        p_host = "-h"  # -hhttp://10.8.8.8:80
        p_t = "-t"  # -txxxxxxxxuser12xxx
        log_level = logging.INFO
        allow_logging = True

        for par_id, par in enumerate(self.fieldnames):
            if par_id <= 1:
                continue
            if par == p_v:
                log_level = logging.DEBUG
            elif par == p_nv:
                allow_logging = False
            elif par.startswith(p_t):
                token = par[len(p_t):]
            elif par.startswith(p_host):
                try:
                    proto, addr, port = par[len(p_host):].split(":")
                    host = proto+":"+addr
                except ValueError:
                    raise Exception(f"Invalid parameter: {par} use syntax: -hhttp://10.8.8.8:80")
            else:
                raise Exception(f"Invalid parameter: {par}")
        if "host" not in _client and allow_logging is True:
            raise Exception(f"It looks like command is being run on multiple machines at the same time. This cannot"
                            f" work because logging is enabled. Try to use -nv argument to stop logging and cut any"
                            f" connections to files. Keep on mind that default configuration will be used.")
        if allow_logging:
            logger = self.setup_logger(os.path.basename(log_path), log_level)
            logger.debug(f"field:{field} group:{group} host:{host} port:{port}")
        t2 = datetime.datetime.now()
        cl = SplunkClient(f"{host}:{port}", token)
        t3 = datetime.datetime.now()
        ips = []
        ip_map = {}  # record_id -> response_id/None
        record_count = 0
        # Map records to requests
        for rec_id, rec in enumerate(records_copy):
            record_count += 1
            try:
                new_ip = rec[field]
                if new_ip not in ips and new_ip != "":
                    ips.append(new_ip)
                    ip_map[rec_id] = len(ips) - 1
                else:
                    ip_map[rec_id] = ips.index(new_ip)
            except (KeyError, ValueError):
                ip_map[rec_id] = None
        if len(ips) == 0:
            for rec in records_copy:
                yield rec
            return
        t4 = datetime.datetime.now()
        results = []
        fistop_res = cl.get_list(group, ips)
        status = {}
        if "server" in fistop_res:
            status = fistop_res["server"]
        if "state" in status and status["state"] != "OK":
            for _ in ips:
                results.append({"fistop": f"Error during request: {status['message']}"})
        else:
            if "group" in status:
                services_names = status["service_names"]
            elif "service_id" in status:
                services_names = [status["service_name"]]
            else:
                services_names = []  # Should not happen
            for ip_index, _ in enumerate(ips):
                parsed_res = {"fistop": {}}
                for srv_name in services_names:
                    parsed_res["fistop"][srv_name] = fistop_res[srv_name][ip_index]["output"]
                results.append(parsed_res)

        t5 = datetime.datetime.now()
        # Map responses to records
        for rec_id, rec in enumerate(records_copy):
            if ip_map[rec_id] is None:
                yield rec
                continue
            for f_field, f_val in (results[ip_map[rec_id]]).items():
                rec[f_field] = f_val
            yield rec
        t6 = datetime.datetime.now()
        if record_count > 0:
            # Speed is total speed, f_speed is fistop speed
            speed = record_count / ((datetime.datetime.now() - t1).total_seconds())
            f_speed = len(ips) / ((datetime.datetime.now() - t1).total_seconds())
        else:
            speed = 0.0
            f_speed = 0.0

        if allow_logging:
            logger.debug(
                f"field:{field} group:{group} count={record_count}({len(ips)}), "
                f"time={(datetime.datetime.now() - t1).total_seconds():.2},"
                f" speed={speed:.2f}r/s({f_speed:.2f}r/s) -> "
                f"t1:{(t2 - t1).total_seconds():.2} t2:{(t3 - t2).total_seconds():.2} "
                f"t3:{(t4 - t3).total_seconds():.2} t4:{(t5 - t4).total_seconds():.2} "
                f"t5:{(t6 - t5).total_seconds():.2}")
            if log_level > 10:  # > DEBUG
                logger.info(
                    f"field:{field} group:{group} count={record_count}({len(ips)}), "
                    f"time={(datetime.datetime.now() - t1).total_seconds():.2}, "
                    f"speed={speed:.2f}r/s({f_speed:.2f}r/s)")
        return


if __name__ == "__main__":
    dispatch(FistopCommand, sys.argv, sys.stdin, sys.stdout, __name__)
