#! /bin/sh

if ! pgrep -f "dbus-i2c.py" ; then
    echo "process not found"
  else
    echo "process running"
  fi
#    exit 0
#fi

#if ! test -e /dev/gpio/digital_input_1/edge; then
#    flags=--poll=poll
#fi

#exec $(dirname $0)/dbus-i2c.py
