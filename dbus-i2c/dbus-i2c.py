#!/usr/bin/env python

# Copyright (c) 2021 LHardwick-git
# Licensed under the BSD 3-Clause license. See LICENSE file in the project root for full license information.
#
# takes data from the i2c and adc channels (which are not used by venus) and publishes the data on the bus.


#  added engine hours metering add the following
#                                   MbOption { description: qsTr("Hours"); value: 4 }
#   in PagePulseCounterSetup.qml   **** dont forget the comma on the line before
#                        description: qsTr("Reset counter")
#                        value: itemCount.value.toFixed(1)
#                        editable: true
#                        onClicked: {
#                                itemCount.setValue(0)
#                        }
#   change to ->         property variant units: ["m<sup>4</sup>", "L", "gal", "gal", "Hours"]
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
# from w1thermsensor import W1ThermSensor
# Import i2c interface driver, this is a modified library stored in the same directory as this file
from i2c import AM2320 as AM2320
from ads1015 import ADS1015
# sourced wget https://raw.githubusercontent.com/pimoroni/ads1015-python/master/library/ads1015/__init__.py 


# our own packages
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-modem'))
from vedbus import VeDbusService, VeDbusItemExport, VeDbusItemImport 
from settingsdevice import SettingsDevice  # available in the velib_python repository

dbusservice = None

#=========================================
#  added ads1015 initialisation and resetting
#   basically the bits the modeul does not do for us

ads1015 = ADS1015()
#ads1015.channels = ['in0/gnd','in1/gnd','in2/gnd','in3/gnd']
ads1015.channels = ['in0/gnd']
ads1015.offset =  0.002
ads1015.multiplier = 9.12/0.9
ads1015.debug = True
WASTE_FLUIDS = ( 2, 5)

am2320 = AM2320(1)
am2320.debug = False

def device_detect(device):
    global chip_type
    try:
        chip_type = device.detect_chip_type()
    except IOError as e: 
        print ("unable to detect device", e)
        return False
    return chip_type

def analogue_reset(device,chip_type):
    print("Found: {}".format(chip_type))
    device.set_mode('single')
    device.set_programmable_gain(2.048)
    if chip_type == 'ADS1015':
        device.set_sample_rate(1600)
    else:
        device.set_sample_rate(860)
    reference = device.get_reference_voltage()
    print("Reference voltage: {:6.3f}v \n".format(reference))

# Test if the analogue chip is found on the bus and if it is then ititialise it.
chip_type = device_detect(ads1015)
if chip_type:
   analogue_reset(ads1015, chip_type)

#==================================================

def update():
# Calls to update ADC and I2C interfaces have been commented out
# The is in case someone runes this who does not know what they are doing 
# and does not have i2c devices and/or does not want or have the extra ADC channels.
# I have left the code in in case you wanton enable them
#
# So the only service left running is the Raspberry pi CPU temperature.
#
     update_am2320()
     update_ads1015()
     return True

# update i2c am2320 interface values
#  ***********************************************************************************
#  *   this all needs changing for the case where the i2c bus is there but no AM2320 *
#  ***********************************************************************************
def update_am2320():
    if not os.path.exists('/dev/i2c-1'):
        if dbusservice['i2c-temp']['/Connected'] != 0:
            logging.info("i2c-temperature  device disconnected")
            dbusservice['i2c-temperature']['/Connected'] = 0
        logging.info("i2c bus not available")
    else:
        (t,h,e, report) = am2320.readSensor()
#       Returns temperature, humidity, error status, and text report
        if e != 0:
            logging.info("Error in i2c-temperature bus read, "+ report)
            dbusservice['i2c-temp']['/Status'] = e
            dbusservice['i2c-temp']['/Temperature'] = []
        else:
             if dbusservice['i2c-temp']['/Connected'] != 1:
                logging.info("i2c-temperature AM2320 bus device connected")
                dbusservice['i2c-temp']['/Connected'] = 1
                dbusservice['i2c-temp']['/Status'] = 0
             if am2320.debug:
                 logging.info("values now are temperature %s, humidity %s" % (t, h))
             dbusservice['i2c-temp']['/Temperature'] = t
             dbusservice['i2c-temp']['/Humidity'] = h

