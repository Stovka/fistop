import socket
import hashlib
import urllib.request
import urllib.parse
import ipaddress
import json
import configparser

from utility import Service

API_KEYS_LOCATION = "settings/tokens.ini"
"""
Here you can define services. Service is defined as a class that inherits f-rom abstract Service class from utility. 
Name of the class is irrelevant be it must unique and not equal to Service. Services must define at least: unique string 
name and implement run() method. Any service configuration should happen in initializer. Optionally you can overwrite 
start() and shutdown() methods. These methods are called when service is started/stopped. There will be one object 
created per service. Service run() method can be parallelize by specifying number of threads/processes on which method 
should be called. Keep on mind that any class variables are shared among the threads/processes. Further more if you use 
processes than you will not have access to standard class variables you have to use multiprocessing values/arrays see 
example class CustomService3. You can define services in multiple files. Every file containing service definition must 
be listed in config.ini like so: services = services additional_services

Service variables with respective data type and default value: 
name: str                   # Required: unique string for every service
description: str = ""       # Optional: service description
service_id: int             # Optional: service ID
threads: int = 1            # Optional: number of threads on which service will be run
processes: int = 0          # Optional: number of processes on which service will be run
timeout: int = 0            # Optional: seconds after which thread/process will be restarted if stuck in run method
max_timeouts: int = 3       # Optional: how many times service can be restarted due to timeout
groups: list[str] = []      # Optional: List of strings representing service groups
ignore: bool = False        # Optional: Boolean if set to True than service will be ignored (not loaded)

timeout - If it is set to zero (be default) then thread/process will never be interrupted. Use it only if you are sure
    that service cannot get stuck. Service will be slightly faster when it is set to 0. When thread/process is not
    responding for approximately timeout seconds than it is restarted.

max_timeouts - When any service thread/process is restarted due to timeout more than max_timeouts times then the
    whole service (all threads/processes) is stopped. If it is set to zero then there is no limit (threads/processes can 
    be restarted unlimited number of times). If timeout is set to 0 then max_timeouts will never be used.

groups - List of strings identifying groups of which the service is a member. Calling group will execute service.

service_id - Automatically assigned number for every service. You can manually overwrite this. It must be unique
    positive integer not greater than number of services.

Service methods:
run(request)        Required method. Accepts string and returns dictionary.
run_list(requests)  Optional method. Accepts list of strings and returns list of dictionaries.
start()             Optional method. Accepts and returns nothing. It is called when service is initialized.
shutdown()          Optional method. Accepts and returns nothing. It is called on shutdown.


example services:
- Simplest services. Returns its name.
class CustomService1(Service):
    name = "custom_service1"

    def run(self, request: str) -> dict:
        return {request: self.name}

- Service calling API
- Service will have service ID 0. 5 threads will be created.
- Service will be restarted (up to 2 times) if fetch will take longer than 2 seconds.
- Service will be member of group "ip".
    - also "all" group if disable_all_groups is false in config.ini
    - also "custom_service2" group if disable_name_groups is false in config.ini
import urllib.request
import json
class CustomService2(Service):
    def __init__(self):
        self.name = "custom_service2"
        self.description = "Sends query to some website"
        self.service_id = 0
        self.threads = 5
        self.processes = 0
        self.timeout = 2
        self.max_timeouts = 2
        self.groups = ["ip"]

        self._token = ""

    def run(self, request: str) -> dict:
        url = f"https://ipinfo.io/{request}"
        if self._token:
            url += f"?token={self._token}"

        req = urllib.request.urlopen(url)
        return json.loads(req.read().decode("utf-8"))

- Service using processes
- Variables that accessible inside run method must be multiprocessing variables
- Service is also utilizing start and shutdown methods which are called upon start/shutdown
import multiprocessing as mp
import ctypes
class CustomService3(Service):
    def __init__(self):
        self.name = "custom_service3"
        self.threads = 0
        self.processes = 5

        self._token = mp.Array(ctypes.c_wchar, "string_token")
        self._number = mp.Value(ctypes.c_int, 10)

    def run(self, request: str) -> dict:
        return {request: f"token: {self._token[:]}, number: {self._number.value}"}

    def start(self) -> None:
        print("Starting CustomService3")

    def shutdown(self) -> None:
        print("Shutting down CustomService3")

"""


