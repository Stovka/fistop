# database.py requires Python3.9 standard library
import ctypes
import datetime
import os
import queue
import re

import _queue
import collections
import sys
import threading as th
import time
from typing import Union, Optional

import utility
import manager

# Do not modify! Use settings/config.ini
GET_TIMEOUT: float = 0.01
GET_ITER: int = 200
TMP_ITER: int = 20


class DatabaseManager:

    def __init__(self, config: Optional[utility.Config] = None, tokens: Optional[dict] = None):
        # Initialize Config
        if isinstance(config, utility.Config):
            if config.validate() is False:
                raise utility.ConfigError("Config: Invalid config")
            self.config = config  # Custom config
        else:
            self.config = utility.Config()  # Default config
        # Add included directories into paths
        for directory in self.config.include_dirs:
            if not os.path.exists(os.path.normpath(directory)):
                raise utility.ConfigError(f"Config: Include directory: {directory} does not exit")
            sys.path.insert(0, os.path.normpath(directory))
        self.version = self._load_version("version.txt")
        # Initialize AuthManager
        # There is no try-catch because app must not start with invalid AuthManager
        if tokens:
            self.aman = utility.AuthManager(dict_tokens=tokens,
                                            token_regex=self.config.token_regex,
                                            bypass_user=self.config.bypass_user_auth,
                                            bypass_admin=self.config.bypass_admin_auth)
        else:
            self.aman = utility.AuthManager(file_tokens=os.path.normpath(self.config.tokens_path),
                                            token_regex=self.config.token_regex,
                                            bypass_user=self.config.bypass_user_auth,
                                            bypass_admin=self.config.bypass_admin_auth)
        # Create logger
        self.logger = utility.MPLogger(name=self.config.db_logger_name,
                                       level=self.config.db_logger_level,
                                       file_name=self.config.db_logger_filename,
                                       syslog_address=self.config.db_logger_syslog_address)
        self.logger.start_mp_logging()
        if self.config.get_changed():
            self.logger.debug(f"DatabaseManager: Modified settings: {self.config.get_changed()}")
        else:
            self.logger.debug(f"DatabaseManager: Using default config")
        self.logger.debug(f"DatabaseManager: Current version: {self.version}")
        self.logger.debug(f"DatabaseManager: Tokens successfully loaded from"
                          f"{': dictionary' if tokens else ' file: '+ self.config.tokens_path}.")
        # Create ServiceManager and start ServiceManager
        self.man = manager.ServiceManager(self.config, self.logger)
        # Check if there are any users/superusers
        if self.aman.get_len_users() == 0 and self.aman.get_len_superusers() == 0:
            if self.config.bypass_user_auth is False:
                # bypass_user_auth is False -> not possible to authenticate
                self.logger.stop_mp_logging()
                raise utility.ConfigError("Config: There are no users nor superusers and bypass_user_auth is False. "
                                          "It would be impossible to run any service.")
            else:
                self.logger.info("DatabaseManager: There are no users nor superusers but bypass_user_auth is True. "
                                 "Continuing")
        # List of services. This does not store actual instances just srv_id a srv_name
        self.services = self.man.get_services()  # [(srv1_id, srv1_name), ...]
        self.service_outputs = [collections.OrderedDict() for _ in self.services]
        self.tmp_results = []
        self.service_output_queues = []
        self.service_input_queues = []
        self.running = False
        self.request_dicts = []  # List of dicts
        self.garbage_queue = queue.Queue()
        self.gb_collector = None
        self.initialized = False
        self.initialize()
        self.start_services()

    def initialize(self) -> None:
        """Initialize ServiceManager with services, start logger, gb_collector. It normally should not be called because
        it is called automatically when initializing DatabaseManager class. It can be called after shutdown to
        reinitialize again."""
        if self.initialized is True:
            self.logger.error(f"ServiceManager: Already initialized")
            return
        if self.running is True:
            # Should never happen
            self.logger.error(f"ServiceManager: Cannot initialize when running.")
            return
        if self.logger.is_running() is False:
            self.logger.start_mp_logging()

        self.tmp_results = []
        self.service_input_queues = []
        self.service_input_queues = []
        self.request_dicts = []
        for srv in self.services:
            self.service_input_queues.append(self.man.get_service_input_queue(srv[0]))
            self.service_output_queues.append(self.man.get_service_output_queue(srv[0]))
            self.tmp_results.append(queue.Queue())
            self.request_dicts.append({})

        self.initialized = True
        self._start_gb_collector()
        self.logger.debug("DatabaseManager: initialized")

    def start_services(self) -> bool:
        """Start all services. Creates new input/output queues old ones will not exists anymore."""
        if self.running is True:
            return False
        if self.initialized is False:
            return False
        self.man.start()
        self.running = True
        self.logger.debug("DatabaseManager: Services started")
        return True

    def stop_services(self) -> bool:
        """Stop all running services. Does not clear database. If you want to exit use shutdown."""
        if self.running is False:
            return False
        self.running = False
        self.man.stop()
        return True

    def restart_services(self) -> bool:
        self.stop_services()
        self.start_services()
        return True

    def shutdown(self) -> bool:
        """Stop all services logger, gb_collector, ServiceManager, clear database. After this calling start will not be
        possible nevertheless you can reinitialize app by calling initialize(). """
        self.running = False
        self.initialized = False
        self.man.shutdown()
        self.logger.stop_mp_logging()
        self._stop_gb_collector()
        self._clear_database()
        self.logger.debug("DatabaseManager: Shutdown complete")
        return True

    @staticmethod
    def _load_version(path: str) -> str:
        version_regex = "^v{0,1}([0-9]{1,6}.){1,5}[0-9]{1,5}[a-zA-Z]{0,5}$"
        with open(path) as f:
            version = f.read().strip()
        if bool(re.search(version_regex, version)) is False:
            raise utility.ConfigError(f"Config: Invalid version file: {path}")
        return version

    def _clear_database(self) -> None:
        """Create new service databases/Remove all cached results."""
        self.service_outputs = [collections.OrderedDict() for _ in self.services]

    def _get_database_result(self, srv_id: int, request: str) -> Union[dict, None]:
        """Get result for a request from service database. It will pop the result if it is too old."""
        result = self.service_outputs[srv_id].get(request)
        if not result:
            return None
        if (datetime.datetime.now() - result["timestamp"]).total_seconds() > self.config.max_result_age:
            self.service_outputs[srv_id].pop(request)
            self.logger.debug(f"DatabaseManager: Removing old result from database for request: {request}")
            return None
        self.service_outputs[srv_id].move_to_end(request)
        self.logger.debug(f"DatabaseManager: Result for request: {request}, service_id: {srv_id} found in database.")
        return result

    def _get_result(self, srv_id: int, request_id: int, request: Union[str, list[str]]) \
            -> Union[dict, list[dict], None]:
        """Get result for a request from service output queue. Before result is returned it is saved to the database.
        If different result was found than it is placed to tmp queue. (Collision between threads)"""
        result = self.man.get_service_result(srv_id, timeout=GET_TIMEOUT)
        if result is None:
            return None
        if result[0] == request_id:
            self.logger.debug(f"DatabaseManager: Result for request_id: {request_id}, "
                              f"service_id: {srv_id} found in ServiceManager.")
            if isinstance(result[1], list):
                outputs = []
                for request, output in zip(request, result[1]):
                    outputs.append(self._save_result(srv_id, request, output))
                return outputs
            else:
                return self._save_result(srv_id, request, result[1])
        else:
            self._save_tmp_result(srv_id, result)
            return None

    def _get_result_no_wait(self, srv_id: int, request_id, request: Union[str, list[str]]) \
            -> Union[dict, list[dict], None]:
        """Get result for a request from service output queue. Same as _get_result but it is non blocking."""
        result = self.man.get_service_result_nowait(srv_id)
        if result is None:
            return None

        if result[0] == request_id:
            self.logger.debug(f"DatabaseManager: Result for request_id: {request_id}, "
                              f"service_id: {srv_id} found in ServiceManager.")
            if isinstance(result[1], list):
                outputs = []
                for request, output in zip(request, result[1]):
                    outputs.append(self._save_result(srv_id, request, output))
                return outputs
            else:
                return self._save_result(srv_id, request, result[1])
        else:
            self._save_tmp_result(srv_id, result)
            return None

    def _get_tmp_result(self, srv_id: int, request_id: int, request: Union[str, list[str]]) \
            -> Union[dict, list[dict], None]:
        """Get result for a request from service tmp queue. Before result is returned it is saved to the database."""
        tmp_q = self.tmp_results[srv_id]
        # tmp_q structure = ((iter_count, (req_id, output)), (iter_count, (req_id, output)), ...)
        tmp_result_list = []
        outputs = []
        # Get up to TMP_ITER results
        for _ in range(TMP_ITER):
            try:
                tmp_result = tmp_q.get_nowait()
                # tmp_result = (iter_count, (req_id, output))
            except queue.Empty:
                break
            tmp_result[0] += 1
            if tmp_result[0] >= 20:
                try:
                    req = self.request_dicts[srv_id][tmp_result[1][0]]
                    if isinstance(req, list):
                        for sub_req, out in zip(req, tmp_result[1][1]):
                            self._save_result(srv_id, sub_req, out)
                    else:
                        self._save_result(srv_id, req, tmp_result[1][1])
                except KeyError:
                    # This can sometimes occur. If multiple same requests comes at the same time. All (same) requests
                    # are put to srv input queue. Once first is finished all clients will use cached result instead of
                    # waiting for their result -> results will never be picked up. Result is lost because original
                    # request is not known at that point.
                    self.logger.debug(f"DatabaseManager: KeyError when trying to access request ID: "
                                      f"{tmp_result[1][0]}, in _get_tmp_result")
                continue
            if tmp_result[1][0] == request_id:
                if isinstance(tmp_result[1][1], list):
                    for req, out in zip(request, tmp_result[1][1]):
                        outputs.append(self._save_result(srv_id, req, out))
                else:
                    outputs.append(self._save_result(srv_id, request, tmp_result[1][1]))
                break
            else:
                tmp_result_list.append(tmp_result)
        for res in tmp_result_list:
            self.tmp_results[srv_id].put(res)
        if outputs:
            self.logger.debug(f"DatabaseManager: Result for request: {request}, "
                              f"service_id: {srv_id} found in tmp cache.")
            if len(outputs) == 1:
                return outputs[0]
            else:
                return outputs
        return None

    def _save_result(self, srv_id: int, request: str, result: dict) -> dict:
        """Save service result to database. Add timestamp and delete least accessed result if database is full.
        Return timestamped result."""
        srv_dict = self.service_outputs[srv_id]
        if len(srv_dict) >= self.config.max_database_size:
            srv_dict.popitem(last=False)
        new_result = {"timestamp": datetime.datetime.now(), "output": result}
        srv_dict[request] = new_result
        return new_result

    def _save_tmp_result(self, srv_id: int, result: tuple) -> None:
        """Append result to service tmp queue."""
        self.tmp_results[srv_id].put([0, result])

    @staticmethod
    def _parse_int(string_id: str) -> Union[int, None]:
        """Try to convert str to int."""
        try:
            return int(string_id)
        except ValueError:
            return None

    def _run_service(self, srv_id: int, request: Union[str, list[str]]) -> Union[None, int]:
        """Append request to service input queue. For internal purpose only. Does do request and srv_id validation"""
        req_id = self.man.run_service(srv_id, request)
        self.request_dicts[srv_id][req_id] = request
        return req_id

    def _run_service_quick(self, srv_id: int, request: Union[str, list[str]]) -> Optional[int]:
        """Append request to service input queue directly. For internal purpose only.
        Does not do request and srv_id validation!"""
        if not request:
            return None
        req_id = self.man.get_next_index()
        self.service_input_queues[srv_id].put((req_id, request))
        self.man.request_dicts[srv_id][req_id] = request
        self.request_dicts[srv_id][req_id] = request
        return req_id

    def _start_gb_collector(self) -> None:
        """Starts Garbage Collector thread."""
        if self.gb_collector is not None:
            self._stop_gb_collector()
        self.gb_collector = th.Thread(target=self._gb_collector, daemon=True, name="db_gb_collector")
        self.gb_collector.start()

    def _stop_gb_collector(self) -> None:
        """Stop/kill Garbage Collector thread."""
        if self.gb_collector is None:
            return
        self.garbage_queue.put(None)
        self.gb_collector.join(1)
        if self.gb_collector.is_alive():
            self.logger.warning(f"ServiceManager: Killing garbage collector")
            self._kill_thread("db_gb_collector")
        self.gb_collector = None

    def _kill_thread(self, thread_name: str) -> None:
        """Forcefully kill thread."""
        for thread in th.enumerate():
            if thread.name == thread_name:
                thread.join(self.config.th_proc_response_time)
                if not thread.is_alive():
                    return
                self.logger.info(f"DatabaseManager: Killing thread: {thread}")
                res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, ctypes.py_object(SystemExit))
                if res > 1:
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, 0)
                return

    def _gb_collector(self):
        """Thread for deleting processed requests. It will delete processed request. Also it will delete unprocessed
        request if they are pending for more then self.config.garbage_collector_timeout and are not pending in
         ServiceManager."""
        self.logger.debug("DatabaseManager: Garbage collector: started")
        pending_requests = [[] for _ in self.services]  # List for every service
        # There is infinite loop because _gb_collector is daemon. It will exit if main thread exited.
        while self.initialized:
            try:
                req = self.garbage_queue.get(timeout=self.config.max_service_run_time)
                # req = (service_id, request_id)
            except OSError:
                self.logger.error(f"DatabaseManager: Error while trying to get from garbage queue.")
                time.sleep(1)
                continue
            except _queue.Empty:
                # Delete request which are still pending and not pending in ServiceManager
                for srv_id, pending_request_list in enumerate(pending_requests):
                    to_delete = []
                    for pending_request_id in self.request_dicts[srv_id].keys():
                        # Delete request if it is pending for too long AND is not pending in ServiceManager
                        if pending_request_id in pending_request_list and\
                                self.man.is_pending(srv_id, pending_request_id) is False:
                            # This should never happen
                            to_delete.append(pending_request_id)
                    for req_id in to_delete:
                        try:
                            del self.request_dicts[srv_id][req_id]
                        except KeyError:
                            # This should never happen
                            self.logger.error(f"DatabaseManager: Key error when trying to delete pending "
                                              f"request ID: {req_id} of a service: {srv_id}.")
                        self.logger.warning(f"DatabaseManager: Request with ID: {req_id} was deleted because "
                                            f"it was not picked up for more then "
                                            f"{self.config.max_service_run_time} seconds")
                # Search for new pending requests
                for d_id, d in enumerate(self.request_dicts):
                    pending_requests[d_id].clear()
                    for req_id in d.keys():
                        pending_requests[d_id].append(req_id)
                continue  # continue while

            if req is None:
                continue
            if req[1] is None:
                continue
            try:
                self.logger.debug(f"DatabaseManager: Garbage collector: removing finished "
                                  f"request ID: {req[1]} of service: {req[0]}")
                del self.request_dicts[req[0]][req[1]]
            except KeyError:
                # This can happen (request processed by ServiceManager but result never picked up).
                # Or just invalid request ID
                self.logger.warning(f"DatabaseManager: Key error when trying to delete "
                                    f"request ID: {req[1]} of a service: {req[0]}. Ignoring.")

        self.logger.debug("DatabaseManager: Garbage collector: died")

    def is_pending(self, service_id: int, request_id: int) -> bool:
        if request_id in self.request_dicts[service_id]:
            return True
        return False

    def reload_tokens(self) -> bool:
        """This will reload tokens file in runtime. It will overwrite running tokens with saved tokens."""
        try:
            new_aman = utility.AuthManager(file_tokens=os.path.normpath(self.config.tokens_path),
                                           token_regex=self.config.token_regex,
                                           bypass_user=self.config.bypass_user_auth,
                                           bypass_admin=self.config.bypass_admin_auth)
        except utility.AuthManagerError as err:
            self.logger.error(f"DatabaseManager: Cannot load tokens from: {self.config.tokens_path} "
                              f"validation failed: {err}.")
            return False
        self.aman = new_aman
        self.logger.info(f"DatabaseManager: Tokens Successfully reloaded")
        return True

    def database_to_dict(self):
        """Returns dict with lengths of all queues and database."""
        output = {}

        input_queues_sizes = []
        for input_queue_index, input_queue in enumerate(self.service_input_queues):
            input_queues_sizes.append({input_queue_index: input_queue.qsize()})
        output["service_input_queues"] = input_queues_sizes

        output_queues_sizes = []
        for output_queue_index, output_queue in enumerate(self.service_output_queues):
            output_queues_sizes.append({output_queue_index: output_queue.qsize()})
        output["service_output_queues"] = output_queues_sizes

        tmp_queues_sizes = []
        for tmp_queues_index, tmp_queues in enumerate(self.tmp_results):
            tmp_queues_sizes.append({tmp_queues_index: tmp_queues.qsize()})
        output["tmp_queues"] = tmp_queues_sizes

        service_outputs_sizes = []
        for service_outputs_index, service_outputs in enumerate(self.service_outputs):
            service_outputs_sizes.append({service_outputs_index: len(service_outputs)})
        output["service_outputs"] = service_outputs_sizes
        requests_dicts_sizes = []
        for requests_dict_index, requests_dict in enumerate(self.request_dicts):
            requests_dicts_sizes.append({requests_dict_index: len(requests_dict)})
        output["pending"] = requests_dicts_sizes
        return output

    def server_info(self) -> dict:
        """Returns running info, static info, database stats. Does not require token."""
        return {"info": self.man.get_services_info(),
                "running": self.man.get_services_running_info(),
                "database": self.database_to_dict()}

    def server_version(self) -> dict:
        """Returns version of application."""
        return {"version": self.version}

    def services_info(self) -> list[tuple]:
        """Returns list of tuples with available services. Does not require token."""
        return self.man.get_services()

    def groups_info(self) -> list[tuple]:
        """Returns list of tuples with available groups. Does not require token."""
        return self.man.get_groups()

    # ============================================= API endpoints ======================================================
    def get_services_info(self, token: str) -> dict:
        """API Admin and User endpoint: Get dictionary of available services
        User will only see services, to which he/she is authorized.

              Args:
                  token (str): Authentication/Authorization token.

              Returns:
                  (dict): Dictionary of services {srv1_id: srv1_name, srv2_id: srv2_name, ...}
        """
        self.logger.info(f"{token}: get_services_info: Services requested")
        if self.aman.authorize_admin(token) is True or self.aman.authorize_superuser(token) is True:
            # Admin -> return everything -> keep on mind that admin may not have permissions to access these services
            # Only Users/Superusers can access services -> If you want admin to run services add him to Users/Superusers
            return dict([(key, value) for key, value in self.man.get_services()])
        # Token belongs to User or invalid
        # Empty dict {} will be return if 0 authorized services found
        output = {}
        service_list = self.man.get_services()
        # Service_list -> [(srv1_id, srv1_name), (), ...]
        for srv in service_list:
            if self.aman.authorize_user(token, srv[0]):
                output[srv[0]] = srv[1]
        return output

    def get_services_info_more(self, token: str) -> dict:
        """API Admin and User endpoint: Get dictionary of available services with additional info
        User will only see services, to which he/she is authorized.

              Args:
                  token (str): Authentication/Authorization token.

              Returns:
                  (dict): Dictionary of services {srv_id: [srv_name, srv_description, srv_groups], ...}
        """
        self.logger.info(f"{token}: get_services_info_more: Services requested")
        if self.aman.authorize_admin(token) is True or self.aman.authorize_superuser(token) is True:
            # Admin -> return everything -> keep on mind that admin may not have permissions to access these services
            # Only Users/Superusers can access services -> If you want admin to run services add him to Users/Superusers
            return dict([(srv[0], [srv[1], srv[2], srv[3]]) for srv in self.man.get_services_more()])
        # Token belongs to User or invalid
        # Empty dict {} will be return if 0 authorized services found
        output = {}
        service_list = self.man.get_services_more()
        # Service_list -> [(srv1_id, srv1_name, srv_description, srv_groups), (), ...]
        for srv in service_list:
            if self.aman.authorize_user(token, srv[0]):
                output[srv[0]] = [srv[1], srv[2], srv[3]]
        return output

    def get_groups_info(self, token: str) -> dict:
        """API Admin and User endpoint: Get dict of groups.
        Group will be shown only if user has permission to at least one service from that group.

        Args:
           token (str): Authentication/Authorization token.

        Returns:
           (dict): Dictionary of groups and services {group_name1: [srv1, srv2], group_name2: [srv3], ...}
        """
        self.logger.info(f"{token}: get_groups_info: Groups requested")
        if self.aman.authorize_admin(token) is True or self.aman.authorize_superuser(token) is True:
            # Admin -> same as get_services_info, admin has only "read" permissions
            return dict([(key, value) for key, value in self.man.get_groups()])
        authorized_groups = {}
        for key, value in self.man.get_groups():
            # key -> group_name, value -> [srv1, srv2, ...]
            authorized_services = []
            for srv in value:
                # srv -> (srv_id, srv_name)
                if self.aman.authorize_user(token, srv[0]):
                    authorized_services.append(srv)
            # Append group name only if authorized services are not empty
            if len(authorized_services) > 0:
                authorized_groups[key] = authorized_services
        return authorized_groups

    def get_tokens_info(self, token: str) -> dict:
        """API Admin endpoint: Get dict of tokens.

       Args:
           token (str): Authentication/Authorization token.

       Returns:
           (dict): Dictionary of running configuration of tokens.
       """
        if self.aman.authorize_admin(token) is False:
            self.logger.info(f"{token}: get_tokens_info: Insufficient permissions")
            return {"server": "Insufficient permissions"}
        self.logger.info(f"{token}: get_tokens_info: Tokens requested")
        return self.aman.get_dict_tokens()

    def get_server_info(self, token: str) -> dict:
        """API Admin endpoint: Get dict of static info, running info, database info.

       Args:
           token (str): Authentication/Authorization token.

       Returns:
           (dict): Dictionary with static info, running info, database info.
       """
        if self.aman.authorize_admin(token) is False:
            self.logger.info(f"{token}: get_server_info: Insufficient permissions")
            return {"server": "Insufficient permissions"}
        self.logger.info(f"{token}: get_server_info: Server info requested")
        return self.server_info()

    def get_server_version(self, token: str) -> dict:
        """API Admin and User endpoint: Get version of application.

       Args:
          token (str): Authentication/Authorization token.

       Returns:
          (dict): Dictionary with current version.
       """
        # If token is either user/superuser/admin
        if self.aman.exist(token) is False:
            self.logger.info(f"{token}: get_server_version: Insufficient permissions")
            return {"server": "Insufficient permissions"}
        self.logger.info(f"{token}: get_server_version: Version requested")
        return self.server_version()

    def put_tokens(self, new_tokens: dict, token: str) -> dict:
        """API Admin endpoint: Update/Add to tokens.

        Args:
            new_tokens (dict): Dictionary with same structure as tokens (see pydantic TokensModel in api.py), provided keys will added or updated.
            token (str): Authentication/Authorization token.

        Returns:
            (dict): Dictionary with status message.
        """
        if self.aman.authorize_admin(token) is False:
            self.logger.info(f"{token}: put_tokens: Insufficient permissions")
            return {"server": "Insufficient permissions"}
        if self.config.disable_config_endpoints is True:
            self.logger.warning(f"{token}: put_tokens: Configuration via API is disabled")
            return {"server": "Configuration via API is disabled"}
        if all(new_tokens[key] == "" or new_tokens[key] == [] for key in [tok_key for tok_key in new_tokens]):
            self.logger.info(f"{token}: put_tokens: Nothing provided")
            return {"server": "Nothing provided"}
        output = {"server": "OK"}
        if new_tokens.get("group"):
            if self.aman.add_group(new_tokens.get("group"), new_tokens.get("group_services")) is True:
                output["group"] = "Group successfully added"
            else:
                output["server"] = "ERROR"
                output["superuser"] = "Error in group addition. Group name cannot be a number " \
                                      "and group services can contain only numbers (Service IDs)."
        if new_tokens.get("user"):
            if self.aman.add_user(new_tokens.get("user"), new_tokens.get("user_services")) is True:
                output["user"] = "User successfully added"
            else:
                output["server"] = "ERROR"
                output["user"] = "Error in user addition. Make sure that token has valid format and user services " \
                                 "contain only numbers (Service IDs) or existing groups."
        if new_tokens.get("superuser"):
            if self.aman.add_superuser(new_tokens.get("superuser")) is True:
                output["group"] = "Superuser successfully added"
            else:
                output["server"] = "ERROR"
                output["superuser"] = "Error in superuser addition. Make sure that token has valid format."
        if new_tokens.get("admin"):
            if self.aman.add_admin(new_tokens.get("admin")) is True:
                output["admin"] = "Admin successfully added"
            else:
                output["server"] = "ERROR"
                output["admin"] = "Error in admin addition. Make sure that token has valid format."

        if output["server"] == "ERROR":
            output["info"] = "Any changes in keys containing errors will not be saved."

        difference = self.aman.get_config_diff(os.path.normpath(self.config.tokens_path))
        if len(difference) == 0:
            output["server"] = "ERROR"
            output["message"] = "Nothing was changed"
            return output

        if self.aman.save_tokens(os.path.normpath(self.config.tokens_path), self.config.tokens_backups) is False:
            output["server"] = "ERROR"
            output["message"] = "Error occurred while saving tokens. Any changes will be lost on reload."
            self.logger.error(f"{token}: put_tokens: Error while trying to save tokens")
        output["changes"] = difference
        self.logger.info(f"{token}: put_tokens: Tokens edited")
        return output

    def del_tokens(self, to_delete: dict, token: str) -> dict:
        """API Admin endpoint: Delete from tokens.

        Args:
            to_delete (dict): Dictionary with same structure as tokens (see pydantic TokensModel in api.py), provided keys will be deleted.
            token (str): Authentication/Authorization token.

        Returns:
            (dict): Dictionary with status message.
        """
        if self.aman.authorize_admin(token) is False:
            self.logger.info(f"{token}: del_tokens: Insufficient permissions")
            return {"server": "Insufficient permissions"}
        if self.config.disable_config_endpoints is True:
            self.logger.warning(f"{token}: del_tokens: Configuration via API is disabled")
            return {"server": "Configuration via API is disabled"}
        if all(to_delete[key] == "" or to_delete[key] == [] for key in [tok_key for tok_key in to_delete]):
            self.logger.info(f"{token}: del_tokens: Nothing provided")
            return {"server": "Nothing provided"}
        output = {"server": "OK"}
        if to_delete.get("group"):
            if self.aman.remove_group(to_delete.get("group")) is True:
                output["group"] = "Group successfully removed"
            else:
                output["server"] = "ERROR"
                output["superuser"] = "Error in group removal. Make sure you are not trying to delete group which is " \
                                      "assigned to a user. Remove group from the user/s first."
        if to_delete.get("user"):
            if self.aman.remove_user(to_delete.get("user")) is True:
                output["user"] = "User successfully removed"
            else:
                output["server"] = "ERROR"
                output["user"] = "Error in user removal"
        if to_delete.get("superuser"):
            if self.aman.remove_superuser(to_delete.get("superuser")) is True:
                output["group"] = "Superuser successfully removed"
            else:
                output["server"] = "ERROR"
                output["superuser"] = "Error in superuser removal"
        if to_delete.get("admin"):
            if self.aman.remove_admin(to_delete.get("admin")) is True:
                output["admin"] = "Admin successfully removed"
            else:
                output["server"] = "ERROR"
                output["admin"] = "Error in admin removal"

        difference = self.aman.get_config_diff(os.path.normpath(self.config.tokens_path))
        if difference is None:
            self.logger.error(f"{token}: del_tokens: Error while reading tokens file")
            output["server"] = "ERROR"
            output["message"] = "Error occurred while saving tokens. Any changes will be lost on reload."
            return output
        if len(difference) == 0:
            output["server"] = "ERROR"
            output["message"] = "Nothing was changed"
            return output

        if not self.aman.save_tokens(os.path.normpath(self.config.tokens_path), self.config.tokens_backups):
            output["server"] = "ERROR"
            output["message"] = "Error occurred while saving tokens. Any changes will be lost on reload."
        output["changes"] = difference
        self.logger.info(f"{token}: del_tokens: Tokens edited")
        return output

    def get_start(self, token) -> dict:
        """API Admin endpoint: Start services (if they are not running).

        Args:
            token (str): Authentication/Authorization token.

        Returns:
            (dict): Dictionary with status message.
        """
        if self.aman.authorize_admin(token) is False:
            self.logger.info(f"{token}: get_start: Insufficient permissions")
            return {"server": "Insufficient permissions"}
        if self.config.disable_config_endpoints is True:
            self.logger.warning(f"{token}: get_start: Configuration via API is disabled")
            return {"server": "Configuration via API is disabled"}
        if self.start_services():
            self.logger.info(f"{token}: get_start: Services started")
            return {"server": "Services started"}
        else:
            self.logger.info(f"{token}: get_start: Services already running")
            return {"server": "Services already running"}

    def get_stop(self, token) -> dict:
        """API Admin endpoint: Stop services.

        Args:
            token (str): Authentication/Authorization token.

        Returns:
            (dict): Dictionary with status message.
        """
        if self.aman.authorize_admin(token) is False:
            self.logger.info(f"{token}: get_stop: Insufficient permissions")
            return {"server": "Insufficient permissions"}
        if self.config.disable_config_endpoints is True:
            self.logger.warning(f"{token}: get_stop: Configuration via API is disabled")
            return {"server": "Configuration via API is disabled"}
        if self.stop_services():
            self.logger.info(f"{token}: get_stop: Services stopped")
            return {"server": "Services stopped"}
        else:
            self.logger.info(f"{token}: get_stop: Services already stopped")
            return {"server": "Services already stopped"}

    def get_restart(self, token: str) -> dict:
        """API Admin endpoint: Restart services.

        Args:
            token (str): Authentication/Authorization token.

        Returns:
            (dict): Dictionary with status message.
        """
        if self.aman.authorize_admin(token) is False:
            self.logger.info(f"{token}: get_restart: Insufficient permissions")
            return {"server": "Insufficient permissions"}
        if self.config.disable_config_endpoints is True:
            self.logger.warning(f" {token}: get_restart: Configuration via API is disabled")
            return {"server": "Configuration via API is disabled"}
        if self.restart_services():
            self.logger.info(f"{token}: get_restart: Services restarted")
            return {"server": "Services restarted"}
        else:
            return {"server": "Cannot occur"}

    def get_reload_tokens(self, token: str) -> dict:
        """API Admin endpoint: Reload tokens file.

        Args:
            token (str): Authentication/Authorization token.

        Returns:
            (dict): Dictionary with status message.
        """
        if self.aman.authorize_admin(token) is False:
            self.logger.info(f"{token}: get_reload_tokens: Insufficient permissions")
            return {"server": "Insufficient permissions"}
        if self.config.disable_config_endpoints is True:
            self.logger.warning(f"{token}: get_reload_tokens: Configuration via API is disabled")
            return {"server": "Configuration via API is disabled"}
        if self.reload_tokens():
            self.logger.info(f"{token}: get_reload_tokens: Tokens reloaded")
            return {"server": "Tokens Successfully reloaded"}
        else:
            self.logger.info(f"{token}: get_reload_tokens: Error while reloading tokens")
            return {"server": "Tokens did not reloaded. Using old tokens."}

    def get_service(self, service_id: Union[str, int], request: str, token: str, caching: bool = True) -> dict:
        """API User endpoint: Get service result by service_id.

        Args:
            service_id (str | int): ID of a service that should be run.
            request (str): Request that a service should process.
            token (str): Authentication/Authorization token.
            caching (bool): Allow cached results (Return cached result if present)

        Returns:
            output_dict (dict): Dictionary with service output or error message.
        """
        timer = utility.Timer()
        timer.start()
        error = {"server": {"state": "ERROR", "input": request, "service": service_id, "message": ""}}
        if self.running is False:
            self.logger.info(f"{token}: get_service: Server is not running "
                             f"service_id: {service_id} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_service: Server is not running "
                              f"service_id: {service_id} caching: {caching} request: {request}")
            error["server"]["message"] = "Server is not running"
            return error
        if self.man.validate_request(request) is False:
            self.logger.info(f"{token}: get_service: Request validation failed "
                             f"service_id: {service_id} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_service: Request validation failed "
                              f"service_id: {service_id} caching: {caching} request: {request}")
            error["server"]["message"] = "Request validation failed"
            return error
        service_id = self._parse_int(service_id)
        if service_id is None:
            self.logger.info(f"{token}: get_service: Invalid service ID "
                             f"service_id: {service_id} [{timer.stop():.2f}]")
            self.logger.debug(f"{token}: get_service: Invalid service ID "
                              f"service_id: {service_id} caching: {caching} request: {request}")
            error["server"]["message"] = "service_id must be integer"
            return error
        if not any(srv[0] == service_id for srv in self.services):
            self.logger.info(f"{token}: get_service: Invalid service ID "
                             f"service_id: {service_id} [{timer.stop():.2f}]")
            self.logger.debug(f"{token}: get_service: Invalid service ID "
                              f"service_id: {service_id} caching: {caching} request: {request}")
            error["server"]["message"] = "Invalid service_id"
            return error
        # Authorize user
        if not self.aman.authorize_user(token, service_id):
            self.logger.info(f"{token}: get_service: Insufficient permissions "
                             f"service_id: {service_id} [{timer.stop():.2f}]")
            self.logger.debug(f"{token}: get_service: Insufficient permissions "
                              f"service_id: {service_id} caching: {caching} request: {request}")
            error["server"]["message"] = "Insufficient permissions"
            return error
        self.logger.info(f"{token}: get_service: Incoming request service_id: {service_id}")
        self.logger.debug(f"{token}: get_service: Incoming request "
                          f"service_id: {service_id} caching: {caching} request: {request}")

        srv = self.services[service_id]
        # Service ID => srv[0], Service name => srv[1]
        output_dict = {"server": {"state": "OK", "input": request, "service_id": srv[0], "service_name": srv[1]}}
        if caching:
            database_result = self._get_database_result(srv[0], request)
        else:
            database_result = None
        if database_result:
            output_dict[self.services[srv[0]][1]] = database_result
            self.logger.debug(f"{token}: get_service: Request done time: {timer.stop():.2f} "
                              f"service_id: {srv[0]} caching: {caching} request: {request}")
            output_dict["server"]["response"] = round(timer.last_time, 3)
            return output_dict
        else:
            req_id = self._run_service_quick(srv[0], request)

        iter_count = 0
        timeout_count = 0
        while True:
            database_result = self._get_database_result(srv[0], request)  # Non-blocking
            if database_result:
                output_dict[srv[1]] = database_result
                break

            tmp_result = self._get_tmp_result(srv[0], req_id, request)  # Non-blocking
            if tmp_result:
                output_dict[srv[1]] = tmp_result
                break

            srv_result = self._get_result(srv[0], req_id, request)  # Blocking
            if srv_result:
                output_dict[srv[1]] = srv_result
                break

            # Periodically check if request is still being processed if not then exit
            iter_count += 1
            if iter_count >= GET_ITER:
                # This will execute every circa GET_ITER*GET_TIMEOUT e.g. 200*0.01 = 2s
                iter_count = 0
                keep_on = False
                if self.is_pending(srv[0], req_id) is True:
                    keep_on = True
                if keep_on is False:
                    output_dict["server"]["state"] = "ERROR"
                    output_dict["server"]["message"] = "Result is incomplete. " \
                                                       "Some service did not process request in time"
                    self.logger.error(f"{token}: get_service: Request returned incomplete due to no "
                                      f"longer pending request_id: {req_id} "
                                      f"service_id: {srv[0]} caching: {caching} request: {request}")
                    break
                if timeout_count >= 30:
                    time.sleep(0.5)  # Total wait time more then 30*2s = 60s
                else:
                    time.sleep(timeout_count * 1.5 * GET_TIMEOUT)  # Max 29*1.7*0.01 = 0.493 s

        self.logger.debug(f"{token}: get_service: Request done time: {timer.stop():.2f} "
                          f"service_id: {srv[0]} caching: {caching} request: {request}")
        self.garbage_queue.put((srv[0], req_id))
        output_dict["server"]["response"] = round(timer.last_time, 3)
        return output_dict

    def get_group(self, group_name: str, request: str, token: str, caching: bool = True) -> dict:
        """API User endpoint: Get service results by group_name.

        Args:
            group_name (str): Name of group of services that should be run.
            request (str): Request that a services should process.
            token (str): Authentication/Authorization token.
            caching (bool): Allow cached results (Return cached result if present)

        Returns:
            output_dict (dict): Dictionary with service outputs or error message.
        """
        timer = utility.Timer()
        timer.start()
        error = {"server": {"state": "ERROR", "input": request, "group": group_name, "message": ""}}
        if self.running is False:
            self.logger.info(f"{token}: get_group: Server is not running "
                             f"group: {group_name} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_group: Server not running "
                              f"group: {group_name} caching: {caching} request: {request}")
            error["server"]["message"] = "Server is not running"
            return error
        if self._parse_int(group_name) is not None:
            # Accept string numbers as service_id -> redirect to get_service
            timer.stop()
            return self.get_service(group_name, request, token, caching)
        if self.man.validate_request(request) is False:
            self.logger.info(f"{token}: get_group: Request validation failed "
                             f"group: {group_name} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_group: Request validation failed "
                              f"group: {group_name} caching: {caching} request: {request}")
            error["server"]["message"] = "Request validation failed"
            return error
        # Includes group_name validation
        group_services = self.man.get_group_services(group_name, self.config.key_sensitivity)
        if not group_services:
            self.logger.info(f"{token}: get_group: Invalid group name "
                             f"group: {group_name} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_group: Invalid group name "
                              f"group: {group_name} caching: {caching} request: {request}")
            error["server"]["message"] = f"Group name \'{group_name}\' is not implemented or is invalid"
            return error
        # Authorize user / Remove unauthorized services
        authorized_services = self.aman.get_user_authorized(token, [srv[0] for srv in group_services])
        group_services = [srv for srv in group_services if srv[0] in authorized_services]
        if not group_services:
            self.logger.info(f"{token}: get_group: Insufficient permissions "
                             f"group: {group_name} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_group: Insufficient permissions "
                              f"group: {group_name} caching: {caching} request: {request}")
            error["server"]["message"] = "Insufficient permissions"
            return error
        self.logger.info(f"{token}: get_group: Incoming request group: {group_name}")
        self.logger.debug(f"{token}: get_group: Incoming request "
                          f"group: {group_name} caching: {caching} request: {request}")

        output_dict = {"server": {"state": "OK", "input": request, "group": group_name,
                                  "service_ids": [srv[0] for srv in group_services],
                                  "service_names": [srv[1] for srv in group_services]}}
        srv_done = []
        srv_map = {}  # Maps srv_id -> req_id
        num_services = 0
        num_done_services = 0
        for srv in group_services:
            # Service ID => srv[0], Service name => srv[1]
            num_services += 1
            if caching:
                database_result = self._get_database_result(srv[0], request)
            else:
                database_result = None
            if database_result:
                output_dict[srv[1]] = database_result
                srv_done.append(True)
                num_done_services += 1
            else:
                req_id = self._run_service_quick(srv[0], request)
                srv_map[srv[0]] = req_id
                srv_done.append(False)

        iter_count = 0
        timeout_count = 0
        while num_done_services < num_services:

            for done_id, srv in enumerate(group_services):
                # Service ID => srv[0], Service name => srv[1]
                if srv_done[done_id] is True:
                    continue

                database_result = self._get_database_result(srv[0], request)  # Non-blocking
                if database_result:
                    output_dict[srv[1]] = database_result
                    srv_done[done_id] = True
                    num_done_services += 1
                    self.garbage_queue.put((srv[0], srv_map[srv[0]]))
                    continue

                tmp_result = self._get_tmp_result(srv[0], srv_map[srv[0]], request)  # Non-blocking
                if tmp_result:
                    output_dict[srv[1]] = tmp_result
                    srv_done[done_id] = True
                    num_done_services += 1
                    self.garbage_queue.put((srv[0], srv_map[srv[0]]))
                    continue

                srv_result = self._get_result(srv[0], srv_map[srv[0]], request)  # Blocking
                if srv_result:
                    output_dict[srv[1]] = srv_result
                    srv_done[done_id] = True
                    num_done_services += 1
                    self.garbage_queue.put((srv[0], srv_map[srv[0]]))
                    continue

            # Periodically check if request is still being processed if not then exit
            iter_count += 1
            if iter_count >= GET_ITER:
                # This will execute every circa GET_ITER*GET_TIMEOUT e.g. 200*0.01 = 2s
                iter_count = 0
                keep_on = False
                for done_id, srv in enumerate(group_services):
                    if srv_done[done_id] is True:
                        continue
                    if self.is_pending(srv[0], srv_map[srv[0]]) is True:
                        keep_on = True
                if keep_on is False:
                    output_dict["server"]["state"] = "ERROR"
                    output_dict["server"]["message"] = "Result is incomplete. " \
                                                       "Some service did not process request in time"
                    self.logger.error(f"{token}: get_group: Request returned incomplete due to no longer pending "
                                      f"group: {group_name} caching: {caching} request: {request}")
                    break
                if timeout_count >= 30:
                    time.sleep(0.5)  # Total wait time more then 30*2s = 60s
                else:
                    time.sleep(timeout_count*1.5*GET_TIMEOUT)  # Max 29*1.7*0.01 = 0.493 s

        self.logger.debug(f"{token}: get_group: Request done time: {timer.stop():.2f} "
                          f"group: {group_name} caching: {caching} request: {request}")
        output_dict["server"]["response"] = round(timer.last_time, 3)
        return output_dict

    def get_service_list(self, service_id: Union[str, int], requests: list[str],
                         token: str, caching: bool = True) -> dict:
        """API User endpoint: Get service results for multiple requests.

        Args:
            service_id (str | int): ID of a service that should be run.
            requests (list): List of requests that service should process.
            token (str): Authentication/Authorization token.
            caching (bool): Allow cached results (Return cached results if present)

        Returns:
            output_dict (dict): Dictionary with service outputs or error message.
        """
        timer = utility.Timer()
        timer.start()
        error = {"server": {"state": "ERROR", "input": requests, "service": service_id, "message": ""}}
        if self.running is False:
            self.logger.info(f"{token}: get_service_list: Server is not running "
                             f"service_id: {service_id} num_requests: {len(requests)} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_service_list: Server is not running "
                              f"service_id: {service_id} num_requests: {len(requests)} requests: {requests}")
            error["server"]["message"] = "Server is not running"
            return error
        service_id = self._parse_int(service_id)
        if service_id is None:
            self.logger.info(f"{token}: get_service_list: Invalid service ID "
                             f"service_id: {service_id} num_requests: {len(requests)} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_service_list: Invalid service ID "
                              f"service_id: {service_id} num_requests: {len(requests)} requests: {requests}")
            error["server"]["message"] = "service_id must be integer"
            return error
        if not any(srv[0] == service_id for srv in self.services):
            self.logger.info(f"{token}: get_service_list: Invalid service ID "
                             f"service_id: {service_id} num_requests: {len(requests)} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_service_list: Invalid service ID "
                              f"service_id: {service_id} num_requests: {len(requests)} requests: {requests}")
            error["server"]["message"] = "Invalid service_id"
            return error
        # Authorize user
        if not self.aman.authorize_user(token, service_id):
            self.logger.info(f"{token}: get_service_list: Insufficient permissions "
                             f"service_id: {service_id} num_requests: {len(requests)} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_service_list: Insufficient permissions "
                              f"service_id: {service_id} num_requests: {len(requests)} requests: {requests}")
            error["server"]["message"] = "Insufficient permissions"
            return error
        # Validate requests, deduplicate
        unique_requests = []  # List of unique requests from requests, subset of requests
        dup_map = {}  # Mapping unique to duplicate requests
        for request_index, request in enumerate(requests):
            if self.man.validate_request(request) is False:
                self.logger.info(f"{token}: get_service_list: Request validation failed "
                                 f"service_id: {service_id} num_requests: {len(requests)} time: {timer.stop():.2f}")
                self.logger.debug(f"{token}: get_service_list: Request validation failed "
                                  f"service_id: {service_id} num_requests: {len(requests)} requests: {requests}")
                error["server"]["message"] = "Request validation failed"
                return error
            if request not in unique_requests:
                # Append unique request
                unique_requests.append(request)
                dup_map[request_index] = len(unique_requests) - 1
            else:
                # Append index of duplicate request
                dup_map[request_index] = unique_requests.index(request)
        self.logger.info(f"DatabaseManager: {token}: get_service_list: Incoming request "
                         f"service_id: {service_id} num_requests: {len(requests)}")
        self.logger.debug(f"DatabaseManager: {token}: get_service_list: Incoming request "
                          f"service_id: {service_id} num_requests: {len(requests)} requests: {requests}")
        response = [None] * len(requests)  # List of responses, same length as requests
        to_request = []  # Unique request not in database -> need to be run, to_request <= unique_request <= requests
        unique_responses = []  # Same length as unique_request, contains responses (None if not present)
        srv = self.services[service_id]
        # Service ID => srv[0], Service name => srv[1]
        for unique_request_id, unique_request in enumerate(unique_requests):
            if caching:
                unique_responses.append(self._get_database_result(srv[0], unique_request))
            else:
                unique_responses.append(None)
            if unique_responses[unique_request_id] is None:
                to_request.append(unique_request)
        req_id = self._run_service_quick(srv[0], to_request)
        output_dict = {"server": {"state": "OK", "input": requests, "service_id": srv[0], "service_name": srv[1]}}
        iter_count = 0
        timeout_count = 0
        results = []
        # Valid req_id is always > 0
        while req_id:
            tmp_result = self._get_tmp_result(srv[0], req_id, to_request)  # Non-blocking
            if tmp_result:
                results = tmp_result
                break

            srv_result = self._get_result(srv[0], req_id, to_request)  # Blocking
            if srv_result:
                results = srv_result
                break

            # Periodically check if request is still being processed if not then exit
            iter_count += 1
            if iter_count >= GET_ITER:
                # This will execute every circa GET_ITER*GET_TIMEOUT e.g. 200*0.01 = 2s
                iter_count = 0
                keep_on = False
                if self.is_pending(srv[0], req_id) is True:
                    keep_on = True
                if keep_on is False:
                    output_dict["server"]["state"] = "ERROR"
                    output_dict["server"]["message"] = "Results are incomplete. " \
                                                       "Some service did not process requests in time"
                    self.logger.error(f"{token}: get_service_list: Request returned incomplete due to no "
                                      f"longer pending request_id: {req_id} "
                                      f"service_id: {srv[0]} num_requests: {len(requests)} requests: {requests}")
                    break
                if timeout_count >= 30:
                    time.sleep(0.5)  # Total wait time more then 30*2s = 60s
                else:
                    time.sleep(timeout_count*1.5*GET_TIMEOUT)  # Max 29*1.7*0.01 = 0.493 s
        # Map results back to original (duplicate) requests/responses
        db_counter = 0
        for resp_id, _ in enumerate(response):
            try:
                if unique_responses[dup_map[resp_id]] is None:
                    # Db result is None -> Therefore it must be in results at index db_counter
                    # Copy result to unique_responses at index dup_map[resp_id]
                    unique_responses[dup_map[resp_id]] = results[db_counter]
                    db_counter += 1
            except IndexError:
                # Should never occur
                self.logger.error(f"{token}: get_service_list: Index error while getting response request_id: {req_id} "
                                  f"service_id: {srv[0]} num_requests: {len(requests)} requests: {requests}")
            response[resp_id] = unique_responses[dup_map[resp_id]]
        output_dict[srv[1]] = response
        self.logger.debug(f"{token}: get_service_list: Request done time: {timer.stop():.2f} "
                          f"service_id: {srv[0]} num_requests: {len(requests)} requests: {requests}")
        self.garbage_queue.put((srv[0], req_id))
        output_dict["server"]["response"] = round(timer.last_time, 3)
        return output_dict

    def get_group_list(self, group_name: str, requests: list[str], token: str, caching: bool = True) -> dict:
        """Beta. Currently does not allow caching.
        API User endpoint: Get service results by group_name for multiple requests.

        Args:
            group_name (str): Name of group of services that should be run.
            requests (list): List of requests that should services process.
            token (str): Authentication/Authorization token.
            caching (bool): Allow cached results (Return cached results if present)

        Returns:
            output_dict (dict): Dictionary with service outputs or error message.
        """
        timer = utility.Timer()
        timer.start()
        error = {"server": {"state": "ERROR", "input": requests, "group": group_name, "message": ""}}
        if self.running is False:
            self.logger.info(f"{token}: get_group_list: Server is not running "
                             f"group: {group_name} num_requests: {len(requests)} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_group_list: Server is not running "
                              f"group: {group_name} num_requests: {len(requests)} requests: {requests}")
            error["server"]["message"] = "Server is not running"
            return error
        if self._parse_int(group_name) is not None:
            # Accept string numbers as service_id -> redirect to get_service_list
            timer.stop()
            return self.get_service_list(group_name, requests, token)
        group_services = self.man.get_group_services(group_name, self.config.key_sensitivity)
        if not group_services:
            self.logger.info(f"{token}: get_group_list: Invalid group name "
                             f"group: {group_name} num_requests: {len(requests)} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_group_list: Invalid group name "
                              f"group: {group_name} num_requests: {len(requests)} requests: {requests}")
            error["server"]["message"] = f"Group name \'{group_name}\' is not implemented or is invalid"
            return error
        # Authorize user / Remove unauthorized services
        authorized_services = self.aman.get_user_authorized(token, [srv[0] for srv in group_services])
        group_services = [srv for srv in group_services if srv[0] in authorized_services]
        if not group_services:
            self.logger.info(f"{token}: get_group_list: Insufficient permissions "
                             f"group: {group_name} num_requests: {len(requests)} time: {timer.stop():.2f}")
            self.logger.debug(f"{token}: get_group_list: Insufficient permissions "
                              f"group: {group_name} num_requests: {len(requests)} requests: {requests}")
            error["server"]["message"] = "Insufficient permissions"
            return error
        # Validate requests, deduplicate
        unique_requests = []  # List of unique requests from requests, subset of requests
        response = [[None] * len(requests) for _ in group_services]  # List of responses, same length as requests
        dup_map = {}  # Mapping unique to duplicate request
        for request_index, request in enumerate(requests):
            if self.man.validate_request(request) is False:
                self.logger.info(f"{token}: get_group_list: Request validation failed "
                                 f"group: {group_name} num_requests: {len(requests)} time: {timer.stop():.2f}")
                self.logger.debug(f"{token}: get_group_list: Request validation failed "
                                  f"group: {group_name} num_requests: {len(requests)} requests: {requests}")
                error["server"]["message"] = "Request validation failed"
                return error
            if request not in unique_requests:
                # Append unique request
                unique_requests.append(request)
                dup_map[request_index] = len(unique_requests) - 1
            else:
                # Append index of duplicate request
                dup_map[request_index] = unique_requests.index(request)
        self.logger.info(f"{token}: get_group_list: Incoming request "
                         f"group: {group_name} num_requests: {len(requests)}")
        self.logger.debug(f"{token}: get_group_list: Incoming request "
                          f"group: {group_name} num_requests: {len(requests)} requests: {requests}")

        output_dict = {"server": {"state": "OK", "input": requests, "group": group_name,
                                  "service_ids": [srv[0] for srv in group_services],
                                  "service_names": [srv[1] for srv in group_services]}}
        srv_done = []
        srv_map = {}  # Maps srv_id -> req_id
        num_services = 0
        num_done_services = 0
        to_request = [[] for _ in group_services]  # Unique request not in database
        unique_responses = [[] for _ in group_services]  # Same length as unique_request, contains responses
        for done_id, srv in enumerate(group_services):
            # Service ID => srv[0], Service name => srv[1]
            for unique_request_id, unique_request in enumerate(unique_requests):
                if caching:
                    unique_responses[done_id].append(self._get_database_result(srv[0], unique_request))
                else:
                    unique_responses[done_id].append(None)
                if unique_responses[done_id][unique_request_id] is None:
                    to_request[done_id].append(unique_request)
            num_services += 1
            req_id = self._run_service_quick(srv[0], to_request[done_id])
            if not req_id:
                srv_done.append(True)
                num_done_services += 1
                continue
            srv_map[srv[0]] = req_id
            srv_done.append(False)

        iter_count = 0
        timeout_count = 0
        results = [[] for _ in group_services]
        while num_done_services < num_services:

            for done_id, srv in enumerate(group_services):
                # Service ID => srv[0], Service name => srv[1]
                if srv_done[done_id] is True:
                    continue

                tmp_result = self._get_tmp_result(srv[0], srv_map[srv[0]], to_request[done_id])  # Non-blocking
                if tmp_result:
                    results[done_id] = tmp_result
                    srv_done[done_id] = True
                    num_done_services += 1
                    continue

                srv_result = self._get_result(srv[0], srv_map[srv[0]], to_request[done_id])  # Blocking
                if srv_result:
                    results[done_id] = srv_result
                    srv_done[done_id] = True
                    num_done_services += 1
                    continue

            # Periodically check if request is still being processed if not then exit
            iter_count += 1
            if iter_count >= GET_ITER:
                # This will execute every circa GET_ITER*GET_TIMEOUT e.g. 200*0.01 = 2s
                iter_count = 0
                keep_on = False
                for done_id, srv in enumerate(group_services):
                    if srv_done[done_id] is True:
                        continue
                    if self.is_pending(srv[0], srv_map[srv[0]]) is True:
                        keep_on = True
                if keep_on is False:
                    output_dict["server"]["state"] = "ERROR"
                    output_dict["server"]["message"] = "Results are incomplete. " \
                                                       "Some service did not process requests in time"
                    self.logger.error(f"{token}: get_group_list: Request returned incomplete due to no longer pending "
                                      f"group: {group_name} num_requests: {len(requests)} requests: {requests}")
                    break
                if timeout_count >= 30:
                    time.sleep(0.5)  # Total wait time more then 30*2s = 60s
                else:
                    time.sleep(timeout_count*1.5*GET_TIMEOUT)  # Max 29*1.7*0.01 = 0.493 s
        # Map results back to original (duplicate) requests/responses
        for done_id, srv in enumerate(group_services):
            db_counter = 0
            for resp_id, _ in enumerate(response[done_id]):
                try:
                    if unique_responses[done_id][dup_map[resp_id]] is None:
                        # Db result is None -> Therefore it must be in results at index db_counter
                        # Copy result to unique_responses at index dup_map[resp_id]
                        unique_responses[done_id][dup_map[resp_id]] = results[done_id][db_counter]
                        db_counter += 1
                except IndexError:
                    # Should never occur
                    self.logger.error(
                        f"{token}: get_group_list: Index error while getting response resp_id: {resp_id} "
                        f"service_id: {srv[0]} num_requests: {len(requests)} requests: {requests}")
                response[done_id][resp_id] = unique_responses[done_id][dup_map[resp_id]]
            output_dict[srv[1]] = response[done_id]
        for srv_id, req_id in srv_map.items():
            self.garbage_queue.put((srv_id, req_id))
        self.logger.debug(f"{token}: get_group_list: Request done time: {timer.stop():.2f} "
                          f"group: {group_name} num_requests: {len(requests)} requests: {requests}")
        output_dict["server"]["response"] = round(timer.last_time, 3)
        return output_dict
