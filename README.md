# Eve-Discord-Authentication
An application your Eve alliance / corp can use to authenticate users on Discord.

## Installation
Download, install the Python prerequisites, and copy / edit the config:

```bash
$ git clone https://github.com/WizBoom/Eve-Discord-Authentication
$ cd Eve-Discord-Authentication
$ virtualenv env
$ . env/bin/activate
$ pip install -r requirements.txt
$ cp config.json.example config.json
```

Edit config.json file.

## Database.
If you do not have the correct database yet:

```bash
$ python create_database.py
```
