#!/bin/bash
#add this line to /data/rc.local
#/data/gps-time.sh > /var/log/gps-date &
# This script read the GPS data from a USB connected dongle and sets the Rpi
# time and date from the GPS data received.

N=0;
FILE=/run/serial-starter/gps/ttyACM0
echo "Waiting for GPS data"
while [ ! -e $FILE ] && [ $N -lt 50 ];
do
    sleep 1;
    ((N++))
    echo -n "."
done;
sleep 5;

if [ $N -ge 17 ]; then
   echo " GPS data not available is the device plugged in"
   exit 0;
fi

echo
echo "Device attached waiting for data"

input=$FILE
N=0

# check if GPS has FIX
LINE1='^\$..GGA,[0-9\.]+,[0-9\.]+,[NS],[0-9\.]+,[EW],([0-2])'
# Catch lines with date and time info
LINE2='^\$..RMC'

FIX=""

# extract date and time from GPS packet

function extract {
[[ $1 =~ ^\$..RMC,([0-9]{4})([0-9]{2})\.[0-9]{2},.,[0-9\.]+,[NS],[0-9\.]+,[EW],[0-9\.]*,[0-9\.]*,([0-9]{2})([0-9]{2})([0-9]{2}), ]]
  echo "foound this"
  COMMAND="20${BASH_REMATCH[5]}${BASH_REMATCH[4]}${BASH_REMATCH[3]}${BASH_REMATCH[1]}.${BASH_REMATCH[2]}"
  echo command is $COMMAND
  date -s $COMMAND
exit 0
}

while IFS= read -r line && [ $N -lt 2000 ] 
do
#  echo "$line"
  [[ $line =~ $LINE1 ]] && FIX=${BASH_REMATCH[1]} && echo "GPS device has a fix after $N lines"
  [[ $line =~ $LINE2 ]] && [[ $FIX -eq 1 ]] && extract $line
  ((N++))
done < "$input"
echo "Timed out no date/time information in 2000 lines from GPS reciver" 