# fistop.py requires packages: fastapi, uvicorn
import logging
import os
import sys
import uvicorn

import api
import database
import utility


if __name__ == "__main__":
    # Overwrite config_file with command line argument if present.
    config_file = "settings/config.ini"
    if len(sys.argv) > 2:
        raise Exception("Invalid arguments")
    elif len(sys.argv) == 2:
        config_file = sys.argv[1]
    # Load user config
    config = utility.Config(file_config=os.path.normpath(config_file))
    # Add included directories into paths
    for directory in config.include_dirs:
        # This will not raise error if directory does not exist
        # Validation is done later in both DatabaseManager and ServiceManager
        sys.path.insert(0, directory)
    # Set token types
    api.ALLOW_HEADER_TOKEN = config.allow_header_token
    api.ALLOW_PARAMETER_TOKEN = config.allow_parameter_token
    api.ALLOW_COOKIE_TOKEN = config.allow_cookie_token
    api.ALLOW_WEB_CLIENT = config.serve_web_client
    # Create database object
    api.db = database.DatabaseManager(config)
    # Start uvicorn server
    if config.use_ssl is True:
        if not os.path.exists(os.path.normpath(config.ssl_key)) or \
                not os.path.exists(os.path.normpath(config.ssl_cert)):
            api.db.shutdown()
            raise utility.ConfigError(f"Cert file: {config.ssl_key} or {config.ssl_key} does not exist")
        uvicorn.run(
            api.app,
            host=config.uvicorn_listen,
            port=config.ssl_port,
            log_level=logging.ERROR,
            ssl_keyfile=os.path.normpath(config.ssl_key),
            ssl_certfile=os.path.normpath(config.ssl_cert),
            workers=config.uvicorn_workers)
    else:
        uvicorn.run(
            api.app,
            host=config.uvicorn_listen,
            port=config.port,
            log_level=logging.ERROR,
            workers=config.uvicorn_workers)