class GeoIP(Service):

    def __init__(self):
        self.name = "GeoIP"
        self.description = "GeoIP by ipinfo: https://ipinfo.io/"
        self.service_id = 0
        self.threads = 5
        self.processes = 0
        self.timeout = 1
        self.max_timeouts = 2
        self.groups = ["ipv4", "ipv6"]
        self._token = ""

    def run(self, request: str) -> dict:
        try:
            valid_ip = ipaddress.ip_address(request)
        except ValueError:
            return {"GeoIP": f"Request: {request} is not a valid IP address"}
        url = f"https://ipinfo.io/{valid_ip}"
        if self._token:
            url += f"?token={self._token}"

        req = urllib.request.urlopen(url)
        return json.loads(req.read().decode("utf-8"))

    def start(self) -> None:
        # Load api key from tokens.ini
        config_parser = configparser.ConfigParser(allow_no_value=True)
        config_parser.read(API_KEYS_LOCATION)
        try:
            self._token = config_parser["SERVICES"]["ipinfo_api_key"]
        except KeyError:
            self._token = ""


class DNSInfo(Service):

    def __init__(self):
        self.name = "DNS info"
        self.description = "DNS info by host.io: https://host.io/"
        self.service_id = 1
        self.threads = 5
        self.processes = 0
        self.timeout = 2
        self.max_timeouts = 2
        self.groups = ["domain"]
        self._token = ""

    def run(self, request: str) -> dict:
        if self._token == "":
            return {"DNS info": "You have to add your API key in settings/tokens.ini. "
                                "You can get is for free after registration here: https://host.io/signup"}
        request_enc = request
        if any(ord(c) > 128 for c in request):
            try:
                request_enc = request.encode("idna").decode()  # Punycode
            except UnicodeDecodeError:
                request_enc = urllib.parse.quote(request)

        url = f"https://host.io/api/dns/{request_enc}?token={self._token}"
        req = urllib.request.urlopen(url)
        return json.loads(req.read().decode("utf-8"))

    def start(self) -> None:
        # Load api key from tokens.ini
        config_parser = configparser.ConfigParser(allow_no_value=True)
        config_parser.read(API_KEYS_LOCATION)
        try:
            self._token = config_parser["SERVICES"]["hostio_api_key"]
        except KeyError:
            self._token = ""


class ResolveDomain(Service):

    def __init__(self):
        self.name = "DNS resolve"
        self.description = "Actively tries to resolve provided domain via server's DNS resolver."
        self.threads = 5

    def run(self, request: str) -> dict:
        return {request: list(map(lambda x: x[4][0], socket.getaddrinfo(request, 22, type=socket.SOCK_STREAM)))}


class PassiveDNS(Service):

    def __init__(self):
        self.name = "Passive DNS"
        self.description = "Mnemonic Passive DNS service: https://api.mnemonic.no/pdns/v3/"
        self.threads = 5
        self.processes = 0
        self.timeout = 2
        self.max_timeouts = 2

    def run(self, request: str) -> dict:
        request_enc = request
        if any(ord(c) > 128 for c in request):
            try:
                request_enc = request.encode("idna").decode()  # Punycode
            except UnicodeDecodeError:
                request_enc = urllib.parse.quote(request)

        url = f"https://api.mnemonic.no/pdns/v3/{request_enc}"
        req = urllib.request.urlopen(url)
        return json.loads(req.read().decode("utf-8"))


