# manager.py requires Python3.9 standard library
import _queue
import datetime
import multiprocessing as mp
import os
import sys
import threading as th
import time
import queue
import ctypes
import importlib
import functools
from typing import Union, Optional, Callable

import utility

CACHE_SIZE = 16  # Should be greater or equal then the number of services


class ServiceManager:
    def __init__(self, config: Optional[utility.Config] = None, mp_logger: Optional[utility.MPLogger] = None):
        # Load config
        if isinstance(config, utility.Config):
            if config.validate() is False:
                raise utility.ConfigError("Invalid config")
            self.config = config  # Custom config
        else:
            self.config = utility.Config()  # Default config
        # Add included directories into paths
        for directory in self.config.include_dirs:
            if not os.path.exists(os.path.normpath(directory)):
                raise utility.ConfigError(f"Include directory: {directory} does not exit")
            sys.path.insert(0, os.path.normpath(directory))
        # Initialize logger
        if self.config.shared_logger is True and mp_logger is None:
            # mp logging cannot be stopped. DatabaseManager might be left hanging
            raise utility.ConfigError(f"ServiceManager: No logger provided while shared_logger = True.")
        if self.config.shared_logger is True:
            self.logger = mp_logger
            self.logger.debug("ServiceManager: Using shared logger")
        if self.config.shared_logger is False:
            self.logger = utility.MPLogger(name=self.config.man_logger_name,
                                           level=self.config.man_logger_level,
                                           file_name=self.config.man_logger_filename,
                                           syslog_address=self.config.man_logger_syslog_address)
            self.logger.debug("ServiceManager: Logger created")
        if self.config.get_changed():
            self.logger.info(f"ServiceManager: Modified settings: {self.config.get_changed()}")
        else:
            self.logger.info(f"ServiceManager: Using default config")
        # Import services
        if len(self.config.services) > 0:
            for module in self.config.services:
                if not module:
                    self.logger.error(f"ServiceManager: Module: {module} has invalid name.")
                    raise utility.ConfigError(f"ServiceManager: Module: {module} has invalid name.")
                try:
                    importlib.import_module(module)
                    self.logger.info(f"ServiceManager: Module: {module} loaded.")
                except ModuleNotFoundError:
                    self.logger.error(f"ServiceManager: Module: {module} not found.")
                    raise utility.ConfigError(f"ServiceManager: Module: {module} not found. Did you add directory in "
                                              f"which services are located into \"include_dirs\" in config?")

        # Variables filled by __init__()
        self.srv_objects = []  # Instances of Service classes -> [Srv1(), Srv2(), ...]
        self.srv_immutables = []  # Immutable instances of Service classes -> [ImmutableService1(), ...]
        self.srv_names = []  # Names of services -> [srv1.name, srv2.name, ...]
        self.helpers_running = mp.Value(ctypes.c_bool, False)
        self.max_request_size = self.config.max_message_size
        self.running = False
        self.initialized = False

        # Variables filled by initialize()
        self.srv_queues = []  # Queues for services -> [(srv1_input_queue, srv1_output_queue), ...]
        self.srv_running = []  # Multiprocessing boolean for every service
        self.srv_states = []  # 3D array with boolean per thread/process indicating state
        # [[[srv 1 threads], [srv 1 processes]], [[srv 2 threads], [srv 2 processes]], ...]
        # [srv 1 threads] = [thread1, thread2, ...], [srv 1 processes] = [process 1, process2, ...]
        self.srv_values = []  # Same as self.srv_states but with current value
        self.srv_awaiting = []
        self.srv_timeout_counters = []
        self.counter = 0
        self.request_dicts = []  # List of dicts per service, maps request_id to request
        self.garbage_queue = None

        # Create instances of Services
        srv_ids = []
        srv_groups = []
        for srv in utility.Service.__subclasses__():
            new_service = srv()
            if new_service.ignore is True:
                continue  # Skip ignored services
            self._validate_service(new_service, self.srv_names, srv_groups, srv_ids)
            self.srv_objects.append(new_service)
            self.srv_names.append(new_service.name)
            for srv_group in new_service.groups:
                if srv_group not in srv_groups:
                    srv_groups.append(srv_group)
            srv_ids.append(new_service.service_id)

        # Sort services by service ID, it will throw exception if not possible
        # It will only sort srv_names and srv_object
        self._sort_services(srv_ids)

        # Convert mutable Service objects into ImmutableService
        for srv in self.srv_objects:
            try:
                self.srv_immutables.append(utility.ImmutableService(service=srv))
            except TypeError:
                # Should never happen
                self.logger.critical("ServiceManager: Error while trying to convert Service to ImmutableService.")
                raise Exception("ServiceManager: Error while trying to convert Service to ImmutableService.")
        if len(self.srv_objects) == 0:
            self.logger.critical("ServiceManager: There are no services to run. Define service first.")
            raise Exception("ServiceManager: There are no services to run. Define service first.")
        self.initialize()
        self.logger.info(f"ServiceManager: Initialed with services ({self.get_num_services()}): {self.srv_names}")
        self.logger.debug(f"ServiceManager: Initialed with service groups ({len(srv_groups)}): {srv_groups}")
        self.start()

    def start(self) -> bool:
        """Start all services. It can be called only after initialization which is done automatically in __init__. If
        you called shutdown then you have reinitialize manually by calling initialize()."""
        if self.running is True:
            return False
        if self.initialized is False:
            self.logger.error("ServiceManager: Cannot start uninitialized services.")
            return False
        self.logger.debug("ServiceManager: Starting services")

        for srv_id, srv in enumerate(self.srv_immutables):
            if self.get_service_threads(srv_id) or self.get_service_processes(srv_id):
                self.logger.error(f"ServiceManager: Some threads or processes seams to be running. Continuing anyway. "
                                  f"threads: {self.get_service_threads(srv_id)} "
                                  f"processes: {self.get_service_processes(srv_id)}")
            self._change_mp_value(self.srv_running[srv_id], True)
            for th_id in range(srv.threads):
                self._start_worker_th(srv_id, th_id, self.srv_running[srv_id], self.srv_states[srv_id][0][th_id],
                                      self.srv_values[srv_id][0][th_id], self.srv_awaiting[srv_id][0][th_id],
                                      self.srv_queues[srv_id])

            for proc_id in range(srv.processes):
                self._start_worker_proc(srv_id, proc_id, self.srv_running[srv_id], self.srv_states[srv_id][1][proc_id],
                                        self.srv_values[srv_id][1][proc_id], self.srv_awaiting[srv_id][1][proc_id],
                                        self.srv_queues[srv_id])

            if not self._call_service_start(srv_id):
                self.logger.error(f"ServiceManager: Service: {srv.name} startup failed. "
                                  f"Service will not run.")
                self._stop_running_service(srv_id, True, "Service stopped due to startup timeout.")

        running = [self.srv_names[srv_id] for srv_id, run in enumerate(self.srv_running) if run.value is True]
        self.logger.info(f"ServiceManager: Running services ({self.get_num_running_services()}): {running}")
        self.running = True
        return True

    def stop(self) -> bool:
        """Stop all services. Does not stop logging, terminator, gb_collector. Service queues will still be accessible.
        Services can be started again by calling start. Call shutdown if you want to exit application."""
        if self.running is False:
            return False
        self.logger.debug("ServiceManager: Stopping services")
        self.running = False

        # Call service shutdown methods and stop/kill them
        for srv_id, _ in enumerate(self.srv_immutables):
            self._stop_running_service(srv_id, False, "")

        self.logger.info(f"ServiceManager: Services: {self.srv_names} stopped.")
        return True

    def restart(self) -> None:
        """Restart all services."""
        self.stop()
        self.start()

    def shutdown(self) -> bool:
        """Stop all running threads a processes (except MainThread). This should be called before exiting application.
        After this calling start will not be possible nevertheless you can reinitialize app by calling initialize()."""
        self.stop()
        if self.config.shared_logger is False:
            self.logger.stop_mp_logging()
        self.running = False
        self.initialized = False
        self._change_mp_value(self.helpers_running, False)
        self.garbage_queue.put(None)
        self._kill_services()
        self._kill_terminator()
        self._kill_gb_collector()
        # Destroy queues
        for srv_id, queues in enumerate(self.srv_queues):
            if queues[0] is not None:
                self._destroy_mp_queue(queues[0])
            if queues[1] is not None:
                self._destroy_mp_queue(queues[1])
            self.srv_queues[srv_id] = (None, None)
        self._destroy_mp_queue(self.garbage_queue)
        self.garbage_queue = None
        return True

    def initialize(self):
        """Initialize services, start logger, terminator, gb_collector. It normally should not be called because it is
        called automatically when initializing ServiceManager class. It can be called after shutdown to reinitialize
        again."""
        if self.initialized is True:
            self.logger.error(f"ServiceManager: Already initialized")
            return
        if self.running is True:
            # Should never happen
            self.logger.error(f"ServiceManager: Cannot initialize when running.")
            return
        self.srv_queues = []
        self.srv_running = []
        self.srv_states = []
        self.srv_values = []
        self.srv_awaiting = []
        self.srv_timeout_counters = []
        self.counter = 0
        self.request_dicts = [{} for _ in self.srv_immutables]
        self.garbage_queue = mp.Queue()

        self._change_mp_value(self.helpers_running, True)

        for srv_id, srv in enumerate(self.srv_immutables):
            queues = (mp.Queue(), mp.Queue())  # (input_queue, output_queue)
            process_states, thread_states = [], []
            process_values, thread_values = [], []
            process_awaits, thread_awaits = [], []
            self.srv_timeout_counters.append(0)
            self.srv_running.append(mp.Value(ctypes.c_bool, False))

            for th_id in range(srv.threads):
                state = mp.Value(ctypes.c_bool, False)
                awaiting = mp.Value(ctypes.c_bool, False)
                value = mp.Value(ctypes.c_ulong)  # Initialize with 0
                thread_states.append(state)
                thread_values.append(value)
                thread_awaits.append(awaiting)

            for proc_id in range(srv.processes):
                state = mp.Value(ctypes.c_bool, False)
                awaiting = mp.Value(ctypes.c_bool, False)
                value = mp.Value(ctypes.c_ulong)  # Initialize with 0
                process_states.append(state)
                process_values.append(value)
                process_awaits.append(awaiting)

            self.srv_queues.append(queues)
            self.srv_states.append([thread_states, process_states])
            self.srv_values.append([thread_values, process_values])
            self.srv_awaiting.append([thread_awaits, process_awaits])

        if self.config.shared_logger is False:
            self.logger.start_mp_logging()
        self._start_terminator()
        self._start_garbage_collector()
        self.initialized = True
        self.logger.debug(f"ServiceManager: Initialed")

    def _call_service_shutdown(self, srv_id: int) -> bool:
        """Create new thread that will run service shutdown method. It is thread because we do not want to block
        main tread or be catching exceptions and also there should be timeout for shutdown method."""
        error_msgs: list = []

        def srv_shutdown(mtd: utility.Service.shutdown, error_messages: list) -> None:
            try:
                mtd()
            except Exception as err:
                error_messages.append(err)

        thread = th.Thread(target=srv_shutdown, args=(self.srv_objects[srv_id].shutdown, error_msgs),
                           name=f"{srv_id}_shutdown")
        thread.start()
        if thread.is_alive():
            thread.join(self.config.service_start_timeout)
        if thread.is_alive():
            self._kill_thread(thread.name)
            self.logger.error(f"ServiceManager: Service: {self.srv_immutables[srv_id].name} "
                              f"shutdown() method took more than {self.config.service_shutdown_timeout} seconds.")
            thread.join(self.config.service_start_timeout)  # Timeout for failsafe.
            return False
        if len(error_msgs) > 0:
            self.logger.error(f"ServiceManager: Service: {self.srv_immutables[srv_id].name} "
                              f"shutdown() method raised exception: {error_msgs[0]}")
            return False
        return True

    def _call_service_start(self, srv_id: int) -> bool:
        """Create new thread that will run service start method. It is thread because we do not want to block
        main tread or be catching exceptions and also there should be timeout for start method."""
        error_msgs: list = []

        def srv_start(mtd: utility.Service.start, error_messages: list) -> None:
            try:
                mtd()
            except Exception as err:
                error_messages.append(err)

        thread = th.Thread(target=srv_start, args=(self.srv_objects[srv_id].start, error_msgs),
                           name=f"{srv_id}_start")
        thread.start()
        if thread.is_alive():
            thread.join(self.config.service_start_timeout)
        if thread.is_alive():
            self._kill_thread(thread.name)
            self.logger.error(f"ServiceManager: Service: {self.srv_immutables[srv_id].name} "
                              f"start() method took more than {self.config.service_start_timeout} seconds.")
            thread.join(self.config.service_start_timeout)  # Timeout for failsafe.
            # There could be exception raised so the user would know that the service was not properly initialized
            return False
        if len(error_msgs) > 0:
            self.logger.error(f"ServiceManager: Service: {self.srv_immutables[srv_id].name} "
                              f"start() method raised exception: {error_msgs[0]}")
            return False
        return True

    @staticmethod
    def _get_th_proc_name(srv_id: int, th_proc_id: int, dummy: bool = False) -> str:
        """Logic for naming threads/processes"""
        if dummy:
            return f"{srv_id}-{th_proc_id}_dummy"
        return f"{srv_id}-{th_proc_id}"

    @staticmethod
    def _is_th_proc_name(srv_id: int, name: str) -> bool:
        """Check if thread/process belongs to the service."""
        if name.startswith(f"{srv_id}-"):
            return True
        return False

    def _start_worker_th(self, srv_id: int, th_id: int, is_running: mp.Value, state: mp.Value,
                         value: mp.Value, awaiting: mp.Value, queues: tuple) -> None:
        """Create a start service worker thread."""
        new_thread = th.Thread(target=self._worker,
                               name=self._get_th_proc_name(srv_id, th_id),
                               args=(is_running, state, value, awaiting, srv_id, self.srv_objects[srv_id].run,
                                     self.srv_objects[srv_id].run_list, self.srv_immutables[srv_id].allow_run_list,
                                     queues, self.logger.get_queue(), self.garbage_queue))
        new_thread.start()

    def _start_worker_proc(self, srv_id: int, proc_id: int, is_running: mp.Value, state: mp.Value,
                           value: mp.Value, awaiting: mp.Value, queues: tuple) -> None:
        """Create a start service worker process."""
        new_process = mp.Process(target=self._worker,
                                 name=self._get_th_proc_name(srv_id, proc_id),
                                 args=(is_running, state, value, awaiting, srv_id, self.srv_objects[srv_id].run,
                                       self.srv_objects[srv_id].run_list, self.srv_immutables[srv_id].allow_run_list,
                                       queues, self.logger.get_queue(), self.garbage_queue))
        new_process.start()

    def _start_terminator(self) -> None:
        """Create and start terminator thread."""
        terminator = th.Thread(target=self._terminator, name="terminator", args=(self.helpers_running,))
        terminator.start()

    def _start_garbage_collector(self) -> None:
        """Create and start garbage collector thread."""
        gb_collector = th.Thread(target=self._gb_collector, name="man_gb_collector",
                                 args=(self.helpers_running,), daemon=True)
        gb_collector.start()

    def _start_dummy_service(self, srv_id: int, message: str) -> None:
        """Create and start dummy worker threads."""
        service_queues = self.srv_queues[srv_id]
        for th_id in range(self.srv_immutables[srv_id].threads + self.srv_immutables[srv_id].processes):
            new_thread = th.Thread(target=self._dummy_worker,
                                   name=self._get_th_proc_name(srv_id, th_id, True),
                                   args=(service_queues, srv_id, self.garbage_queue, message))
            new_thread.start()

    @staticmethod
    def _worker(is_running: mp.Value, state: mp.Value, value: mp.Array, awaiting: mp.Value, srv_id: int,
                run: Callable[[str], dict], run_list: Callable[[list[str]], list[dict]], allow_list: bool,
                queues: tuple, log_q: mp.Queue, gb_q: mp.Queue) -> None:
        """Implementation of service worker thread/process.
        Allows thread/process timeout interruption and value recovery."""
        def change_value(val: mp.Value, new_val: Union[bool, int]) -> None:
            val.acquire()
            val.value = new_val
            val.release()

        def check_result(result: dict) -> dict:
            if not isinstance(result, dict):
                raise Exception("Service did not return valid result.")
            return result

        def check_results(results: list) -> list:
            if not isinstance(results, list):
                raise Exception("Service did not return valid result.")
            if any(not isinstance(res, dict) for res in results):
                raise Exception("Service did not return valid result.")
            return results

        log_q.put(("DEBUG", f"Worker ({run.__self__.__class__}): started"))
        while is_running.value is True:
            if state.value is False:
                change_value(state, True)

            change_value(awaiting, True)
            request = queues[0].get()
            if request is None:
                # None is a signal to thread/process to check is_running value. It is crucial part of supervision.
                continue
            change_value(value, request[0])  # Request ID
            change_value(awaiting, False)

            try:
                if isinstance(request[1], list):
                    if allow_list is True:
                        service_output = check_results(run_list(request[1]))
                    else:
                        service_output = []
                        for req in request[1]:
                            service_output.append(check_result(run(req)))
                    if len(request[1]) != len(service_output):
                        raise Exception("Length of input does not equal length of output. Output Discarded.")
                else:
                    service_output = check_result(run(request[1]))
            except Exception as err:
                log_q.put(("ERROR", f"Worker ({run.__self__.__class__}): Service raised exception: exception: {err}"))
                output = {"server": "Service raised exception", "exception": str(err)}
                if isinstance(request[1], list):
                    service_output = [output for _ in range(len(request[1]))]
                else:
                    service_output = output
            if is_running.value is False:
                # Service stopped while running service run method
                try:
                    # This is sketchy
                    queues[1].put((request[0], service_output))
                    change_value(value, 0)
                    gb_q.put((srv_id, request[0]))
                    log_q.put(("ERROR", f"Worker ({run.__self__.__class__}): "
                                        f"Thread/Process stopped during running, output processed anyway."))
                except (OSError, IndexError):
                    # Output is lost because output queue does not exist at this point
                    log_q.put(("ERROR", f"Worker ({run.__self__.__class__}): "
                                        f"Thread/Process stopped during running, output is lost."))
                break
            queues[1].put((request[0], service_output))
            change_value(value, 0)
            gb_q.put((srv_id, request[0]))
            log_q.put(("DEBUG", f"Worker ({run.__self__.__class__}): request: {request} result: {service_output}"))
        log_q.put(("DEBUG", f"Worker ({run.__self__.__class__}): died"))

    def _dummy_worker(self, queues: tuple, srv_id: int, gb_q: mp.Queue, message: str) -> None:
        """Implementation of service dummy worker thread. This worker is used when service is stopped."""
        self.logger.debug(f"Dummy worker (srv_id: {srv_id}): started")
        while self.running is True:
            request = queues[0].get()
            if request is None:
                # None is a signal to thread/process to check is_running value. It is crucial part of supervision.
                continue
            output = {"server": message}
            if isinstance(request[1], list):
                service_output = [output for _ in range(len(request[1]))]
            else:
                service_output = output
            queues[1].put((request[0], service_output))
            gb_q.put((srv_id, request[0]))
            self.logger.debug(f"Dummy worker (srv_id: {srv_id}): {request} -> {service_output}")
        self.logger.debug(f"Dummy worker (srv_id: {srv_id}): died")

    def _terminator(self, running: mp.Value) -> None:
        """Implementation of terminator thread. Main purpose of this thread is to supervise worker thread. Monitor
        if workers are running properly if not than terminate them recover values and start new thread. If service
        thread/process timeouts more than Service.max_timeouts than whole service is terminated."""
        time.sleep(self.config.th_proc_response_time)  # Delay for services to start
        if all(srv.timeout == 0 for srv in self.srv_immutables):
            self.logger.debug("ServiceManager: Terminator: did not start because every service has timeout 0")
            return

        # Create counters (Copy of self.service_states filled with zeroes)
        counters = [[[], []] for _ in range(len(self.srv_states))]
        for srv_id, srv in enumerate(self.srv_states):
            for th_proc_id, th_proc in enumerate(srv):
                for _ in th_proc:
                    counters[srv_id][th_proc_id].append(0)

        self.logger.debug("ServiceManager: Terminator: started")
        while running.value is True:
            no_respond = False
            for srv_id, srv_states, srv in zip(range(len(self.srv_immutables)), self.srv_states, self.srv_immutables):
                # Skip services with timeout = 0
                # if self.srv_simple[srv_id] is True:
                #     continue
                if self.srv_immutables[srv_id].timeout == 0:
                    continue
                # Skip not running services
                if self.srv_running[srv_id].value is False:
                    continue
                stop_service = False

                # Check thread states
                for th_id, th_state in enumerate(srv_states[0]):
                    if th_state.value:  # Thread responding normally
                        counters[srv_id][0][th_id] = 0
                        self._change_mp_value(th_state, False)
                        continue
                    if self.srv_awaiting[srv_id][0][th_id].value is True:
                        # Thread awaiting request
                        counters[srv_id][0][th_id] = 0
                        continue
                    # Thread not responding (Stuck in service run method)
                    no_respond = True
                    counters[srv_id][0][th_id] += 1
                    if counters[srv_id][0][th_id] < srv.timeout:  # No respond within timeout limit
                        continue
                    # If request is list -> extend timeout times number of requests
                    try:
                        request_id = self.srv_values[srv_id][0][th_id]
                        request = self.request_dicts[srv_id][int(request_id.value)]
                        if isinstance(request, list):
                            if counters[srv_id][0][th_id] < srv.timeout * len(request):
                                continue
                    except (KeyError, IndexError):
                        self.logger.warning(f"ServiceManager: Terminator: KeyError or IndexError when accessing value "
                                            f"of service: {srv.name} thread: {srv_id}-{th_id}")
                        # Request id does not exists -> Can theoretically happen
                        # srv_value error -> Should not happen
                        # Proceed restarting thread/process
                    # Thread not responding for srv.timeout seconds
                    self.srv_timeout_counters[srv_id] += 1
                    if self.srv_timeout_counters[srv_id] >= srv.max_timeouts != 0:
                        # Service timeout too many times (srv.max_timeouts)
                        stop_service = True
                        break
                    self.logger.warning(f"ServiceManager: Terminator: Restarting service: {srv.name} thread: "
                                        f"{srv_id}-{th_id}, due to not responding for "
                                        f"{counters[srv_id][0][th_id]} seconds")
                    self._restart_thread(srv_id, th_id)

                # Check process states
                for proc_id, process_state in enumerate(srv_states[1]):
                    if stop_service is True:
                        break
                    if process_state.value:
                        counters[srv_id][1][proc_id] = 0
                        self._change_mp_value(process_state, False)
                        continue
                    if self.srv_awaiting[srv_id][1][proc_id].value is True:
                        # Process awaiting request
                        counters[srv_id][1][proc_id] = 0
                        continue
                    no_respond = True
                    counters[srv_id][1][proc_id] += 1
                    if counters[srv_id][1][proc_id] < srv.timeout:
                        continue
                    # If request is list -> extend timeout times number of requests
                    try:
                        request_id = self.srv_values[srv_id][1][proc_id]
                        request = self.request_dicts[srv_id][int(request_id.value)]
                        if isinstance(request, list):
                            if counters[srv_id][1][proc_id] < srv.timeout * len(request):
                                continue
                    except (KeyError, IndexError):
                        self.logger.warning(f"ServiceManager: Terminator: KeyError or IndexError when accessing value "
                                            f"of service: {srv.name} process: {srv_id}-{proc_id}")
                        # Proceed restarting thread/process
                    self.srv_timeout_counters[srv_id] += 1
                    if self.srv_timeout_counters[srv_id] >= srv.max_timeouts != 0:
                        stop_service = True
                        break
                    self.logger.warning(f"ServiceManager: Terminator: Restarting service: {srv.name} process: "
                                        f"{srv_id}-{proc_id}, due to not responding for "
                                        f"{counters[srv_id][1][proc_id]} seconds")
                    self._restart_process(srv_id, proc_id)

                if stop_service is True:
                    self.logger.error(f"ServiceManager: Terminator: Stopping service {srv.name} due to too many "
                                      f"timeouts. Starting dummy service.")
                    self._stop_running_service(srv_id, True, "Service stopped due to too many timeouts.")

            if no_respond is True:
                time.sleep(1)  # 1 sec delay between terminator cycles (when not responding services detected)
            else:
                time.sleep(self.config.terminator_idle_cycle)  # Term. delay when nothing stuck
        self.logger.debug("ServiceManager: Terminator: died")

    def _gb_collector(self, running: mp.Value) -> None:
        """Implementation of garbage collector thread. Thread for deleting processed requests. It will also periodically
        delete unprocessed request if they are pending for more than avg self.config.garbage_collector_timeout.
        This should not be used as substitute for terminator thread/proc supervision. 1. this will only delete request
        but it will not stop the actual thread/process 2. timing is not precise, in reality it can take much longer.
        For thread/process supervision Service.timeout should be used."""
        self.logger.debug("ServiceManager: Garbage collector: started")
        # Set min max to garbage_cycle
        garbage_cycle = self.config.max_service_run_time
        if garbage_cycle > 90:
            garbage_cycle = 90
        pending_requests = [[] for _ in self.srv_names]  # List for every service
        while running.value is True:
            try:
                req = self.garbage_queue.get(timeout=garbage_cycle)
                # req = (service_id, request_id)
            except OSError:
                self.logger.error(f"ServiceManager: Error while trying to get from garbage queue.")
                time.sleep(1)
                continue
            except _queue.Empty:
                # Delete requests which are still pending. Timing is not precise. This will be triggered at minimum
                # config.garbage_collector_timeout seconds but it can take longer (never in some scenarios).
                for srv_id, pending_request_list in enumerate(pending_requests):
                    to_delete = []
                    existing_pending_ids = [req[0] for req in pending_requests[srv_id]]
                    for pending_request_id in self.request_dicts[srv_id].keys():
                        if pending_request_id in existing_pending_ids:
                            # This should happen very rarely
                            req = pending_requests[srv_id][existing_pending_ids.index(pending_request_id)]
                            if (datetime.datetime.now() - req[1]).total_seconds() <= self.config.max_service_run_time:
                                # Pending for less than self.config.max_service_run_time seconds
                                continue
                            to_delete.append(pending_request_id)
                    for req_id in to_delete:
                        try:
                            del self.request_dicts[srv_id][req_id]
                        except KeyError:
                            # This should never happen
                            self.logger.error(f"ServiceManager: Key error when trying to delete pending "
                                              f"request ID: {req_id} of a service: {srv_id}.")
                        # Let user know why request was deleted (It might by confusing)
                        self.logger.warning(f"ServiceManager: Request with ID: {req_id} was deleted because its "
                                            f"processing took too long. It was triggered by setting: "
                                            f"\'max_service_run_time\'={self.config.max_service_run_time}.")

                # Search for new pending requests
                for d_id, d in enumerate(self.request_dicts):
                    new_pending_requests = []
                    existing_pending_ids = [req[0] for req in pending_requests[d_id]]
                    for req_id in d.keys():
                        try:
                            new_pending_requests.append(pending_requests[d_id][existing_pending_ids.index(req_id)])
                        except ValueError:
                            new_pending_requests.append((req_id, datetime.datetime.now()))
                    pending_requests[d_id] = new_pending_requests

                continue  # continue while

            if req is None:
                continue
            try:
                self.logger.debug(f"ServiceManager: Garbage collector: removing finished "
                                  f"request ID: {req[1]} of service: {req[0]}")
                del self.request_dicts[req[0]][req[1]]
            except KeyError:
                # This can rarely happen (request was deleted from request_dicts due to garbage_collector_timeout then
                # worker finished processing). Response might be still processable by DatabaseManager
                self.logger.warning(f"ServiceManager: Key error when trying to delete "
                                    f"request ID: {req[1]} of a service: {req[0]}. Ignoring.")

        self.logger.debug("ServiceManager: Garbage collector: died")

    @staticmethod
    def _change_mp_value(value: mp.Value, new_value: bool) -> None:
        """Acquire and change multiprocessing.Value"""
        value.acquire()
        value.value = new_value
        value.release()

    def _recover_value(self, srv_id: int, value: mp.Array) -> Union[str, list[str], None]:
        """Recover request from service thread/process that was stopped."""
        value.acquire()
        res_id = value.value
        value.value = 0  # Reset value so it cannot be recovered again
        value.release()
        if res_id == 0:
            return None
        try:
            return self.request_dicts[srv_id][res_id]
        except KeyError:
            return None

    def _recover_service_values(self, srv_id: int) -> list:
        """Recover requests from all service threads/processes."""
        service_values = self.srv_values[srv_id]
        recovered_values = []
        for th_value in service_values[0]:
            recovered_value = self._recover_value(srv_id, th_value)
            if recovered_value:
                recovered_values.append(recovered_value)

        for proc_values in service_values[1]:
            recovered_value = self._recover_value(srv_id, proc_values)
            if recovered_value:
                recovered_values.append(recovered_value)

        return recovered_values

    def _stop_running_service(self, srv_id: int, start_dummy: bool, message: str) -> None:
        """Signal service threads/processes to stop. Wait for response than forcefully kill remaining. """
        # Signal treads/processes to stop
        self._change_mp_value(self.srv_running[srv_id], False)

        for _ in range(self.srv_immutables[srv_id].threads + self.srv_immutables[srv_id].processes + 1):
            self.srv_queues[srv_id][0].put(None)
        # Kill threads/processes if still running
        self._kill_service(srv_id)
        # Call service shutdown method
        if not self._call_service_shutdown(srv_id):
            self.logger.error(f"ServiceManager: Service: {self.srv_immutables[srv_id].name} shutdown failed.")
        # Recover threads/processes unprocessed requests
        recovered_values = self._recover_service_values(srv_id)
        if recovered_values:
            self.logger.debug(f"ServiceManager: Service: {self.srv_names[srv_id]}, "
                              f"recovered values: {recovered_values}")
        for value in recovered_values:
            # Put recovered value to the service input queue (without changing request_id)
            self._rerun_service(srv_id, value)
        if start_dummy:
            # Start dummy worker for the service
            self._start_dummy_service(srv_id, message)

    def _kill_terminator(self) -> None:
        """Forcefully kill terminator."""
        for thread in th.enumerate():
            if thread.name == f"terminator":
                thread.join(self.config.th_proc_response_time)
                if not thread.is_alive():
                    return
                self.logger.info(f"ServiceManager: Killing terminator: {thread}")
                res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, ctypes.py_object(SystemExit))
                if res > 1:
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, 0)
                return

    def _kill_gb_collector(self) -> None:
        """Forcefully kill garbage collector. This can be called only after every service thread/process is dead."""
        for thread in th.enumerate():
            if thread.name == "man_gb_collector":
                thread.join(self.config.th_proc_response_time)
                if not thread.is_alive():
                    return
                self.logger.info(f"ServiceManager: Killing garbage collector: {thread}")
                res = ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, ctypes.py_object(SystemExit))
                if res > 1:
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, 0)
                return

    def _kill_service(self, srv_id: int) -> None:
        """Forcefully kill all service threads/processes."""
        for thread_name in self.get_service_threads(srv_id):
            self._kill_thread(thread_name)

        for process_name in self.get_service_processes(srv_id):
            self._kill_process(process_name)

    def _kill_services(self) -> None:
        """Forcefully kill all services and their threads/processes."""
        for srv_id, _ in enumerate(self.srv_immutables):
            self._kill_service(srv_id)

    def _kill_thread(self, thread_name: str) -> None:
        """Forcefully kill thread."""
        for thread in th.enumerate():
            if thread.name == thread_name:
                # Time for graceful shutdown
                thread.join(self.config.th_proc_response_time)
                if not thread.is_alive():
                    return
                self.logger.info(f"ServiceManager: Killing thread: {thread}")
                res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread.ident),
                                                                 ctypes.py_object(SystemExit))
                if res > 1:
                    self.logger.warning(f"ServiceManager: Killing thread: {thread} failed")
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, 0)
                thread.join(0.5)

    def _kill_process(self, process_name: str) -> None:
        """Forcefully kill process."""
        for process in mp.active_children():
            if process.name == process_name:
                process.join(self.config.th_proc_response_time)
                if not process.is_alive():
                    return
                self.logger.info(f"ServiceManager: Killing process: {process}")
                process.terminate()
                process.join()

    def _restart_thread(self, srv_id: int, th_id: int) -> None:
        """Forcefully restart service worker thread and recover unfinished request."""
        self._kill_thread(self._get_th_proc_name(srv_id, th_id))
        # Recover thread value
        recovered_value = self._recover_value(srv_id, self.srv_values[srv_id][0][th_id])
        if recovered_value:
            self.logger.debug(f"ServiceManager: Service: {self.srv_names[srv_id]}, recovered value: {recovered_value}")
            self._rerun_service(srv_id, recovered_value)
        self._start_worker_th(srv_id,
                              th_id,
                              self.srv_running[srv_id],
                              self.srv_states[srv_id][0][th_id],
                              self.srv_values[srv_id][0][th_id],
                              self.srv_awaiting[srv_id][0][th_id],
                              self.srv_queues[srv_id])

    def _restart_process(self, srv_id: int, proc_id: int) -> None:
        """Forcefully restart service worker process and recover unfinished request."""
        self._kill_process(self._get_th_proc_name(srv_id, proc_id))
        # Recover process value
        recovered_value = self._recover_value(srv_id, self.srv_values[srv_id][1][proc_id])
        if recovered_value:
            self.logger.debug(f"ServiceManager: Service: {self.srv_names[srv_id]}, recovered value: {recovered_value}")
            self._rerun_service(srv_id, recovered_value)

        self._start_worker_proc(srv_id,
                                proc_id,
                                self.srv_running[srv_id],
                                self.srv_states[srv_id][1][proc_id],
                                self.srv_values[srv_id][1][proc_id],
                                self.srv_awaiting[srv_id][1][proc_id],
                                self.srv_queues[srv_id])

    @staticmethod
    def _destroy_mp_queue(q: mp.Queue) -> None:
        try:
            while not q.empty():
                q.get()
        except OSError:
            # Queue is already closed
            pass
        q.close()
        q.cancel_join_thread()
        q.join_thread()

    def _sort_services(self, srv_ids) -> bool:
        """Sort services according to service ID. Raise exception if not possible."""
        # Assign service IDs
        for srv_id, custom_id in enumerate(srv_ids):
            if isinstance(custom_id, int) and custom_id >= len(srv_ids):
                self.logger.critical(f"ServiceManager: {self.srv_objects[srv_id].__class__}: Service ID is too large.")
                raise Exception(f"ServiceManager: {self.srv_objects[srv_id].__class__}: Service ID is too large.")
            if custom_id is None:
                for i in range(len(srv_ids)):
                    if i not in srv_ids:
                        srv_ids[srv_id] = i
                        self.srv_objects[srv_id].service_id = i
                        break

        # Check if sorted
        if all(a <= b for a, b in zip(srv_ids, srv_ids[1:])):
            return True  # Services sorted
        else:
            # Only srv_objects, srv_names needs to be sorted at this point
            srv_info = zip(srv_ids, self.srv_objects, self.srv_names)
            srv_info = sorted(srv_info, key=lambda x: x[0])
            self.srv_objects = [s_o for s_i, s_o, s_n in srv_info]
            self.srv_names = [s_n for s_i, s_o, s_n in srv_info]
            return True

    def _validate_service(self, srv: utility.Service, srv_names: list, srv_groups: list, srv_ids: list) -> bool:
        """Service object validation. Raises exception if not valid."""
        # Data type validation
        if not all(isinstance(i, int) for i in [srv.threads, srv.processes,
                                                srv.timeout, srv.max_timeouts]):
            self.logger.critical(f"{srv.__class__}: [threads, processes, timeout, max_timeouts] must be integer.")
            raise Exception(f"{srv.__class__}: [threads, processes, timeout, max_timeouts] must be integer.")
        if not all(isinstance(i, str) for i in [srv.name, srv.description]):
            self.logger.critical(f"{srv.__class__}: [name, description] must be string.")
            raise Exception(f"{srv.__class__}: [name, description] must be string.")
        if not isinstance(srv.groups, list):
            self.logger.critical(f"{srv.__class__}: [srv.groups] must be list.")
            raise Exception(f"{srv.__class__}: [srv.groups] must be list.")
        if not all(isinstance(i, str) for i in srv.groups):
            self.logger.critical(f"{srv.__class__}: [srv.groups] group_name must be string.")
            raise Exception(f"{srv.__class__}: [srv.groups] group_name must be string.")
        if not srv.threads > 0 and not srv.processes > 0:
            self.logger.critical(f"{srv.__class__}: Every service must have at least 1 thread/process.")
            raise Exception(f"{srv.__class__}: Every service must have at least 1 thread/process.")

        # Service name validation
        if srv.name in srv_names:
            self.logger.critical(f"{srv.__class__}: Every service must have unique name.")
            raise Exception(f"{srv.__class__}: Every service must have unique name.")
        if srv.name == "":
            self.logger.critical(f"{srv.__class__}: Every service must have service name.")
            raise Exception(f"{srv.__class__}: Every service must have service name.")
        # Allow only ASCII letters or numbers or allowed_chars
        allowed_chars = [" ", "_", "-", "."]
        if not all(ord(c) < 128 and (c.isalnum() or c in allowed_chars) for c in srv.name):
            self.logger.critical(f"{srv.__class__}: Invalid service name \'{srv.name}\' "
                                 f"it can contain only ASCII letters, numbers or characters in: {allowed_chars}.")
            raise Exception(f"{srv.__class__}: Invalid service name \'{srv.name}\' "
                            f"it can contain only ASCII letters, numbers or characters in: {allowed_chars}.")

        # Do not allow special characters at the end
        if any(srv.name.endswith(c) for c in allowed_chars):
            self.logger.critical(f"{srv.__class__}: Invalid service name \'{srv.name}\' name cannot ends with "
                                 f"characters in: {allowed_chars}.")
            raise Exception(f"{srv.__class__}: Invalid service name \'{srv.name}\' name cannot ends with "
                            f"characters in: {allowed_chars}.")

        # Do not allow leading/trailing spaces
        if srv.name != srv.name.strip():
            self.logger.critical(f"{srv.__class__}: Invalid service name \'{srv.name}\' "
                                 f"did you mean \'{srv.name.strip()}\'?")
            raise Exception(f"{srv.__class__}: Invalid service name \'{srv.name}\' "
                            f"did you mean \'{srv.name.strip()}\'?")
        # Auto is reserved because web_client search select. / Server because that is default server response.
        prohibited = ["server", "auto"]
        if srv.name.lower() in prohibited:
            self.logger.critical(f"{srv.__class__}: Names: {prohibited} are reserved. Please use different name.")
            raise Exception(f"{srv.__class__}: Names: {prohibited} are reserved. Please use different name.")

        # Service ID validation (It can be int or None)
        if not isinstance(srv.service_id, int) and srv.service_id is not None:
            self.logger.critical(f"{srv.__class__}: Service ID must be integer.")
            raise Exception(f"{srv.__class__}: Service ID must be integer.")
        # If it is int it must be >= 0
        if isinstance(srv.service_id, int) and srv.service_id < 0:
            self.logger.critical(f"{srv.__class__}: Service ID must be positive number.")
            raise Exception(f"{srv.__class__}: Service ID must be positive number.")
        # If it is int then it must be unique
        if isinstance(srv.service_id, int) and srv.service_id in srv_ids:
            self.logger.critical(f"{srv.__class__}: Service ID must be unique.")
            raise Exception(f"{srv.__class__}: Service ID must be unique.")

        # Handle all group
        if self.config.disable_all_groups is False:
            # Do not allow similar group name to "all"
            for group_name in srv.groups:
                if group_name.strip().lower() == "all" and group_name != "all":
                    self.logger.critical(f"{srv.__class__}: Invalid group name \'{group_name}\' "
                                         f"it could be confused with implicit group name \'all\'.")
                    raise Exception(f"{srv.__class__}: Invalid group name \'{group_name}\' "
                                    f"it could be confused with implicit group name \'all\'.")
            # Append all group front
            if "all" not in srv.groups:
                srv.groups.insert(0, "all")  # Append front
        else:
            # self.config.disable_all_group is True -> remove all group from service
            if "all" in srv.groups:
                srv.groups.pop(srv.groups.index("all"))

        # Group name extra validation
        srv_groups_lower = [g.lower() for g in srv_groups]
        srv_names_lower = [n.lower() for n in srv_names]
        for group_name in srv.groups:
            # Allow only ASCII letters or numbers or allowed_chars
            if not all(ord(c) < 128 and (c.isalnum() or c in allowed_chars) for c in group_name):
                self.logger.critical(f"{srv.__class__}: Invalid group name \'{group_name}\' "
                                     f"it can contain only ASCII letters, numbers or characters in: {allowed_chars}.")
                raise Exception(f"{srv.__class__}: Invalid group name \'{group_name}\' "
                                f"it can contain only ASCII letters, numbers or characters in: {allowed_chars}.")
            # Do not allow special characters at the end
            if any(group_name.endswith(c) for c in allowed_chars):
                self.logger.critical(f"{srv.__class__}: Invalid group name \'{group_name}\' name cannot ends with "
                                     f"characters in: {allowed_chars}.")
                raise Exception(f"{srv.__class__}: Invalid group name \'{group_name}\' name cannot ends with "
                                f"characters in: {allowed_chars}.")
            # Do not allow leading/trailing spaces
            if group_name != group_name.strip():
                self.logger.critical(f"{srv.__class__}: Invalid group name \'{group_name}\' "
                                     f"did you mean \'{group_name.strip()}\'?")
                raise Exception(f"{srv.__class__}: Invalid group name \'{group_name}\' "
                                f"did you mean \'{group_name.strip()}\'?")
            # Do not allow group name starts with "list "
            # It because web client logic
            if group_name.lower().startswith("list "):
                self.logger.critical(f"{srv.__class__}: Invalid group name \'{group_name}\' "
                                     f"it cannot starts with \'list \'")
                raise Exception(f"{srv.__class__}: Invalid group name \'{group_name}\' "
                                f"it cannot starts with \'list \'")
            # Do not allow same group name as other service name if disable_name_groups is False
            if self.config.disable_name_groups is False:
                # Less strict
                if group_name in srv_names:
                    self.logger.critical(f"{srv.__class__}: Invalid service group \'{group_name}\' it cannot be name of"
                                         f" a service while using disable_name_groups=False.")
                    raise Exception(f"{srv.__class__}: Invalid service group \'{group_name}\' it cannot be name of "
                                    f"a service while using disable_name_groups=False.")
                # More strict if key_sensitivity is False
                if self.config.key_sensitivity is False:
                    if group_name.lower() in srv_names_lower:
                        self.logger.critical(f"{srv.__class__}: Invalid service group \'{group_name}\' it cannot be "
                                             f"name of a service while using disable_name_groups=False.")
                        raise Exception(f"{srv.__class__}: Invalid service group \'{group_name}\' it cannot be name of "
                                        f"a service while using disable_name_groups=False.")
            # Warn user about key insensitive same group names
            if self.config.key_sensitivity is False:
                if group_name not in srv_groups and group_name.lower() in srv_groups_lower:
                    self.logger.warning(f"{srv.__class__}: Service group: \'{group_name}\' and: "
                                        f"\'{srv_groups[srv_groups_lower.index(group_name.lower())]}\' "
                                        f"are considered the same due to key_sensitivity=False.")

        # Handle name group
        if self.config.disable_name_groups is False:
            if srv.name in srv_groups:
                self.logger.critical(
                    f"{srv.__class__}: Service group \'{srv.name}\' is already used in a different "
                    f"service. It must be unique while using disable_name_groups=False.")
                raise Exception(f"{srv.__class__}: Service group \'{srv.name}\' is already used in a different "
                                f"service. It must be unique while using disable_name_groups=False.")
            if self.config.key_sensitivity is False:
                if srv.name.lower() in srv_groups_lower:
                    self.logger.critical(
                        f"{srv.__class__}: Service group \'{srv.name}\' is already used in a different"
                        f" service. It must be unique while using disable_name_groups=False.")
                    raise Exception(
                        f"{srv.__class__}: Service group \'{srv.name}\' is already used in a different "
                        f"service. It must be unique while using disable_name_groups=False.")
            # Append name group front
            if srv.name not in srv.groups:
                srv.groups = [srv.name] + srv.groups  # Append front
                # srv.groups.insert(0, srv.name)  # This causes unexpected behaviour
                # srv.groups.append(srv.name)  # This causes unexpected behaviour

        # If key_sensitivity is False, then do not allow same (key insensitive) name
        if self.config.key_sensitivity is False:
            for name in srv_names:
                if name.lower() == srv.name.lower():
                    self.logger.critical(f"{srv.__class__}: Service name \'{srv.name}\' is already being used in a "
                                         f"different service \'{name}\'. Choose unique name.")
                    raise Exception(f"{srv.__class__}: Service name \'{srv.name}\' is already being used in a "
                                    f"different service \'{name}\'. Choose unique name.")

        # Service timeout validation
        if srv.timeout > self.config.max_service_run_time:
            # Let user know that having Service.timeout more the config.max_service_run_time is weird but valid.
            self.logger.warning(f"{srv.__class__}: Service timeout: {srv.timeout} is more then global "
                                f"\'max_service_run_time\'={self.config.max_service_run_time} this might result "
                                f"in unexpected behavior. ")
        # Warn user that having both threads and processes is unusual
        if srv.threads > 0 and srv.processes > 0:
            self.logger.warning(f"{srv.__class__}: Service is mixing threads ({srv.threads}) "
                                f"and processes ({srv.processes}).")
        return True

    def validate_request(self, request: str) -> bool:
        """Validate single request.

            Args:
                request (str): Request that should be validated.

            Returns:
                (bool): True if request is valid.
        """
        if not isinstance(request, str):
            self.logger.debug(f"ServiceManager: Request validation failed: not a string, request: {request}")
            return False
        # benchmark needed: self.config.max_message_size vs self.max_request_size
        if len(request) > self.max_request_size:
            self.logger.debug(f"ServiceManager: Request validation failed: request too big, request: {request}")
            return False
        return True

    def validate_requests(self, requests: list[str]) -> bool:
        """Validate list of requests.

            Args:
                requests (list[str]): list of requests that should be validated.

            Returns:
                (bool): True if requests are valid.
        """
        if not isinstance(requests, list):
            self.logger.debug(f"ServiceManager: Requests validation failed: not a list, requests: {requests}")
            return False
        for req in requests:
            # benchmark needed: self.config.max_message_size vs self.max_request_size
            if not isinstance(req, str):
                self.logger.debug(f"ServiceManager: Request validation "
                                  f"failed: not a string, request: {req} in requests: {requests}")
                return False
            if len(req) > self.max_request_size:
                self.logger.debug(f"ServiceManager: Request validation "
                                  f"failed: request too big, request: {req} in requests: {requests}")
                return False
        return True

    @functools.lru_cache(maxsize=CACHE_SIZE)
    def validate_service_id(self, service_id: int) -> bool:
        """Validate service ID.

            Args:
                service_id (int): ID of service that should be validated.

            Returns:
                (bool): True if it is valid service ID
        """
        if not isinstance(service_id, int):
            self.logger.debug(f"ServiceManager: service_id: {service_id} validation failed: not an int")
            return False
        if service_id > len(self.srv_names) or service_id < 0:
            self.logger.debug(f"ServiceManager: service_id: {service_id} validation failed: too small/too large")
            return False
        return True

    def run_service(self, service_id: int, request: str) -> Union[None, int]:
        """Run service with single request. Request and service ID will be validated. Does Not check if services are
        running.

            Args:
                service_id (int): ID of service which should be run.
                request (str): Request that service should process.

            Returns:
                (None | int): Request ID or None if validation failed.
        """
        if self.validate_service_id(service_id) is False:
            return None

        if self.validate_request(request) is False:
            return None
        try:
            req_id = self.get_next_index()
            self.srv_queues[service_id][0].put((req_id, request))
            # Request is saved to request_dict after it is placed to srv input queue
            self.request_dicts[service_id][req_id] = request
            self.logger.debug(f"ServiceManager: Running service: {self.srv_names[service_id]} "
                              f"with request ID: {req_id} request: {request}")
            return req_id
        except AttributeError:
            self.logger.error(f"ServiceManager: Input queue for service: {self.srv_names[service_id]} no longer exists")
            return None

    def run_service_list(self, service_id: int, request_list: list[str]) -> Union[None, int]:
        """Run service with list of requests. Requests and service ID will be validated. Does Not check if services are
        running.

            Args:
                service_id (int): ID of service which should be run.
                request_list (list[str]): List of requests that service should process.

            Returns:
                (None | int): Request ID or None if validation failed.
        """
        if self.validate_service_id(service_id) is False:
            return None

        if self.validate_requests(request_list) is False:
            return None

        try:
            req_id = self.get_next_index()
            self.srv_queues[service_id][0].put((req_id, request_list))
            # Request is saved to request_dict after it is placed to srv input queue
            self.request_dicts[service_id][req_id] = request_list
            self.logger.debug(f"ServiceManager: Running service: {self.srv_names[service_id]} "
                              f"with request ID: {req_id} requests: {request_list}")
            return req_id
        except AttributeError:
            self.logger.error(f"ServiceManager: Input queue for service: {self.srv_names[service_id]} no longer exists")
            return None

    def _rerun_service(self, service_id: int, request: Union[str, list[str]]) -> None:
        """Rerun request. This will not create new request ID."""
        # Find original index
        orig_indexes = []
        for k, v in self.request_dicts[service_id].items():
            if v == request:
                orig_indexes.append(k)
        if len(orig_indexes) == 0:
            # Should not happen -> if it does than request will be lost
            self.logger.error(f"ServiceManager: Request is lost due to missing request ID. Request: {request}")
            return
        if len(orig_indexes) > 1:
            # This theoretically can happen if request is submitted while at the same time identical request is being
            # removed due to garbage_collector_timeout. In that case lower ID (first found) will be picked up.
            self.logger.error(f"ServiceManager: Multiple IDs for request: {request} found. Choosing: {orig_indexes[0]}")

        # Put request directly to input queue (request ID must not change)
        try:
            self.srv_queues[service_id][0].put((orig_indexes[0], request))
            self.logger.debug(f"ServiceManager: Rerunning request_id: {orig_indexes[0]} request: {request}")
        except AttributeError:
            # Input queue does not exist. Should never happen.
            self.logger.error(f"ServiceManager: Input queue for service: {self.srv_names[service_id]} does not exists."
                              f"Request: {request} is lost.")

    def is_pending(self, service_id: int, request_id: int) -> Union[None, bool]:
        """Check if request is still being processed. Service ID and request ID will be validated.

            Args:
                service_id (int): ID of service that should be checked.
                request_id (list[str]): Request ID that should be check.

            Returns:
                (None | bool): True if request is still being processed. None if validation failed.
        """
        if self.validate_service_id(service_id) is False:
            return None

        if not isinstance(request_id, int):
            return None

        if request_id in self.request_dicts[service_id]:
            return True
        return False

    def get_current_index(self) -> int:
        """Get current request ID.

            Returns:
                (int): Current request ID.
        """
        return self.counter

    def get_next_index(self):
        """Generate new request ID.

            Returns:
                (int): New request ID.
        """
        if self.counter >= 4294967295:
            # limited to unsigned long
            self.counter = 0
        # Counter must never be 0
        self.counter += 1
        return self.counter

    def get_service_result_nowait(self, service_id: int) -> Union[tuple, None]:
        """Get service output non blocking. Service ID will be validated.

            Args:
                service_id (int): ID of service that should be checked for result.

            Returns:
                (tuple | None): Tuple with (request_id, output). Returns None if validation failed or no result found.
        """
        if self.validate_service_id(service_id) is False:
            return None
        if self.srv_queues[service_id][1].empty():
            return None
        try:
            return self.srv_queues[service_id][1].get_nowait()
        except queue.Empty:
            return None

    def get_service_result(self, service_id: int, timeout: Union[float, None] = None) -> Union[tuple, None]:
        """Get service output blocking version. Service ID and timeout will be validated.

            Args:
                service_id (int): ID of service that should be checked for result.
                timeout (float | None): Max block time in seconds. None for no limit.

            Returns:
                (tuple | None): Tuple with (request_id, output). Returns None if validation failed or no result found.
        """
        if self.validate_service_id(service_id) is False:
            return None
        if timeout is None:
            result = self.srv_queues[service_id][1].get()
            return result

        # int will be also accepted
        if not isinstance(timeout, (float, int)):
            return None

        try:
            result = self.srv_queues[service_id][1].get(timeout=timeout)
        except queue.Empty:
            return None
        return result

    def get_service_output_queue(self, service_id: int) -> Union[mp.Queue, None]:
        """Get service output queue. Direct access to service queue. Use with caution!

            Args:
                service_id (int): ID of service which output queue should be returned.

            Returns:
                (mp.Queue | None): Output queue (multiprocessing.Queue) of a service. Returns None if service_id validation failed queue does not exist.
        """
        if self.validate_service_id(service_id) is False:
            return None
        try:
            return self.srv_queues[service_id][1]
        except IndexError:
            return None

    def get_service_input_queue(self, service_id: int) -> Union[mp.Queue, None]:
        """Get service input queue. Direct access to service queue. Use with caution!

            Args:
                service_id (int): ID of service which input queue should be returned.

            Returns:
                (mp.Queue | None): Input queue (multiprocessing.Queue) of a service. Returns None if service_id validation failed queue does not exist.
        """
        if self.validate_service_id(service_id) is False:
            return None
        try:
            return self.srv_queues[service_id][0]
        except IndexError:
            return None

    @functools.lru_cache(maxsize=1)
    def get_services(self) -> list[tuple]:
        """Get initialized services.

            Returns:
                (list[tuple]): List of tuples with services: [(service1_id, service1_name), ...]
        """
        return [(srv_id, srv_name) for srv_id, srv_name in enumerate(self.srv_names)]

    @functools.lru_cache(maxsize=1)
    def get_groups(self) -> list[tuple]:
        """Get available groups with services.

            Returns:
                (list[tuple]): List of tuples with groups and belonging services: [(group1_name, [service1_id, service2_id, ...]), ...]
        """
        group_names = set()
        for srv in self.srv_immutables:
            for group_name in srv.groups:
                group_names.add(group_name)
        output = []
        for group_name in group_names:
            output.append((group_name, self.get_group_services(group_name)))
        return output

    @functools.lru_cache(maxsize=1)
    def get_services_more(self) -> list[tuple]:
        """Get initialized services more information.

            Returns:
                (list[tuple]): List of tuples with services: [(srv_id, srv_name, srv_description, srv_groups), ...]
        """
        return [(srv.service_id, srv.name, srv.description, srv.groups) for srv in self.srv_immutables]

    @functools.lru_cache(maxsize=1)
    def get_num_services(self) -> int:
        """Get number of all services.

            Returns:
                (int): Number of all initialized services.
        """
        return len(self.srv_names)

    def get_num_running_services(self) -> int:
        """Get number of running services.

            Returns:
                (int): Number of running services.
        """
        num = 0
        for run in self.srv_running:
            if run.value is True:
                num += 1
        return num

    # @functools.lru_cache(maxsize=CACHE_SIZE)
    """Bug when using lru_cache: two request to same group_name get_group_services() first time returns correctly
    but on second request (with the same argument) returns [] """
    def get_group_services(self, group_name: str, key_sensitive: bool = True) -> list[tuple]:
        """Get services belonging to the group.
        
            Args:
                group_name (str): Group name which services should be returned.
                key_sensitive(bool): Whether to be key sensitive

            Returns:
                (list[tuple]): List of tuple services [(service1_id, service1_name),  ...)]
        """
        group_services = []
        if not isinstance(group_name, str):
            self.logger.debug(f"ServiceManager: Invalid group_name: {group_name} entered.")
            return group_services
        if key_sensitive is True:
            for srv_id, srv_name in enumerate(self.srv_names):
                if group_name in self.srv_immutables[srv_id].groups:
                    group_services.append((srv_id, srv_name))
        else:
            for srv_id, srv_name in enumerate(self.srv_names):
                if group_name.lower() in [g.lower() for g in self.srv_immutables[srv_id].groups]:
                    group_services.append((srv_id, srv_name))
        return group_services

    def get_service_threads(self, service_id: int) -> list:
        """Get list of names of service threads.

            Args:
                service_id (int): ID of service which threads should be listed.

            Returns:
                (list[tuple]): List of thread names. Empty list if there are no threads or service_id validation failed.
        """
        if self.validate_service_id(service_id) is False:
            return []
        return [thread.name for thread in th.enumerate() if self._is_th_proc_name(service_id, thread.name)]

    def get_service_processes(self, service_id: int) -> list:
        """Get list of names of service processes.

            Args:
                service_id (int): ID of service which processes should be listed.

            Returns:
                (list[tuple]): List of process names. Empty list if there are no processes or service_id validation failed.
        """
        if self.validate_service_id(service_id) is False:
            return []
        return [process.name for process in mp.active_children() if self._is_th_proc_name(service_id, process.name)]

    def get_running(self) -> list[bool]:
        """Get list of running/not running services.

            Returns:
                (list[bool]): list of booleans indicating which services are running or not running.
        """
        return [value.value for value in self.srv_running]

    def get_service_id(self, service_name: str) -> Union[int, None]:
        """Convert service name to service ID.

            Returns:
                (int | None): Service ID of a given service name. None if there is not such a service.
        """
        if not isinstance(service_name, str):
            self.logger.debug(f"ServiceManager: Invalid service_name: {service_name} entered.")
            return None

        for srv_id, srv_name in enumerate(self.srv_names):
            if service_name == srv_name:
                return srv_id
        return None

    @functools.lru_cache(maxsize=CACHE_SIZE)
    def get_service_groups(self, service_id: int) -> Union[list[str], None]:
        """Get list of group which is given service member.

            Args:
                service_id (int): ID of service which groups should be listed.

            Returns:
                (list[str] | None): List of service groups.
        """
        if self.validate_service_id(service_id) is False:
            return None
        return self.srv_immutables[service_id].groups

    @functools.lru_cache(maxsize=CACHE_SIZE)
    def get_service_info(self, service_id: int) -> Union[dict, None]:
        """Get static information about service.

            Args:
                service_id (int): ID of service which info should be listed.

            Returns:
                (dict | None): Dictionary with service info. None if service does not exist.
        """
        if self.validate_service_id(service_id) is False:
            return None
        return self.srv_immutables[service_id].get_info()

    def get_service_running_info(self, service_id: int) -> Union[dict, None]:
        """Get running information about service.

            Args:
                service_id (int): ID of service which info should be listed.

            Returns:
                (dict | None): Dictionary with service running info. None if service does not exist.
        """
        if self.validate_service_id(service_id) is False:
            return None
        return {"service_id": service_id,
                "running": self.srv_running[service_id].value,
                "threads": self.get_service_threads(service_id),
                "processes": self.get_service_processes(service_id),
                "input queue length": self.srv_queues[service_id][0].qsize(),
                "output queue length": self.srv_queues[service_id][1].qsize(),
                "pending requests": len(self.request_dicts[service_id])}

    def get_services_running_info(self) -> dict:
        """Get running information about all service.

            Returns:
                (dict): Dictionary with running info of all services.
        """
        run_info = {}

        for srv_id, srv_name in enumerate(self.srv_names):
            run_info[srv_name] = self.get_service_running_info(srv_id)
        return run_info

    @functools.lru_cache(maxsize=1)
    def get_services_info(self) -> dict:
        """Get static information about all service.

            Returns:
                (dict): Dictionary with static info of all services.
        """
        # It is cached because it cannot change at runtime.
        info = {}

        for srv_id, srv_name in enumerate(self.srv_names):
            info[srv_name] = self.get_service_info(srv_id)
        return info
