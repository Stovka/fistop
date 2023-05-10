# utility.py requires Python3.9 standard library
import configparser
import ctypes
import datetime
import json
import multiprocessing as mp
import os
import re
import sys
import threading as th
import logging
import logging.handlers
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, InitVar, field
from typing import Optional, Union


class Service(ABC):
    """
    Abstract service from which every custom service must inherit from. Do not modify!
    """
    name: str = ""  # Required: unique string for every service
    description: str = ""  # Optional: service description
    service_id: Optional[int] = None  # Optional: service ID
    threads: int = 1  # Optional: number of threads on which service will be run
    processes: int = 0  # Optional: number of processes on which service will be run
    timeout: int = 0  # Optional: seconds after which worker will be restarted if stuck in run method
    max_timeouts: int = 3  # Optional: how many times service can be restarted due to timeout
    groups: list[str] = ["all"]  # Optional: List of strings representing service groups
    allow_run_list: bool = False  # Optional: If set to True than run_list method will be called
    ignore: bool = False  # Optional: if set to True than service will be ignored (not loaded)

    @abstractmethod
    def run(self, request: str) -> dict:
        pass

    def run_list(self, request_list: list[str]) -> list[dict]:
        return [{"server": "Not implemented"} for _ in request_list]

    def start(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def get_info(self) -> dict:
        return {"name": self.name,
                "description": self.description,
                "service_id": self.service_id,
                "threads": self.threads,
                "processes": self.processes,
                "timeout": self.timeout,
                "max_timeouts": self.max_timeouts,
                "groups": self.groups,
                "allow_run_list": self.allow_run_list}


@dataclass(frozen=True)
class ImmutableService:
    """This dataclass immutably stores Services attributes. Definition of attributes is redundant. They are defined
    automatically in __post_init__. It is here solely so the IDE recognizes them."""
    service: InitVar[Service]
    name: str = field(init=False)
    description: str = field(init=False)
    service_id: int = field(init=False)
    threads: int = field(init=False)
    processes: int = field(init=False)
    timeout: int = field(init=False)
    max_timeouts: int = field(init=False)
    groups: list[str] = field(init=False)
    allow_run_list: bool = field(init=False)

    def __post_init__(self, service: Service):
        # Get Service default attributes
        allowed_attrs = [at for at in dir(Service) if not at.startswith("_")]
        # Here is called get_info() therefore ImmutableService can be created only after all attributes are set.
        for at_name, at in service.get_info().items():
            if at_name in allowed_attrs:
                object.__setattr__(self, at_name, at)

    def get_info(self):
        return self.__dict__


class MPLoggerError(Exception):
    pass


class MPLogger:
    def __init__(self, name: str, level: str, file_name: Optional[str] = None, syslog_address: Optional[str] = None):
        if not all(ord(c) < 128 and (c.isalnum() or c in ["_", "-", "."]) for c in name):
            raise MPLoggerError(f"Logger: Invalid log name: {name}.")
        self.logger = logging.getLogger(name)
        self.queue = None
        self.thread = None

        allowed_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if isinstance(level, str) and level.upper() not in allowed_levels:
            raise MPLoggerError(f"Logger: Invalid log level: {level}, allowed levels: {allowed_levels}")
        self.logger.setLevel(level.upper())

        if file_name and syslog_address:
            # both file_name and syslog_address != "" or None
            raise MPLoggerError(f"Logger: Invalid log destination. You can specify only one destination but "
                                f"two provided: file_name={file_name} syslog_address={syslog_address}")

        handler = None
        if not file_name and not syslog_address:
            # Stream logger
            handler = logging.StreamHandler()

        elif file_name:
            file_name = os.path.normpath(file_name)  # Normalize path
            try:
                if not os.path.exists(os.path.dirname(file_name)) and os.path.dirname(file_name) != "":
                    os.makedirs(os.path.dirname(file_name))
                handler = logging.handlers.RotatingFileHandler(file_name, maxBytes=25000000, backupCount=10)
            except FileNotFoundError:
                raise MPLoggerError(f"Logger: Invalid path: {file_name}")
            except PermissionError:
                raise MPLoggerError(f"Logger: Permission error while creating path: {file_name}")
        elif syslog_address:
            if not sys.platform.startswith("linux"):
                raise MPLoggerError(f"Logger: syslog logging is only available on linux.")
            sys_add = syslog_address.split(":")
            if len(sys_add) == 2:
                try:
                    port = int(sys_add[1])
                except ValueError:
                    raise MPLoggerError(f"Logger: Invalid syslog port: {sys_add[1]}")
                handler = logging.handlers.SysLogHandler(address=(sys_add[0], port))  # This can raise exception
            elif len(sys_add) == 1:
                handler = logging.handlers.SysLogHandler(address=sys_add[0])  # This can raise exception
            else:
                raise MPLoggerError(f"Logger: Invalid syslog address use 1.1.1.1:514 or /dev/log")

        formatter = logging.Formatter("[%(asctime)s/%(process)d/%(levelname)s] %(message)s")
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        if not file_name and not syslog_address:
            self.logger.debug(f"Logger: stream logger: {name} with level: {level} initialized")
        elif file_name:
            self.logger.debug(f"Logger: file logger: {name} with level: {level} initialized")
        elif syslog_address:
            try:
                self.debug(f"Logger: syslog logger: {name} with level: {level} initialized")
            except OSError:
                raise MPLoggerError(f"Logger: error while trying to contact syslog server.")

    def debug(self, msg: str) -> None:
        self.logger.debug(msg)

    def info(self, msg: str) -> None:
        self.logger.info(msg)

    def warning(self, msg: str) -> None:
        self.logger.warning(msg)

    def error(self, msg: str) -> None:
        self.logger.error(msg)

    def critical(self, msg: str) -> None:
        self.logger.critical(msg)

    def _mp_logger(self) -> None:
        while True:
            try:
                record = self.queue.get()
            except (BrokenPipeError, AttributeError, OSError, EOFError):
                self.logger.error(f"Logger: MP logger stopped. Queue is not accessible.")
                break
            if record is None:
                break

            if record[0] == "DEBUG":
                self.logger.debug(record[1])
            elif record[0] == "INFO":
                self.logger.info(record[1])
            elif record[0] == "WARNING":
                self.logger.warning(record[1])
            elif record[0] == "ERROR":
                self.logger.error(record[1])
            elif record[0] == "CRITICAL":
                self.logger.critical(record[1])
            else:
                self.logger.error(f"Logger: invalid log level: {record[0]}, message: {record[1]}")
        self.logger.debug("Logger: MP logging thread died.")

    def start_mp_logging(self) -> None:
        self.stop_mp_logging()
        self.queue = mp.Queue()
        # Thread is daemon because it has to stop when main thread exited
        self.thread = th.Thread(target=self._mp_logger, daemon=True, name="mp_logger")
        self.thread.start()
        self.logger.debug("Logger: MP Logging started.")

    def stop_mp_logging(self) -> None:
        if self.thread is None:
            return
        if self.queue is None:
            # MP logging thread cannot be running if queue does not exist.
            return
        # Stop/kill logging thread
        self.queue.put(None)
        self.thread.join(1)
        if self.thread.is_alive():
            self.logger.error("Logger: Killing MP logging thread")
            res = ctypes.pythonapi.PyThreadState_SetAsyncExc(self.thread.ident, ctypes.py_object(SystemExit))
            if res > 1:
                ctypes.pythonapi.PyThreadState_SetAsyncExc(self.thread.ident, 0)
        # Destroy log queue -> its thread
        self.queue.close()
        self.queue.cancel_join_thread()
        self.queue.join_thread()
        self.thread = None
        self.queue = None
        self.logger.debug("Logger: MP Logging stopped.")

    def is_running(self) -> bool:
        if self.thread is None or self.queue is None:
            return False
        return True

    def get_queue(self) -> mp.Queue:
        """Returns queue for MP logging. Queue accepts tuple (LOG_LEVEL, LOG_MESSAGE)."""
        return self.queue


class Timer:
    def __init__(self):
        self._start = None
        self.last_time = None

    def start(self) -> None:
        self._start = time.perf_counter()

    def stop(self) -> float:
        self.last_time = time.perf_counter() - self._start
        return self.last_time


class AuthManagerError(Exception):
    pass


class AuthManager:

    def __init__(self, dict_tokens: Optional[dict] = None,
                 file_tokens: Optional[str] = None,
                 token_regex: str = "",
                 bypass_user: bool = False,
                 bypass_admin: bool = False):
        self.admins = []  # List of admin tokens
        self.superusers = []  # List of superuser tokens
        self.groups = {}  # Dict of groups with services {"gr1" : [0, 1, 2]}
        self.users_mixed = {}  # Dict of user tokens containing service IDs and group names {"tok1" : [0, "gr1", 2]}
        self.users = {}  # Dict of user tokens with only service IDs {"tok1": [0, 1, 2]}
        self.k_g = "groups"
        self.k_u = "users"
        self.k_s = "superusers"
        self.k_a = "admins"

        if not isinstance(bypass_user, bool) or not isinstance(bypass_admin, bool):
            raise AuthManagerError(f"AuthManagerError: bypass_user and bypass_admin must by boolean.")
        self.bypass_user = bypass_user
        self.bypass_admin = bypass_admin
        if dict_tokens is None and file_tokens is None:
            raise AuthManagerError(f"AuthManagerError: You have to specify either dict_tokens or file_tokens.")
        if dict_tokens is not None and file_tokens is not None:
            raise AuthManagerError(f"AuthManagerError: You can specify either dict_tokens or file_tokens not both.")
        # Validate token regex
        try:
            re.compile(token_regex)
            self.token_regex = token_regex
        except re.error:
            raise AuthManagerError(f"AuthManagerError: token_regex: {token_regex} is not valid regex")
        # Load tokens
        if dict_tokens is not None:
            user_tokens = dict_tokens
        else:
            # Disable inspection -> file_config cannot be None here
            # noinspection PyTypeChecker
            user_tokens = self._parse_file(file_tokens)
        # Validate tokens
        empty_tokens = {self.k_g: {}, self.k_u: {}, self.k_s: [], self.k_a: []}
        t_source = "provided dictionary"
        if file_tokens:
            t_source = file_tokens
        for key in user_tokens:
            # Check that all required keys exist
            if key not in empty_tokens.keys():
                raise AuthManagerError(
                    f"AuthManagerError: Invalid key: {key} in {t_source} valid structure: {empty_tokens}")
            # Check if values are of required data type
            if not isinstance(user_tokens[key], type(empty_tokens[key])):
                raise AuthManagerError(f"AuthManagerError: Invalid data type of value: {user_tokens[key]} in "
                                       f"i{t_source} expected:{type(empty_tokens[key])} got: {type(user_tokens[key])}")
        # Check if every key was validated
        if len(user_tokens) != len(empty_tokens):
            raise AuthManagerError(f"AuthManagerError: Missing key in {t_source} valid "
                                   f"structure: {empty_tokens}")
        # Load admin tokens
        for adm_token in user_tokens[self.k_a]:
            if not self.validate_token_format(adm_token):
                raise AuthManagerError(f"AuthManagerError: Invalid admin token: {adm_token} in {t_source} "
                                       f"token did not match token_regex: {token_regex}")
            self.admins.append(adm_token)
        # Load superuser tokens
        for su_token in user_tokens[self.k_s]:
            if not self.validate_token_format(su_token):
                raise AuthManagerError(f"AuthManagerError: Invalid superuser token: {su_token} in {t_source} "
                                       f"token did not match token_regex: {token_regex}")
            self.superusers.append(su_token)
        # Load groups
        for group_name in user_tokens[self.k_g]:
            # Group name must be string
            if not isinstance(group_name, str):
                raise AuthManagerError(f"AuthManagerError: Invalid group name: {group_name} in {t_source}")
            # Group name cannot be string number
            if group_name.isdigit():
                raise AuthManagerError(f"AuthManagerError: Invalid group name: {group_name} group name "
                                       f"must no be a string numbers in {t_source}")
                # It is because 1. It is misleading 2. To simplify runtime tokens modifications/creations. There
                # group name may come as strings and we need to differentiate between them and service IDs
            # Group name value must be list
            if not isinstance(user_tokens[self.k_g][group_name], list):
                # Convert to list
                user_tokens[self.k_g][group_name] = [user_tokens[self.k_g][group_name]]
            # Group services must be integers
            clean_list = []
            for srv_id in user_tokens[self.k_g][group_name]:
                if srv_id is None or srv_id == "":
                    continue  # Ignore None and ""
                if not isinstance(srv_id, int):
                    raise AuthManagerError(f"AuthManagerError: Invalid value: {srv_id} of group name: {group_name} "
                                           f"expected: int in {t_source}")
                clean_list.append(srv_id)
            user_tokens[self.k_g][group_name] = clean_list
        self.groups = user_tokens[self.k_g]
        # Load users and convert group names to service IDs
        for usr_token in user_tokens[self.k_u]:
            if not self.validate_token_format(usr_token):
                raise AuthManagerError(f"AuthManagerError: Invalid user token: {usr_token} in {t_source} "
                                       f"token did not match token_regex: {token_regex}")
            # User token value must be list
            if not isinstance(user_tokens[self.k_u][usr_token], list):
                # Convert to list
                user_tokens[self.k_u][usr_token] = [user_tokens[self.k_u][usr_token]]
            srv_ids = set()
            for srv_id in user_tokens[self.k_u][usr_token]:
                if srv_id is None or srv_id == "":
                    continue  # Ignore None and ""
                # srv_id is int service ID or str Group name
                if isinstance(srv_id, int):
                    # srv_id is Service ID
                    srv_ids.add(srv_id)
                elif isinstance(srv_id, str):
                    # srv_id is Group name
                    if srv_id not in self.groups:
                        raise AuthManagerError(f"AuthManagerError: group name {srv_id} does not exist in {t_source}")
                    for s_id in self.groups[srv_id]:
                        # convert group name to service IDs
                        srv_ids.add(s_id)
                else:
                    # srv_id is not int or string
                    raise AuthManagerError(f"AuthManagerError: Invalid value: {srv_id} of group name: {usr_token} "
                                           f"expected: int or str in {t_source}")
            self.users[usr_token] = [s for s in srv_ids]
        self.users_mixed = user_tokens[self.k_u]

    def validate_token_format(self, token: str) -> bool:
        """Token validation. If is instance of str and match token_regex"""
        if not isinstance(token, str):
            return False
        return bool(re.match(self.token_regex, token))

    def _parse_file(self, path: str) -> dict:
        """Load tokens from file."""
        if path.endswith(".json"):
            return self._parse_json_tokens(path)
        elif path.endswith(".ini"):
            return self._parse_ini_tokens(path)

    @staticmethod
    def _parse_json_tokens(path: str) -> dict:
        """Parse JSON file containing tokens. Lines starting with # are skipped (assuming comments)."""
        user_config = ""
        try:
            with open(path) as f:
                for line in f:
                    if not line.startswith("#"):
                        user_config += line
        except FileNotFoundError:
            raise AuthManagerError(f"AuthManagerError: Tokens file: {path} does not exist.")
        except PermissionError:
            raise AuthManagerError(f"AuthManagerError: Tokens file: {path} permission error.")
        try:
            return json.loads(user_config)
        except json.decoder.JSONDecodeError:
            raise AuthManagerError(f"AuthManagerError: Syntax error in tokens file: {path}")

    def _parse_ini_tokens(self, path: str) -> dict:
        """Parse INI file containing tokens. Comments are ; or #"""
        config_parser = configparser.ConfigParser(allow_no_value=True)
        user_config = ""
        try:
            with open(path) as f:
                for line in f:
                    user_config += line
        except FileNotFoundError:
            raise AuthManagerError(f"AuthManagerError: Tokens file: {path} does not exist.")
        except PermissionError:
            raise AuthManagerError(f"AuthManagerError: Tokens file: {path} permission error.")
        try:
            config_parser.read_string(user_config)
        except (configparser.ParsingError, configparser.DuplicateOptionError):
            raise AuthManagerError(f"AuthManagerError: Syntax error in tokens file: {path}")
        for section in config_parser.items():
            try:
                if section[0] == "DEFAULT":
                    continue  # Skip default section
                if section[0] == "SERVICES":
                    continue  # Skip services section
                if section[0] not in [self.k_g.upper(), self.k_u.upper(), self.k_s.upper(), self.k_a.upper()]:
                    raise AuthManagerError(f"AuthManagerError: Invalid section: {section[0]} in tokens file: {path}")
            except IndexError:
                raise AuthManagerError(f"AuthManagerError: Syntax error in tokens file: {path}")
        parsed_tokens = {self.k_g: {}, self.k_u: {}, self.k_s: [], self.k_a: []}
        try:
            for item in config_parser[self.k_g.upper()]:
                parsed_tokens[self.k_g][item] = self.guess_type(config_parser[self.k_g.upper()][item])
            for item in config_parser[self.k_u.upper()]:
                parsed_tokens[self.k_u][item] = self.guess_type(config_parser[self.k_u.upper()][item])
            for item in config_parser[self.k_s.upper()]:
                parsed_tokens[self.k_s].append(item)
            for item in config_parser[self.k_a.upper()]:
                parsed_tokens[self.k_a].append(item)
        except KeyError as err:
            raise AuthManagerError(f"AuthManagerError: Missing key: {err} in tokens file: {path}")
        return parsed_tokens

    def guess_type(self, s: str):
        if not isinstance(s, str):
            return ""
        x = s.strip()
        try:
            if x == "" or x == "''" or x == '""':
                return ""
            elif re.match("[0-9]+$", x):
                return int(x)
            if " " in x:
                return [self.guess_type(y) for y in x.split(" ") if y.strip() != ""]
            else:
                return x
        except ValueError:
            return x

    @staticmethod
    def _get_delta_list(list_orig: list, list_saved: list) -> (list, list):
        """Returns two lists.
        add_list -> what is in list_orig but not in list_saved
        del_list -> what is in list_saved but not in list_orig"""
        add_list = []
        del_list = []
        for token in list_orig:
            if token not in list_saved:
                add_list.append(token)
        for token in list_saved:
            if token not in list_orig:
                del_list.append(token)
        return add_list, del_list

    @staticmethod
    def _get_delta_dict(dict_orig: dict, dict_saved: dict) -> (dict, dict):
        """Returns two lists.
        add_dict -> what is in dict_orig but not in dict_saved OR values do not match!
        del_dict -> what is in dict_saved but not in dict_orig"""
        add_dict = {}
        del_dict = {}
        for key, value in dict_orig.items():
            if key not in dict_saved:
                add_dict[key] = value
                continue
            if value != dict_saved[key]:
                add_dict[key] = value

        for key, value in dict_saved.items():
            if key not in dict_orig:
                del_dict[key] = value
        return add_dict, del_dict

    def get_config_diff(self, path: str) -> Union[dict, None]:
        """Computes difference between running config and given file. Returns changes keys/values. If there is error
        while reading file it returns None"""
        try:
            # Initialize new instance of AuthManager with file tokens. Do not raise exception
            saved_tokens = AuthManager(file_tokens=path)
        except AuthManagerError:
            return None
        difference = {}
        su_add, su_del = self._get_delta_list(self.superusers, saved_tokens.superusers)
        a_add, a_del = self._get_delta_list(self.admins, saved_tokens.admins)
        g_add, g_del = self._get_delta_dict(self.groups, saved_tokens.groups)
        u_add, u_del = self._get_delta_dict(self.users, saved_tokens.users)

        if len(su_add) > 0 or len(su_del) > 0:
            difference[self.k_s] = {}
            difference[self.k_s]["add"] = su_add
            difference[self.k_s]["del"] = su_del
        if len(a_add) > 0 or len(a_del) > 0:
            difference[self.k_a] = {}
            difference[self.k_a]["add"] = a_add
            difference[self.k_a]["del"] = a_del
        if len(g_add) > 0 or len(g_del) > 0:
            difference[self.k_g] = {}
            difference[self.k_g]["add"] = g_add
            difference[self.k_g]["del"] = g_del
        if len(u_add) > 0 or len(u_del) > 0:
            difference[self.k_u] = {}
            difference[self.k_u]["add"] = u_add
            difference[self.k_u]["del"] = u_del
        return difference

    def save_tokens(self, path: str, create_backup: bool) -> bool:
        """Save running config to file. Optionally create backup of old file."""
        if path.lower().endswith(".json"):
            file_tokens = json.dumps(self.get_dict_tokens(), indent=2)
        elif path.lower().endswith(".ini"):
            file_tokens = self.get_ini_tokens()
        else:
            return False
        if create_backup is False:
            try:
                with open(path, "w+") as f:
                    f.write(file_tokens)
            except (PermissionError, FileNotFoundError):
                return False
            return True
        backup_folder = "tokens_backups"
        backup_format_prefix = "%Y-%m-%d_%H-%M-%S"
        # Create backup folder if it does not exist
        backup_dir_path = os.path.join(os.path.dirname(path), backup_folder)
        if not os.path.isdir(backup_dir_path):
            os.mkdir(backup_dir_path)
        _, file_name = os.path.split(path)
        # Create file name
        now = datetime.datetime.now()
        new_file_name = now.strftime(backup_format_prefix) + file_name
        # Check if file already exists -> pick new name
        deadlock_prev = 0
        while os.path.exists(new_file_name):
            # Potential deadlock -> exit if 16x unsuccessful -> 16*0.25 -> max 4s
            time.sleep(0.25)
            now = datetime.datetime.now()
            new_file_name = now.strftime(backup_format_prefix) + file_name
            deadlock_prev += 1
            if deadlock_prev >= 16:
                return False
        # Move old tokens to backup folder a rename it
        os.replace(path, os.path.join(backup_dir_path, new_file_name))
        # Write new tokens
        with open(path, "w+") as f:
            # Write tokens
            f.write(file_tokens)

        return True

    def get_ini_tokens(self) -> str:
        """Convert running config to INI string."""
        ini_tokens = f"[{self.k_g.upper()}]\n"
        for g in self.groups:
            services = ' '.join(str(x) for x in self.groups[g])
            if not services:
                ini_tokens += f"{g}\n"
            else:
                ini_tokens += f"{g} = {services}\n"
        ini_tokens += f"\n[{self.k_u.upper()}]\n"
        for u in self.users:
            user_services = ' '.join(str(x) for x in self.users[u])
            if not user_services:
                ini_tokens += f"{u}\n"
            else:
                ini_tokens += f"{u} = {user_services}\n"
        ini_tokens += f"\n[{self.k_s.upper()}]\n"
        for s in self.superusers:
            ini_tokens += f"{s}\n"
        ini_tokens += f"\n[{self.k_a.upper()}]\n"
        for a in self.admins:
            ini_tokens += f"{a}\n"
        return ini_tokens

    def get_dict_tokens(self) -> dict:
        """Convert running config to dict."""
        return {
            self.k_g: self.groups,
            self.k_u: self.users_mixed,
            self.k_s: self.superusers,
            self.k_a: self.admins
        }

    def get_len_groups(self) -> int:
        return len(self.groups)

    def get_len_users(self) -> int:
        return len(self.users)

    def get_len_superusers(self) -> int:
        return len(self.superusers)

    def get_len_admins(self) -> int:
        return len(self.admins)

    def add_admin(self, token: str) -> bool:
        """Add admin to running config."""
        if not self.validate_token_format(token):
            return False
        if token not in self.admins:
            self.admins.append(token)
        return True

    def remove_admin(self, token: str) -> bool:
        """Remove admin from running config."""
        if not self.validate_token_format(token):
            return False
        if token not in self.admins:
            return False
        self.admins.pop(self.admins.index(token))
        return True

    def add_superuser(self, token: str) -> bool:
        """Add superuser to running config."""
        if not self.validate_token_format(token):
            return False
        if token not in self.superusers:
            self.superusers.append(token)
        return True

    def remove_superuser(self, token: str) -> bool:
        """Remove superuser from running config."""
        if not self.validate_token_format(token):
            return False
        if token not in self.superusers:
            return False
        self.superusers.pop(self.superusers.index(token))
        return True

    def add_group(self, group_name: str, group_services: list) -> bool:
        """Add group with group services to running config."""
        if not isinstance(group_services, list) or not isinstance(group_name, str):
            return False
        if group_name.isdigit():
            return False
        # Validate group_services -> empty list is ok
        new_group_services = []
        for s_id in group_services:
            if isinstance(s_id, int):
                new_group_services.append(s_id)
            elif isinstance(s_id, str):
                new_s_id = s_id.strip()  # Strip leading and trailing whitespaces
                if new_s_id == "":
                    continue  # Ignore ""
                if new_s_id.isdigit():
                    # Allow string numbers -> convert to int
                    new_group_services.append(int(new_s_id))
                else:
                    return False
            else:
                return False

        # Overwrite existing group / create new group
        self.groups[group_name] = new_group_services
        return True

    def remove_group(self, group_name: str) -> bool:
        """Remove group from running config. Do not allow removal if group is assign to some user."""
        if group_name not in self.groups:
            return False
        for u_services in self.users_mixed.values():
            if group_name in u_services:
                # group_name exists in some user
                return False
        self.groups.pop(group_name)
        return True

    def add_user(self, token: str, user_services: list) -> bool:
        """Add user with user services to running config. User can be added without services. If group name is provided
        in user_services it must exists first otherwise it will be rejected."""
        # It is because group name has to be converted to services IDs
        if not self.validate_token_format(token):
            return False
        if not isinstance(user_services, list):
            return False
        # Validate/filter/Normalize user_services
        new_group_services = []
        for s_id in user_services:
            if isinstance(s_id, int):
                # Service ID -> do not validate (it is OK even if service does not exist)
                new_group_services.append(s_id)
            elif isinstance(s_id, str):
                new_s_id = s_id.strip()  # Strip leading and trailing whitespaces
                if new_s_id == "":
                    continue  # Ignore ""
                if new_s_id.isdigit():
                    # String number is interpreted as number. This is possible because string numbers are prohibited
                    # as group names. Therefore string numbers are Service IDs
                    new_group_services.append(int(new_s_id))
                    continue
                if new_s_id in self.groups:
                    new_group_services.append(new_s_id)
                else:
                    # Provided group is not in self.groups
                    return False
            else:
                return False
        # Convert group names to service IDs
        clean_s_ids = set()
        for s_id in new_group_services:
            if isinstance(s_id, int):
                clean_s_ids.add(s_id)
            else:
                # s_id is group name
                for s_id_num in self.groups[s_id]:
                    clean_s_ids.add(s_id_num)

        self.users_mixed[token] = new_group_services
        self.users[token] = [s_id for s_id in clean_s_ids]
        return True

    def remove_user(self, token: str) -> bool:
        """Remove user from running config."""
        if token not in self.users:
            return False
        self.users.pop(token)
        return True

    def exist(self, token: str) -> bool:
        """Check if token exist in user/superuser/admin. Or bypass is active."""
        if self.bypass_user:
            return True  # Does not validate token format
        if self.bypass_admin:
            return True  # Does not validate token format
        if not self.validate_token_format(token):
            return False
        if token in self.superusers:
            return True
        if token in self.admins:
            return True
        if self.users.get(token) is not None:
            return True
        return False

    def authorize_user(self, user_token: str, service_id: int) -> bool:
        """Check if token is authorized to service ID."""
        if self.bypass_user:
            return True  # Does not validate token format
        if not self.validate_token_format(user_token):
            return False
        if user_token in self.superusers:
            return True
        user_services = self.users.get(user_token)
        if user_services is None:
            # Token does not exist
            return False
        if service_id not in user_services:
            # Token exists but service_id not
            return False
        return True

    def authorize_user_multiple(self, user_token: str, service_ids: list) -> bool:
        """Check if token is authorized all service IDs in list."""
        if self.bypass_user:
            return True  # Does not validate token format
        if not self.validate_token_format(user_token):
            return False
        if user_token in self.superusers:
            return True
        for srv_id in service_ids:
            if self.authorize_user(user_token, srv_id) is False:
                return False
        return True

    def get_user_authorized(self, user_token: str, service_ids: list) -> list:
        """Returns filtered list of authorized service IDs of given token. Not all authorized services but those
        from provided list (service_ids)."""
        if self.bypass_user:
            return service_ids  # Does not validate token format
        if not self.validate_token_format(user_token):
            return []
        if user_token in self.superusers:
            return service_ids
        user_services = self.users.get(user_token)
        if user_services is None:
            return []
        authorized = []
        for srv_id in service_ids:
            if srv_id in user_services:
                authorized.append(srv_id)
        return authorized

    def authorize_admin(self, admin_token: str) -> bool:
        """Check if token exists in admin list."""
        if self.bypass_admin:
            return True  # Does not validate token format
        if not self.validate_token_format(admin_token):
            return False
        if admin_token not in self.admins:
            return False
        return True

    def authorize_superuser(self, user_token: str) -> bool:
        """Check if token exists in superuser list."""
        if self.bypass_user:
            return True  # Does not validate token format
        if not self.validate_token_format(user_token):
            return False
        if user_token not in self.superusers:
            return False
        return True


class ConfigError(Exception):
    pass


class Config:
    """
        Default config. Do not modify! To change config use settings/config.json.
    """
    port: int = 80  # Port on which application will listen
    ssl_port: int = 443  # Port on which application will listen (if use_ssl is set to True).
    max_message_size: int = 64  # Maximum size of request
    max_database_size: int = 10000  # Maximum number of cached results !per service!
    max_result_age: int = 1800  # Time after which cached result will be deleted
    max_service_run_time = 120  # This should be greater than the maximum run time of any service (in seconds).
    service_start_timeout: float = 3.0  # Timeout for service start() method.
    service_shutdown_timeout: float = 3.0  # Timeout for service shutdown() method.
    terminator_idle_cycle: float = 1.0  # Terminator sleep time between idle cycles. Should be 1 in the most scenarios.
    th_proc_response_time: float = 0.5  # Time for threads, processes to react.
    uvicorn_workers: int = 1  # Number of processes for uvicorn HTTP server.
    uvicorn_listen: str = "0.0.0.0"  # IP On which should uvicorn listen.
    include_dirs: list[str] = ["settings"]  # List of directories containing service definitions.
    services: list[str] = ["services"]  # List of modules (in included_dirs) with service definitions (services.py).
    tokens_path: str = "settings/tokens.ini"  # File containing tokens and tokens groups.
    token_regex: str = "[A-Za-z0-9]{10,}$"  # Token format validation. You can enter "" if you want no validation.
    key_sensitivity: bool = False  # Differentiate between upper/lower letters in service names and service groups
    shared_logger: bool = True  # If True, then DatabaseManager and ServiceManager will share same logger.
    disable_name_groups: bool = True  # Disable creation of group names for all service names.
    disable_all_groups: bool = True  # Disable common group (all) for all services.
    disable_config_endpoints: bool = False  # Disable admin configuration API endpoints.
    bypass_user_auth: bool = False  # Everyone (even without token) has access to all services and service groups.
    bypass_admin_auth: bool = False  # Everyone (even without token) has access to all administration endpoints.
    tokens_backups: bool = True  # Create backup of tokens file when modified at run time.
    serve_web_client: bool = True  # FastAPI will serve web client.
    allow_header_token: bool = True  # FastAPI will accept token from header.
    allow_parameter_token: bool = True  # FastAPI will accept token from parameter.
    allow_cookie_token: bool = True  # FastAPI will accept token from cookie.
    use_ssl: bool = False  # This will start uvicorn with SSL with port ssl_port. Keys must exist first
    ssl_cert: str = "settings/cert/localhost.crt"  # Certificate for SSL. Do not use this certificate. Use your own.
    ssl_key: str = "settings/cert/localhost.key"  # Key for SSL certificate. Do not use this certificate. Use your own.

    db_logger_name: str = "database_logger"
    db_logger_level: str = "INFO"  # Log level options: DEBUG, INFO, WARNING, ERROR, CRITICAL
    db_logger_filename: str = ""  # "" means logging to console. Specify path (logs/app.log) to log to the file.
    db_logger_syslog_address: str = ""  # Address of a syslog server (127.0.0.1:514 or /dev/log) Linux only.

    man_logger_name: str = "manager_logger"  # This will be applied only if shared_logger is False.
    man_logger_level: str = "INFO"  # This will be applied only if shared_logger is False.
    man_logger_filename: str = "logs/manager.log"  # This will be applied only if shared_logger is False.
    man_logger_syslog_address: str = ""  # This will be applied only if shared_logger is False.

    def __init__(self, dict_config: Optional[dict] = None, file_config: Optional[str] = None):
        """
        Config initialization and validation. You can pass dict (JSON object) config or path to file containing JSON or
        INI config. Provided config does not need to have all config items. Provided items will overwrite default
        values. Provided items will be validated and converted to Config object. If nothing is passed then default
        config is returned.
        """
        # No custom config
        if dict_config is None and file_config is None:
            return  # return default config does not need validation
        if dict_config is not None and file_config is not None:
            raise ConfigError(f"Config: You can specify either dict_config or file_config not both.")

        c_source = "provided dictionary"
        if dict_config is not None:
            user_config = dict_config
        else:
            # Disable inspection -> file_config cannot be None here
            # noinspection PyTypeChecker
            user_config = self._parse_file(file_config)
            c_source = file_config

        # Custom config validation => compare data types of user/default config
        # When validation is done than setting is applied to self (Config object on which __init__ is called)
        default_config = self.get_default_dict_config()
        for key in user_config.keys():
            # Check if key exists in default config
            try:
                attr = default_config[key]
            except KeyError:
                raise ConfigError(f"Config: Invalid key: {key} in {c_source}")
            # Check if provided data type is equal to default.
            # Allow int if default is float. Do not allow float if default is int
            if type(user_config[key]) == type(attr) or (isinstance(user_config[key], int) and isinstance(attr, float)):
                # Do not allow negative numbers or zero
                if isinstance(user_config[key], (int, float)) and user_config[key] < 0:
                    raise ConfigError(f"Config: Invalid value: {user_config[key]} in {c_source}")
                # If it is list -> check list items if they are correct type
                if isinstance(user_config[key], list):
                    for item in user_config[key]:
                        if not isinstance(item, type(attr[0])):
                            # Type of item in list differs from default type
                            raise ConfigError(
                                f"Config: Invalid value: {item} in list: {user_config[key]} for key: {key} expected "
                                f"type: list[{type(attr[0])}] got type: {type(item)} in {c_source}")
                # Set new value
                setattr(self, key, user_config[key])
            # Allow single value if default is list but only if type is equal to type inside the (default) list
            elif type(attr) == list and type(user_config[key]) != list:
                if isinstance(user_config[key], type(attr[0])):
                    # Convert single value to list
                    setattr(self, key, [user_config[key]])
                else:
                    raise ConfigError(f"Config: Invalid value: {user_config[key]} for key: {key} expected type: "
                                      f"list[{type(attr[0])}] got type: {type(user_config[key])} in {c_source}")
            else:
                raise ConfigError(f"Config: Invalid value: {user_config[key]} for key: {key} expected type: "
                                  f"{type(attr)} got type: {type(user_config[key])} in {c_source}")
        # Special case -> validate regex expression
        # Regex is also validated while creating AuthManager object so this is redundant. Here it is only so that user
        # know the error was caused by invalid config (ConfigError will be raise instead of AuthManagerError)
        try:
            re.compile(self.token_regex)
        except re.error:
            raise ConfigError(f"Config: Invalid token regex: {self.token_regex} in {c_source}")

        # Check if at least one token method is allowed
        if False is self.allow_header_token is self.allow_parameter_token is self.allow_cookie_token:
            # Check if at least user auth bypass is active -> if yes than is it valid option
            if self.bypass_user_auth is False:
                raise ConfigError(f"Config: All token options (header, parameter, cookie) are False and auth bypass "
                                  f"is not set. It would be impossible to authenticate in {c_source}")
        # Remove .py from services -> avoid confusion when importing module
        for srv_index, srv_module in enumerate(self.services):
            if srv_module.endswith(".py"):
                self.services[srv_index] = self.services[srv_index][:-3]
        # Limit values
        if self.port > 65535 or self.ssl_port > 65535:
            raise ConfigError(f"Config: Invalid port: {self.port} or ssl_port: {self.ssl_port} in {c_source}")
        if self.max_service_run_time < 10:
            raise ConfigError(f"Config: Invalid max_service_run_time: {self.max_service_run_time} it cannot be less "
                              f"then 10 in {c_source}")
        if self.service_start_timeout < 1 or self.service_shutdown_timeout < 1:
            raise ConfigError(f"Config: service_start_timeout and service_shutdown_timeout cannot be less 1 "
                              f"in {c_source}")
        if self.terminator_idle_cycle < 0.2 or self.terminator_idle_cycle > 60:
            raise ConfigError(f"Config: terminator_idle_cycle cannot be lower then 0.2 or greater then 60 "
                              f"in {c_source}")
        if self.th_proc_response_time < 0.1 or self.th_proc_response_time > 10:
            raise ConfigError(f"Config: th_proc_response_time cannot be lower then 0.1 or greater then 10 "
                              f"in {c_source}")

    def _parse_file(self, path: str) -> dict:
        """Load config from file as dictionary."""
        if path.endswith(".json"):
            return self._parse_json_config(path)
        elif path.endswith(".ini"):
            return self._parse_ini_config(path)

    @staticmethod
    def _parse_json_config(path: str) -> dict:
        """Config file is a JSON. Lines starting with # are skipped (assuming comments)."""
        user_config = ""
        try:
            with open(path) as f:
                for line in f:
                    if not line.startswith("#"):
                        user_config += line
        except FileNotFoundError:
            raise ConfigError(f"Config: Config file: {path} does not exist.")
        except PermissionError:
            raise ConfigError(f"Config: Config file: {path} permission error.")
        try:
            return json.loads(user_config)
        except json.decoder.JSONDecodeError:
            raise ConfigError(f"Config: Syntax error in config file: {path}")

    def _parse_ini_config(self, path: str) -> dict:
        """Config file is a INI. Comments are ; or #"""
        config_parser = configparser.ConfigParser()
        user_config = ""
        try:
            with open(path) as f:
                for line in f:
                    user_config += line
        except FileNotFoundError:
            raise ConfigError(f"Config: Config file: {path} does not exist.")
        except PermissionError:
            raise ConfigError(f"Config: Config file: {path} permission error.")
        try:
            config_parser.read_string(user_config)
        except (configparser.ParsingError, configparser.DuplicateOptionError):
            raise ConfigError(f"Config: Syntax error in config file: {path}")
        for section in config_parser.items():
            try:
                if section[0] == "DEFAULT":
                    continue  # Skip default section -> only valid section
                raise AuthManagerError(f"AuthManagerError: Invalid section: {section[0]}. There can be only one section"
                                       f" \'DEFAULT\' in tokens file: {path}")
            except IndexError:
                raise AuthManagerError(f"AuthManagerError: Syntax error in tokens file: {path}")
        parsed_config = {}
        for item in config_parser["DEFAULT"]:
            parsed_config[item] = self.guess_type(config_parser["DEFAULT"][item])
        return parsed_config

    def guess_type(self, s: str):
        """Guess data type from string. White space between list items."""
        x = s.strip()
        try:
            if x == "" or x == "''" or x == '""':
                return ""
            elif re.match("[0-9]+$", x):
                return int(x)
            elif re.match("[0-9]+.[0-9]+$", x):
                return float(x)
            elif re.match("(true|false|True|False)$", x):
                return True if x in ["true", "True"] else False
            if " " in x:
                return [self.guess_type(y) for y in x.split(" ") if y.strip() != ""]
            else:
                return x
        except ValueError:
            return x

    def get_changed(self) -> dict:
        """Get dictionary of keys and values from current config that differs from default config."""
        changed_values = {}
        current_config = self.get_current_dict_config()
        default_config = self.get_default_dict_config()
        for key in current_config.keys():
            if current_config[key] != default_config[key]:
                changed_values[key] = current_config[key]
        return changed_values

    @staticmethod
    def get_default_dict_config() -> dict:
        """Get default config as dictionary."""
        default_config = {}
        for attr in Config.__dict__.keys():
            if not attr.startswith("__") and not callable(getattr(Config, attr)):
                default_config[attr] = getattr(Config, attr)
        return default_config

    def get_current_dict_config(self) -> dict:
        """Convert current config to dictionary."""
        current_config = {}
        for attr, value in self.__dict__.items():
            current_config[attr] = value
        return current_config

    def validate(self) -> bool:
        """Runtime config validation does not throw exception."""
        try:
            # Try to create new instance of Config. If it is successful than config is valid.
            Config(dict_config=self.get_current_dict_config())
        except ConfigError:
            return False
        return True