class Shodan(Service):

    def __init__(self):
        self.name = "Shodan IP"
        self.description = "Queries Shodan IP API: https://api.shodan.io/shodan/host/"
        self.threads = 2
        self.processes = 0
        self._token = ""

    def run(self, request: str) -> dict:
        if self._token == "":
            return {"Shodan IP": "You have to add your API key in settings/tokens.ini"}
        try:
            valid_ip = ipaddress.ip_address(request)
        except ValueError:
            return {"Shodan IP": f"Request: {request} is not a valid IP address"}
        url = f"https://api.shodan.io/shodan/host/{valid_ip}?key={self._token}"
        req = urllib.request.urlopen(url)
        return json.loads(req.read().decode("utf-8"))

    def start(self) -> None:
        # Load api key from tokens.ini
        config_parser = configparser.ConfigParser(allow_no_value=True)
        config_parser.read(API_KEYS_LOCATION)
        try:
            self._token = config_parser["SERVICES"]["shodan_api_key"]
        except KeyError:
            self._token = ""


class ShodanMin(Service):

    def __init__(self):
        self.name = "Shodan IP Minify"
        self.description = "Queries Shodan IP API minify version: https://api.shodan.io/shodan/host/"
        self.threads = 2
        self.processes = 0
        self._token = ""

    def run(self, request: str) -> dict:
        if self._token == "":
            return {"Shodan IP Minify": "You have to add your API key in settings/tokens.ini"}
        try:
            valid_ip = ipaddress.ip_address(request)
        except ValueError:
            return {"Shodan IP Minify": f"Request: {request} is not a valid IP address"}
        url = f"https://api.shodan.io/shodan/host/{valid_ip}?key={self._token}&?minify=True"
        req = urllib.request.urlopen(url)
        return json.loads(req.read().decode("utf-8"))

    def start(self) -> None:
        # Load api key from tokens.ini
        config_parser = configparser.ConfigParser(allow_no_value=True)
        config_parser.read(API_KEYS_LOCATION)
        try:
            self._token = config_parser["SERVICES"]["shodan_api_key"]
        except KeyError:
            self._token = ""


class VirusTotalIP(Service):

    def __init__(self):
        self.name = "VirusTotal IP"
        self.description = "Sends Query to VirusTotal IP API: https://www.virustotal.com/api/v3/ip_addresses/"
        self.threads = 2
        self.processes = 0
        self._token = ""

    def run(self, request: str) -> dict:
        if self._token == "":
            return {"VirusTotal IP": "You have to add your API key in settings/tokens.ini"}
        try:
            valid_ip = ipaddress.ip_address(request)
        except ValueError:
            return {"VirusTotal IP": f"Request: {request} is not a valid IP address"}
        req = urllib.request.Request(f"https://www.virustotal.com/api/v3/ip_addresses/{valid_ip}")
        req.add_header("x-apikey", self._token)
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read().decode("utf-8"))

    def start(self) -> None:
        # Load api key from tokens.ini
        config_parser = configparser.ConfigParser(allow_no_value=True)
        config_parser.read(API_KEYS_LOCATION)
        try:
            self._token = config_parser["SERVICES"]["virustotal_api_key"]
        except KeyError:
            self._token = ""


class VirusTotalHash(Service):

    def __init__(self):
        self.name = "VirusTotal Hash"
        self.description = "Sends Query to VirusTotal hash API: https://www.virustotal.com/api/v3/files/"
        self.threads = 2
        self.processes = 0
        self.groups = ["sha256", "md5"]
        self._token = ""

    def run(self, request: str) -> dict:
        if self._token == "":
            return {"VirusTotal Hash": "You have to add your API key in settings/tokens.ini"}
        if not request.isalnum() or len(request) not in [32, 40, 56]:
            return {"VirusTotal IP": f"Request: {request} is not a valid SHA-256, SHA-1 or MD5 hash"}
        req = urllib.request.Request(f"https://www.virustotal.com/api/v3/files/{request}")
        req.add_header("x-apikey", self._token)
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read().decode("utf-8"))

    def start(self) -> None:
        # Load api key from tokens.ini
        config_parser = configparser.ConfigParser(allow_no_value=True)
        config_parser.read(API_KEYS_LOCATION)
        try:
            self._token = config_parser["SERVICES"]["virustotal_api_key"]
        except KeyError:
            self._token = ""


