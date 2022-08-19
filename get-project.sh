#!/bin/sh
#
# Take this file and copy it to your Venus GX device (Mine is Raspberry Pi)
# For example you can do that by :
# nano get-project.sh
# Cut and past this text into the nano window
# CTRL o to save the file
# CTRL x to exit nano
# chmod +x get-project.sh
# 
# Then run this file.
# ./get-project.sh
# All the files from this repository will be downloaded and the execute permissions
# will be set on the files that need to be executable.
# 
# Instructions or options to install the services will be added here 
#
wget https://github.com/LHardwick-git/Victron-Dbus-Services/archive/master.zip
unzip -q master.zip
mv Victron-Dbus-Services-main Victron-Dbus-Services 
rm master.zip
find . -name '*.sh' -type f -exec chmod +x {} +
find . -name 'run' -type f -exec chmod +x {} +
find . -name '*.py' -type f -exec chmod +x {} +
chmod u+x Victron-Dbus-Services/Rpi-GPS-time/rc.local
