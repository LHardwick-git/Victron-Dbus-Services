#!/usr/bin/env python

# Copyright (c) 2021 LHardwick-git
# Licensed under the BSD 3-Clause license. See LICENSE file in the project root for full license information.
#
# takes data from the i2c and adc channels (which are not used by venus) and publishes the data on the bus.


#  added engine hours metering add the following
#                                   MbOption { description: qsTr("Hours"); value: 4 }
#   in PagePulseCounterSetup.qml   **** dont forget the comma on the line before
#   change to ->         property variant units: ["m<sup>4</sup>", "L", "gal", "gal", " Hours"]
#   change decimals on the agregate output form 0 to 1 #
#   in PagePulseCounter.qml (change 3 to 4 and add hours)


# If edditing then use 
# svc -d /service/dbus-i2c and
# svc -u /service/dbus-i2c
# to stop and restart the service 

from dbus.mainloop.glib import DBusGMainLoop
import sys
if sys.version_info.major == 2:
    import gobject
    from gobject import idle_add
else:
    from gi.repository import GLib as gobject
import dbus
import dbus.service
import inspect
import platform
from threading import Timer
import argparse
import logging
import sys
import os
import urllib.request

from pprint import pprint


# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-modem'))
from vedbus import VeDbusService, VeDbusItemExport, VeDbusItemImport 
from settingsdevice import SettingsDevice  # available in the velib_python repository

def update():
#
    update_engine()
    return True

def update_engine():
#   only increment time if the service is configured as connected by setting it as a pulse counter
    if dbus_engine['/Connected'] == 1:
        incremented = round(((settings['/Settings/DigitalInput/6/Aggregate'] * 100) +1 )/100,2)
#       This increments the setting which comes via the callback to update the service copy
#       so no need to update it twice
        
        settings['/Settings/DigitalInput/6/Aggregate'] = incremented
        settings['/Settings/DigitalInput/6/Count'] += 0.01

# enable us to read settings raw (not through interfce)

class SystemBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)

class SessionBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)

def dbusconnection():
    return SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else SystemBus()

DBusGMainLoop(set_as_default=True)
dBusConn = dbus.SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else dbus.SystemBus()

serviceSettings  = VeDbusItemImport(dBusConn, "com.victronenergy.settings" , "/Settings/DigitalInput/6").get_value()

# =========================== Start of settings interface ================
#  The settings interface handles the persistent storage of changes to settings
#  This should probably be created as a new class extension to the settingDevice object
#  The complexity is because this python service handles temperature and humidity
#  Data for about 6 different service paths so we need different dBusObjects for each device
#
newSettings = {}     # Used to gather new settings to create/check as each dBus object is created
settingObjects = {}  # Used to identify the dBus object and path for each setting
                     # settingsObjects = {setting: [path,object],}
                     # each setting is the complete string e.g. /Settings/Temperature/4/Scale

#********************************************************************************
#   It is a stange feature of settings that default values are passed into settings
#   which will overwrite the stored setting. (I have not found how to fix this?)
#*******************************************************************************


#  Default settings triplets are the default value and the minimum and maximum values permitted.
settingDefaults = {'/CustomName'        : ['Engine Hours', 0, 0],
                   '/InvertAlarm'       : [0, 0, 1],
                   '/InvertTranslation' : [0, 0, 1],
                   '/Type'              : [1, 0, 6],
                   '/Multiplier'        : [0.001, 0, 10],
                   '/AlarmSetting'      : [0, 0, 1],
                   '/Count'             : [1.1, 0, 300000],
                   '/Aggregate'         : [0.0, 0, 100000]
                   }

# Values changed in the GUI need to be updated in the settings
# Without this changes made through the GUI change the dBusObject but not the persistent setting
# (as tested in venus OS 2.54 August 2020)
def handle_changed_value(setting, path, value):
    global settings
    print("some value changed")
    # The callback to the handle value changes has been modified by using an anonymouse function (lambda)
    # the callback is declared each time a path is added see example here
    # self.add_path(path, 0, writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y) )
    logging.info(" ".join(("Storing change to setting", setting+path, str(value) )) )
    settings[setting+path] = value
    return True

# Changes made to settings need to be reflected in the GUI and in the running service
def handle_changed_setting(setting, oldvalue, newvalue):
    change_setting = setting.split("/")[-1]   # extract leaf name
#   if change_setting != "Aggregate":#
    if change_setting not in ("Aggregate","Count"):
#       Avoid cloging the logs with changes every 36 seconds (but report other changes)
        logging.info('Setting changed, setting: %s, old: %s, new: %s' % (setting, oldvalue, newvalue))
    if change_setting == "Type":
        if newvalue == 1:
            dbus_engine['/Connected'] = 1
            logging.info('Engine counting service started by configuration change')
        else:
            dbus_engine['/Connected'] = 0
            logging.info('Engine counting halted by configuration change')
#   The method of storage in an ojects list is a hangover from bigger constructs handling multiple services 
    [path, object] = settingObjects[setting]
    try:
        object[path] = newvalue
    except:
        logging.info(" no localpath to store changed setting to "+ str(settings[setting]))
    return True

