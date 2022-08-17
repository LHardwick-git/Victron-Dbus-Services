# Victron-Dbus-Services

I am refactoring all my Dbus services for Venus 2.8

In this repository you will find a number of Dbus services for Victron Venus OS.

This includes services for:

Native (or innate) data - such as the temperature of the CPU when running on an Rpi.
   Also a service for monitoring engine hours based on detected alternator output
i2C devices - such as voltage (including a tank level sensor), temperature and humidity.
1-wire devices - Temperature and Relay drivers.
Remote device support - data collected using a JSON data exchanges with a separate server.

This is all based on my original Venus Dbus Service
https://github.com/LHardwick-git/Victron-Service

Why the changes?

Venus has moved on and there are new features in Venus 2.8 for tanks, analogue interfaces etc.
That can be used by new code versions.

My Dbus-i2c service has become too big people just want to use portions of the code so buy
Separating out the different services you can install just the ones you need.

The additional adc Dbus services used to access the spare 3 analogue interfaces on an mcp3208 are no longer required
Venus OS now has the option to support the additional interfaces by modifying the /etc/venus/dbus-adc.conf file.

I'll add installation notes for Venus OS 2.8 as the installation of new services has changed from previous Venus versions.
      
Hope this all works for you
    