def calculate_level( value, min=0, max=100):
#   Returns % level 
    try:
        return 100 * (value - min) / (max - min)
    except ZeroDivisionError:
        return 0

def calculate_remaining (percent, capacity, type=0):
    if type in  WASTE_FLUIDS:
        return capacity * ( 1 - percent/100)
    else:
        return capacity * percent/100

def update_ads1015():
    if ads1015.debug:
        logging.info("updating ads1015 values")
    tank_object = dbusservice['adc-tank1']
    for channel in ads1015.channels:
           if chip_type:
               try:
                   voltage = ads1015.get_voltage(channel=channel)
                   voltage = max (0, voltage - ads1015.offset)
                   voltage = round (voltage * ads1015.multiplier, 2)
                   tank_object['/RawValue'] = voltage
#        Zero voltage or low volatage reading mean tank device has been switched off
                   if voltage > tank_object['/RawValueEmpty']/2:
                       if tank_object['/Connected'] != 1:
                           tank_object['/Connected'] = 1
                           logging.info("i2c-adc ads1015 bus device connected")
                       level = calculate_level(voltage, tank_object['/RawValueEmpty'], tank_object['/RawValueFull']) 
                       if ads1015.debug:
                           logging.info("Readings are channel %s voltage %s level %s" % (channel, voltage, level))
                       tank_object['/Level'] = level
                       tank_object['/Remaining'] = calculate_remaining (level, tank_object['/Capacity'], tank_object['/FluidType'])
                   else:
                       if tank_object['/Connected'] != 0:
                           tank_object['/Connected'] = 0
                           logging.info("i2c-adc ads1015 is disconnected or low voltage")
               except IOError as e:
                   if ads1015.debug: 
                       logging.info("Unable to read value, with error %s" % (e))
           else:
               logging.info("i2c-adc ads1015 is disconnected")
               tank_object['/Connected'] = 0

def update_remote():
#   this is a stub to test collecting readings from remote json interface
    base = 'http://192.168.1.176:8080'
    action = '/ping-temp'
    try:
        with urllib.request.urlopen(base+action) as page:
            logging.info(page.read())
    except Exception as e:
            logging.info(str(e))


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

#***************************************************************************
#         This is in the wrong place as setting are used by multiple services
#        It should not be up to the setting device to define what the default is
#         It should be in the service definition
#***************************************************************************


#  Default settings triplets are the default value and the minimum and maximum values permitted.
settingDefaults = {'/Offset': [0, -10, 10],
                   '/Scale'  : [1.0, -5, 5],
                   '/TemperatureType'   : [0, 0, 3],
                   '/CustomName'        : ['fred', 0, 0],
                   '/FluidType'         : [0, 0, 6],
                   '/RawValueEmpty'     : [4, 0, 5],
                   '/RawValueFull'	: [9, 0, 10],
                   '/Capacity'          : [1.0, -10,  10],
                   '/Standard'          : [0, 0, 3]
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
    logging.info('Setting changed, setting: %s, old: %s, new: %s' % (setting, oldvalue, newvalue))
    [path, object] = settingObjects[setting]
    try:
        object[path] = newvalue
    except:
        logging.info(" no localpath to store "+ str(settings[setting]))
    return True

# Add setting is called each time a new service path is created that needs a persistent setting
# If the setting already exists the existing recored is unchanged
# If the setting does not exist it is created when the serviceDevice object is created
def addSetting(base, path, dBusObject):
    global settingObjects
    global newSettings
    global settingDefaults
    setting = (base + path)
    logging.info(" ".join(("Add setting", setting, str(settingDefaults[path]) )) )
    settingObjects[setting] = [path, dBusObject]             # Record the dBus Object and path for this setting 
    newSettings[setting] = [setting] + settingDefaults[path] # Add the setting to the list to be created

# initSettings is called when all the required settings have been added
def initSettings(newSettings):
    global settings

#   settingsDevice is the library class that handles the reading and setting of persistent settings
    settings = SettingsDevice(
        bus=dbus.SystemBus() if (platform.machine() == 'armv7l') else dbus.SessionBus(),
        supportedSettings = newSettings,
        eventCallback     = handle_changed_setting)

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
            logging.info(" no localpath to store "+ str(settings[setting]))

# =========================== end of settings interface ======================

class SystemBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)

class SessionBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)

def dbusconnection():
    return SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else SystemBus()


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

    # Create device type specific objects, snd set values to empty until connected
    if settingId :
        setting = "/Settings/" + type.capitalize() + "/" + str(settingId)
    else:
        logging.info('No Setting required for ' + type.capitalize() + "/" + str(settingId))
        setting = "" 

    if type == 'temperature':
        self.add_path('/Temperature', [])
       	self.add_path('/Status', 0)
        if settingId:
            addSetting(setting , '/TemperatureType', self)
            addSetting(setting , '/CustomName', self)
       	self.add_path('/TemperatureType', 0, writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y) )
        self.add_path('/CustomName', '', writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y) )
        self.add_path('/Function', 1, writeable=True )

    if type == 'humidity':
        self.add_path('/Humidity', [])
        self.add_path('/Status', 0)

    if type == 'tank':
        self.add_path('/RawUnit' , 'V')
        self.add_path('/RawValue' , 99)
        self.add_path('/Level', 0)
        self.add_path('/Remaining', 0)
        self.add_path('/Status', 0)

        if settingId:
            addSetting(setting, '/FluidType', self)
            addSetting(setting, '/Capacity', self)
            addSetting(setting, '/CustomName', self)
            addSetting(setting, '/RawValueEmpty', self)
            addSetting(setting, '/RawValueFull', self)
            addSetting(setting, '/Standard', self)
            self.add_path('/FluidType', 0,   writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y) )
            self.add_path('/Capacity', 10,  writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y) )
            self.add_path('/CustomName', '', writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y) )
            self.add_path('/RawValueEmpty', 3, writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y) )
            self.add_path('/RawValueFull', 9, writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y) )
            self.add_path('/Standard', 0, writeable=True, onchangecallback = lambda x,y: handle_changed_value(setting,x,y) )

    return self

dbusservice = {} # Dictionary to hold the multiple services

base = 'com.victronenergy'

# Init setting - create setting object to read any existing settings
# Init is called again later to set anything that does not exist
# this gets round the Chicken and Egg bootstrap problem,

# service defined by (base*, type*, connection*, logial, id*, instance, settings ID):
# The setting iD is used with settingsDevice library to create a persistent setting
# Items marked with a (*) are included in the service name
#
# I have commented out the bits that will make new services for i2C and ADC services here
# If you want to re-enable these you need to uncomment the right lines

dbusservice['i2c-temp']     = new_service(base, 'temperature', 'i2c',      'i2c Device 1',  0, 25, 7)

dbusservice['i2c-temp']    ['/ProductName']     = 'Encased i2c AM2315t'

# Adding the humidity reading to the temperature object works in Venus 2.8
dbusservice['i2c-temp'].add_path('/Humidity', [])


# Tidy up custom or missing items

dbusservice['adc-tank1']     = new_service(base, 'tank', 'ADS1015_v1',  'Analogue voltage 1',  0, 30, 7)

# Persistent settings obejects in settingsDevice will not exist before this is executed
initSettings(newSettings)
# Do something to read the saved settings and apply them to the objects
readSettings(settingObjects)

# Do a first update so that all the readings appear.
update()
# update every 10 seconds - temperature and humidity should move slowly so no need to demand
# too much CPU time
#
gobject.timeout_add(10000, update)

print('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
mainloop = gobject.MainLoop()
mainloop.run()