# Add setting is called each time a new service path is created that needs a persistent setting
# If the setting already exists the existing recored is unchanged
# If the setting does not exist it is created when the serviceDevice object is created
def addSetting(base, path, dBusObject):
    global settingObjects
    global newSettings
    global settingDefaults
    setting = (base + path).replace('Pulsemeter', 'DigitalInput') # Strangly the confiiguration for the pulse meter is "DigitalInput"
    if path in serviceSettings:
        logging.info("Setting alrady exists for "+path)
    else:
        logging.info(" ".join(("Add setting", setting, str(settingDefaults[path]) )) )
        newSettings[setting] = [setting] + settingDefaults[path] # Add the setting to the list to be created
    settingObjects[setting] = [path, dBusObject] 

# initSettings is called when all the required settings have been added
def initSettings(newSettings):
    global settings

#   settingsDevice is the library class that handles the reading and setting of persistent settings
    settings = SettingsDevice(
        dbus.SystemBus() if (platform.machine() == 'armv7l') else dbus.SessionBus(),
        newSettings,
        handle_changed_setting)

# readSettings is called after init settings to read all the stored settings and
# set the initial values of each of the service object paths
# Note you can not read or set a setting if it has not be included in the newSettings
#      list passed to create the new settingsDevice class object

def readSettings(list):
    global settings
    for setting in list:
        [path, object] = list[setting]
        logging.info(" ".join(("Retreived setting", setting, path, str(settings[setting]))))
        try:
            object[path] = settings[setting]
        except:
            logging.info("  ".join(("No localpath to store ", setting, str(settings[setting]))))

# =========================== end of settings interface ======================

# Argument parsing removed from source as never used 
class args: pass
args.debug = False
#args.debug = True

# Init logging
logging.basicConfig(level=(logging.DEBUG if args.debug else logging.INFO))
logging.info(__file__ + " is starting up")
logLevel = {0: 'NOTSET', 10: 'DEBUG', 20: 'INFO', 30: 'WARNING', 40: 'ERROR'}
logging.info('Loglevel set to ' + logLevel[logging.getLogger().getEffectiveLevel()])

# Have a mainloop, so we can send/receive asynchronous calls to and from dbus
DBusGMainLoop(set_as_default=True)

def new_service(base, type, physical, logical, id, instance, settingId = False):
#    self =  VeDbusService("{}.{}.{}_id{:02d}".format(base, type, physical,  id), dbusconnection())
    self =  VeDbusService("{}.{}.{}{:02d}".format(base, type, physical,  id), dbusconnection())
    # physical is the physical connection 
    # logical is the logical connection to allign with the numbering of the console display
    # Create the management objects, as specified in the ccgx dbus-api document
    self.add_path('/Mgmt/ProcessName', __file__)
    self.add_path('/Mgmt/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
    self.add_path('/Mgmt/Connection', logical)

    # Create the mandatory objects, note these may need to be customised after object creation
    self.add_path('/DeviceInstance', instance)
    self.add_path('/ProductId', 0)
    self.add_path('/ProductName', '')
    self.add_path('/FirmwareVersion', 0)
    self.add_path('/HardwareVersion', 0)
    self.add_path('/Connected', 0)  # Mark devices as disconnected until they are confirmed

    # Create device type specific objects set values to empty until connected
    if settingId :
        setting = "/Settings/" + type.capitalize() + "/" + str(settingId)
    else:
        logging.info('No Setting required for ' + type.capitalize() + "/" + str(settingId))
        setting = "" 

    if type == 'pulsemeter':
       	self.add_path('/Aggregate',5000.0, writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y))
        self.add_path('/Count', 0,writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y))
        if settingId:
            addSetting(setting, '/CustomName', self)
            addSetting(setting, '/Aggregate', self)    # to store engine hours persistently over restart
            addSetting(setting, '/InvertAlarm', self)
            addSetting(setting, '/Multiplier', self)
            addSetting(setting, '/Type', self)
            addSetting(setting, '/InvertTranslation', self)
            addSetting(setting, '/AlarmSetting', self),
            addSetting(setting, '/Count', self),
            self.add_path('/CustomName', 'Engine Hours', writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y))

    return self

base = 'com.victronenergy'

# Init setting - create setting object to read any existing settings
# Init is called again later to set anything that does not exist
# this gets round the Chicken and Egg bootstrap problem,

# service defined by (base*, type*, connection*, logial, id*, instance, settings ID):
# The setting iD is used with settingsDevice library to create a persistent setting
# Items marked with a (*) are included in the service name
#
#  trying to make a pulsemeter work delete this and other lines if necessary  to give up
dbus_engine = new_service(base, 'pulsemeter', 'input', 'DC system generation', 6, 6, 6)
dbus_engine['/CustomName'] = 'Engine Hours'

# Persistent settings obejects in settingsDevice will not exist before this is executed
initSettings(newSettings)
# Do something to read the saved settings and apply them to the objects
#pprint(settingObjects)
readSettings(settingObjects)

if settings['/Settings/DigitalInput/6/Type'] == 1:
    dbus_engine['/Connected'] = 1
    logging.info('Service enabled by configuration and running')
else:
    dbus_engine['/Connected'] = 0
    logging.info('Service dissabled by configuration')
 
# Do a first update so that all the readings appear.
update()
# update every 36 seconds 1/100h- so should catch granularity of engine starts/stops to about a minute
#
gobject.timeout_add(36000, update)

print('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
mainloop = gobject.MainLoop()
mainloop.run()
