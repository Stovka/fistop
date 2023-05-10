

## Installation

```sh
mv splunk_client /opt/splunk/etc/apps/splunk-fistop-app

cd /opt/splunk/etc/apps/splunk-fistop-app/bin
pip install -t . splunk-sdk
```
or download splunklib directory from https://github.com/splunk/splunk-sdk-python and copy to bin/

## Change permissions
Splunk > Apps > Manage Apps >
splunk-fistop-app > Permissions > Sharing for config file-only objects > All apps
```sh
chown -R splunk /opt/splunk/etc/apps/splunk-fistop-app/
chgrp -R splunk /opt/splunk/etc/apps/splunk-fistop-app/
```

## Restart Splunk
```sh
/opt/splunk/bin/splunk restart
```


## Configuration
```sh
vi /opt/splunk/etc/apps/splunk-fistop-app/default/fistop.conf
```

```
host = http://10.8.66.66
port = 80
token = yoursecrettoken
```