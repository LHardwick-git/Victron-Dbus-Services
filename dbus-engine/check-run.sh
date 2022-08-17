#! /bin/sh

if ! pgrep -f "dbus-engine.py" >/dev/null; then
    echo "process not found"
  else
    echo "process running"
  fi
    exit 0
    