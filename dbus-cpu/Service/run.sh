#!/bin/sh
exec 2>&1
exec softlimit -d 100000000 -s 1000000 -a 100000000 /opt/victronenergy/dbus-cpu/dbus-cpu.py