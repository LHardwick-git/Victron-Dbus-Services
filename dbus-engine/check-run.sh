#! /bin/sh

if ! pgrep -f "dbus-engine.py" ; then
    echo "process not found"
  else
    echo "process running"
  fi
    exit 0
    
