![Python 3.9](https://img.shields.io/badge/Python-3.9-green.svg)
![Centos 8](https://img.shields.io/badge/Centos-8-red.svg)
![Ubuntu 22.04](https://img.shields.io/badge/Ubuntu-22.04-red.svg)
![Windows 11](https://img.shields.io/badge/Windows-11-blue.svg)

# Fistop
Flexible information searching and transformation tool. 
Lookup whois, Shodan, VirusTotal, passive DNS, etc. about domain or IP address. 
Compute hashes of input, punycode conversions other transformations. 
Easily implement your custom services which can be accessed by provided web client,
Splunk client, Python client or by universal API.

## Requirements
### Software
- Python 3.9+
### Operating System
- Windows 10/11
- Centos 8
- Ubuntu 22.04
### Python Packages
- fastapi (web framework)
- uvicorn (HTTP server)
## Prerequisites
CentOS 8:
```
yum install -y epel-release
yum install -y python3-pip git
```
If you do not have Python or version is lower than 3.9. 
Then please install newer version according to tutorial: https://linuxstans.com/how-to-install-python-centos/

Ubuntu 22.04:
```
apt-get -y update
apt-get -y upgrade
apt-get install -y python3 python3-pip python3-venv git
```

Clone this repository
```
git clone https://www.github.com/Stovka/fistop
```
## Install
### 1. Create venv (Optional)
Venv Linux
```
cd fistop
python3 -m venv venv
source venv/bin/activate
```
Venv Windows
```
cd fistop
python -m venv venv
venv\Scripts\activate
```
### 2. Install Packages (fastapi, uvicorn)
```
pip install -r requirements.txt
```
## Run & Shutdown
```
python fistop.py
// Linux server
nohup python fistop.py &
// Or
nohup python fistop.py settings/custom_config.ini &
// Or
nohup /usr/local/bin/python3.9 fistop.py &
```
### Shutdown
Use _ctrl+c_ if you are running it from the console. Use _kill_ (_SIGINT_) when running it in the background. 
PID is process ID which is visible in every log message. 
```
kill -2 PID
```
## Docker Install & Run
### create image
```
cd fistop
docker build -t fistop .
```
### Run docker image
Run with mounted local folder. Allows file modification.
```
docker run -d --name docker-fistop --mount type=bind,source="$(pwd)",target=/app -p 80:80 docker-fistop
```
Run built image.
```
docker run -d --name docker-fistop -p 80:80 docker-fistop
```

## Configuration
### Via text:
```
cd fistop/settings/
-> config.ini
-> tokens.ini
-> services.py
```
To set logging to the file use:
```
vi settings/config.ini

db_logger_filename = logs/fistop.log
```

### Via web GUI
```
http://localhost/admin
```

## Web client development

```
cd fistop/web_client
npm install

npm run build
```