class VirusTotalDomain(Service):

    def __init__(self):
        self.name = "VirusTotal Domain"
        self.description = "Sends Query to VirusTotal Domain API: https://www.virustotal.com/api/v3/domains/"
        self.threads = 2
        self.processes = 0
        self._token = ""

    def run(self, request: str) -> dict:
        if self._token == "":
            return {"VirusTotal Domain": "You have to add your API key in settings/tokens.ini"}
        req = urllib.request.Request(f"https://www.virustotal.com/api/v3/domains/{urllib.parse.quote(request)}")
        req.add_header("x-apikey", self._token)
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read().decode("utf-8"))

    def start(self) -> None:
        # Load api key from tokens.ini
        config_parser = configparser.ConfigParser(allow_no_value=True)
        config_parser.read(API_KEYS_LOCATION)
        try:
            self._token = config_parser["SERVICES"]["virustotal_api_key"]
        except KeyError:
            self._token = ""


class VirusTotalURL(Service):

    def __init__(self):
        self.name = "VirusTotal URL"
        self.description = "Sends Query to VirusTotal URL API: https://www.virustotal.com/api/v3/urls/"
        self.threads = 2
        self.processes = 0
        self._token = ""

    def run(self, request: str) -> dict:
        if self._token == "":
            return {"VirusTotal URL": "You have to add your API key in settings/tokens.ini"}
        req = urllib.request.Request(f"https://www.virustotal.com/api/v3/urls/{urllib.parse.quote(request)}")
        req.add_header("x-apikey", self._token)
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read().decode("utf-8"))

    def start(self) -> None:
        # Load api key from tokens.ini
        config_parser = configparser.ConfigParser(allow_no_value=True)
        config_parser.read(API_KEYS_LOCATION)
        try:
            self._token = config_parser["SERVICES"]["virustotal_api_key"]
        except KeyError:
            self._token = ""


class DoHash(Service):

    def __init__(self):
        self.name = "Calculate Hash"
        self.description = "Calculates hashes of input."

    def run(self, request: str) -> dict:
        return {"your request": request,
                "MD5": hashlib.md5(bytes(request, encoding="utf-8")).hexdigest(),
                "SHA1": hashlib.sha1(bytes(request, encoding="utf-8")).hexdigest(),
                "SHA2-224": hashlib.sha224(bytes(request, encoding="utf-8")).hexdigest(),
                "SHA2-256": hashlib.sha256(bytes(request, encoding="utf-8")).hexdigest(),
                "SHA2-384": hashlib.sha384(bytes(request, encoding="utf-8")).hexdigest(),
                "SHA2-512": hashlib.sha512(bytes(request, encoding="utf-8")).hexdigest(),
                "SHA3-224": hashlib.sha3_224(bytes(request, encoding="utf-8")).hexdigest(),
                "SHA3-256": hashlib.sha3_256(bytes(request, encoding="utf-8")).hexdigest(),
                "SHA3-384": hashlib.sha3_384(bytes(request, encoding="utf-8")).hexdigest(),
                "SHA3-512": hashlib.sha3_512(bytes(request, encoding="utf-8")).hexdigest(),
                "blake2b": hashlib.blake2b(bytes(request, encoding="utf-8")).hexdigest(),
                "blake2s": hashlib.blake2s(bytes(request, encoding="utf-8")).hexdigest()}


class PunnyCodes(Service):

    def __init__(self):
        self.name = "Punycode"
        self.description = "Decode/Encode provided string with " \
                           "Internationalized Domain Names in Applications (IDNA)/Punycode."
        self.groups = ["domain"]
        self.allow_run_list = True

    def run(self, request: str) -> dict:
        encoded = request
        decoded = request
        try:
            encoded = request.encode("idna").decode()
        except UnicodeDecodeError:
            pass
        try:
            decoded = request.encode().decode("idna")
        except UnicodeDecodeError:
            pass
        return {"decoded": decoded,
                "encoded": encoded}

    def run_list(self, request_list: list[str]) -> list[dict]:
        return [self.run(req) for req in request_list]
