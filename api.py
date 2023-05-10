# api.py requires packages: fastapi, uvicorn
import os
from typing import Union
from fastapi import FastAPI, Request, Depends
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRouter
from pydantic import BaseModel

import database

tags_metadata: list = [
    {
        "name": "Info",
        "description": "Information endpoints for retrieving information about services, groups, etc.",
    },
    {
        "name": "Commands",
        "description": "Endpoints for sending commands to the server.",
    },
    {
        "name": "Get",
        "description": "Endpoints for requests.",
    },
    {
        "name": "Index",
        "description": "Endpoint for serving web client.",
    },
    {
        "name": "Tokens",
        "description": "Endpoint for token addition and deletion.",
    }
]
description: str = """
Flexible information searching and transformation tool. 
Lookup whois, Shodan, VirusTotal, passive DNS, etc. about domain or IP address. 
Compute hashes of input, punycode conversions other transformations. 
Easily implement your custom services which can be accessed by provided web client, Splunk client, 
Python client or by universal API.

**To use this tool you have to have authentication token. If you do not have have please contact the administrator.**
"""
license_info = {"name": "GPLv3", "url": "https://www.gnu.org/licenses/gpl-3.0.en.html"}
contact = {
        "name": "Petr Stovicek",
        "url": "https://github.com/Stovka/dpv5",
        "email": "petrstovicek1@gmail.com",
    }
with open("version.txt") as file:
    version = file.read()
app = FastAPI(title="Fistop",
              version=version,
              description=description,
              license_info=license_info,
              contact=contact,
              openapi_tags=tags_metadata)
api_router = APIRouter()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Do not modify! Use settings/config.ini
db: Union[None, database.DatabaseManager] = None
ALLOW_HEADER_TOKEN: bool = True
ALLOW_PARAMETER_TOKEN: bool = True
ALLOW_COOKIE_TOKEN: bool = True
ALLOW_WEB_CLIENT: bool = True
INDEX: str = "web_client/build/index.html"
STATIC_FILES: str = "web_client/build/"  # Relative path
STATIC_FILES_ABS: str = os.path.realpath(STATIC_FILES)  # Absolute path


# API ##################################################################################################################
def get_token(request: Request, token: str = "") -> str:
    # Header token
    if ALLOW_HEADER_TOKEN is True:
        header_token = request.headers.get("token")
        if header_token is not None:
            if header_token != "null":  # Javascript None
                return header_token

    # Parameter token
    if ALLOW_PARAMETER_TOKEN is True and token != "":
        return token

    # Cookie token
    if ALLOW_COOKIE_TOKEN:
        try:
            cookie_token = request.cookies["token"]
            if cookie_token != "null":
                return cookie_token
        except KeyError:
            pass
    # Always return at least empty token
    return ""


# GET
# User/Admin endpoints
@api_router.get("/server/info/services/", tags=["Info"])
def info_services(token: str = Depends(get_token)):
    return db.get_services_info(token)


@api_router.get("/server/info/services2/", tags=["Info"])
def info_services2(token: str = Depends(get_token)):
    return db.get_services_info_more(token)


@api_router.get("/server/info/groups/", tags=["Info"])
def info_groups(token: str = Depends(get_token)):
    return db.get_groups_info(token)


# Admin endpoints
@api_router.get("/server/info/tokens/", tags=["Info"])
def info_tokens(token: str = Depends(get_token)):
    return db.get_tokens_info(token)


@api_router.get("/server/info/server/", tags=["Info"])
def info_server(token: str = Depends(get_token)):
    return db.get_server_info(token)


@api_router.get("/server/info/version/", tags=["Info"])
def info_version(token: str = Depends(get_token)):
    return db.get_server_version(token)


@api_router.get("/server/start/", tags=["Commands"])
def start_services(token: str = Depends(get_token)):
    return db.get_start(token)


@api_router.get("/server/stop/", tags=["Commands"])
def stop_services(token: str = Depends(get_token)):
    return db.get_stop(token)


@api_router.get("/server/restart/", tags=["Commands"])
def restart_services(token: str = Depends(get_token)):
    return db.get_restart(token)


@api_router.get("/server/reload_tokens/", tags=["Commands"])
def reload_tokens(token: str = Depends(get_token)):
    return db.get_reload_tokens(token)


# PUT
class TokensModel(BaseModel):
    group: str = ""
    group_services: list = []
    user: str = ""
    user_services: list = []
    superuser: str = ""
    admin: str = ""


@api_router.put("/server/tokens/", tags=["Tokens"])
def put_tokens(data: TokensModel, token: str = Depends(get_token)):
    return db.put_tokens(data.dict(), token)


# DEL
@api_router.delete("/server/tokens/", tags=["Tokens"])
def del_tokens(data: TokensModel, token: str = Depends(get_token)):
    return db.del_tokens(data.dict(), token)


# GET
# User endpoints
# curl -X GET http://127.0.0.1/api/v1/0/8.8.8.8?token=yourtoken -H "accept: application/json"
@api_router.get("/{group_service}/{request:path}", tags=["Get"])
def get(group_service: str, request: str, token: str = Depends(get_token)):
    # This serves both groups and services IDs, path is here so it accepts slashes
    return db.get_group(group_service, request, token)


# curl -X POST http://127.0.0.1/api/v1/0/?token=yourtoken -H "accept: application/json" -H "Content-Type: application/json" -d "[\"8.8.8.8\",\"8.8.4.4\"]"
@api_router.post("/{group_service}/", tags=["Get"])
def get_list(group_service: str, requests: list[str], token: str = Depends(get_token)):
    # This serves both groups and services IDs
    return db.get_group_list(group_service, requests, token)


app.include_router(api_router, prefix="/api/v1")


# Web App ##############################################################################################################
@app.get("/{request:path}", response_class=FileResponse, tags=["Index"])
def index(request):
    if ALLOW_WEB_CLIENT is False:
        return Response("", status_code=403)
    file_path = os.path.realpath(STATIC_FILES + request)
    if os.path.commonpath([STATIC_FILES_ABS, file_path]) != STATIC_FILES_ABS:
        # Path traversal protection
        return Response("", status_code=403)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    return FileResponse(INDEX, media_type="text/html")


# FastAPI ##############################################################################################################
@app.on_event("startup")
async def startup_event():
    pass


@app.on_event("shutdown")
async def shutdown_event():
    global db
    db.shutdown()
