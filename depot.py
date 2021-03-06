#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
##
## This file is part of Cockpit.
##
## Cockpit is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## Cockpit is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Cockpit.  If not, see <http://www.gnu.org/licenses/>.

## Copyright 2013, The Regents of University of California
##
## Redistribution and use in source and binary forms, with or without
## modification, are permitted provided that the following conditions
## are met:
##
## 1. Redistributions of source code must retain the above copyright
##   notice, this list of conditions and the following disclaimer.
##
## 2. Redistributions in binary form must reproduce the above copyright
##   notice, this list of conditions and the following disclaimer in
##   the documentation and/or other materials provided with the
##   distribution.
##
## 3. Neither the name of the copyright holder nor the names of its
##   contributors may be used to endorse or promote products derived
##   from this software without specific prior written permission.
##
## THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
## "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
## LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
## FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
## COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
## INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
## BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
## LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
## CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
## LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
## ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
## POSSIBILITY OF SUCH DAMAGE.


## This module serves as a central coordination point for all devices. Devices
# are initialized and registered from here, and if a part of the UI wants to 
# interact with a specific kind of device, they can find it through the depot.

import ast
import importlib
import os
from six import string_types, iteritems
from handlers.deviceHandler import DeviceHandler

## Different eligible device handler types. These correspond 1-to-1 to
# subclasses of the DeviceHandler class.
CAMERA = "camera"
CONFIGURATOR = "configurator"
DRAWER = "drawer"
EXECUTOR = "experiment executor"
GENERIC_DEVICE = "generic device"
GENERIC_POSITIONER = "generic positioner"
IMAGER = "imager"
LIGHT_FILTER = "light filter"
LIGHT_POWER = "light power"
LIGHT_TOGGLE = "light source"
OBJECTIVE = "objective"
POWER_CONTROL = "power control"
SERVER = "server"
STAGE_POSITIONER = "stage positioner"
DEVICE_FOLDER = 'devices'
THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))

SKIP_CONFIG = ['objectives', 'server']

class DeviceDepot:
    ## Initialize the Depot. Find all the other modules in the "devices" 
    # directory and initialize them.
    def __init__(self):
        self._configurator = None
        ## Maps device classes to their module
        self.classToModule = {}
        ## Maps config section names to device
        self.nameToDevice = {}
        ## Maps devices to their handlers.
        self.deviceToHandlers = {}
        ## Maps handlers back to their devices.
        self.handlerToDevice = {}
        ## List of all device handlers for active modules.
        self.handlersList = []
        ## Maps handler device types to lists of the handlers controlling that
        # type.
        self.deviceTypeToHandlers = {}
        ## Maps handler names to handlers with those names. NB we enforce that
        # there only be one handler per name when we load the handlers.
        self.nameToHandler = {}
        ## Maps group name to handlers.
        self.groupNameToHandlers = {}

    ## HACK: load any Configurator device that may be stored in a
    # "configurator.py" module. This is needed because config must be loaded
    # before any other Device, so that logfiles can be stored properly.
    def loadConfig(self):
        if self._configurator:
            return
        if os.path.exists(os.path.join(THIS_FOLDER,
                                       DEVICE_FOLDER,
                                       'configurator.py')):
            import devices.configurator
            self._configurator = devices.configurator.Configurator()
            self.initDevice(self._configurator)


    ## Call the initialize() method for each registered device, then get
    # the device's Handler instances and insert them into our various
    # containers. Yield the names of the modules holding the Devices as we go.
    def initialize(self, config):
        # Parse device files to map classes to their module.
        modfiles = [fn for fn in os.listdir(DEVICE_FOLDER) if fn.endswith('.py')]
        for m in modfiles:
            modname = m[0:-3] # Strip .py extension
            with open(os.path.join(DEVICE_FOLDER, m), 'r') as f:
                # Extract class definitions from the module
                try:
                    classes = [c for c in ast.parse(f.read()).body
                                    if isinstance(c, ast.ClassDef)]
                except Exception as e:
                    raise Exception("Error parsing device module %s.\n%s" % (modname, e))

            for c in classes:
                if c.name in self.classToModule.keys():
                    raise Exception('Duplicate class definition for %s in %s and %s' %
                                    (c.name, self.classToModule[c.name], modname))
                else:
                    self.classToModule[c.name] = modname

        # Create our server
        import devices.server
        if config.has_section('server'):
            sconf = dict(config.items('server'))
        else:
            sconf = {}
        self.nameToDevice['server'] = devices.server.CockpitServer('server', sconf)


        # Parse config to create device instances.
        for name in config.sections():
            if name in SKIP_CONFIG:
                continue
            classname = config.get(name, 'type')
            modname = self.classToModule.get(classname, None)
            if not modname:
                raise Exception("No module found for device with name %s." % name)
            try:
                mod = importlib.import_module('devices.' + modname)
            except Exception as e:
                print("Importing %s failed with %s" % (modname, e))
            else:
                cls = getattr(mod, classname)
                try:
                    self.nameToDevice[name] = cls(name, dict(config.items(name)))
                except Exception as e:
                    raise Exception("In device %s" % name, e)

        # Initialize devices in order of dependence
        # Convert to list - python3 dict_values has no pop method.
        devices = list(self.nameToDevice.values())
        done = []
        while devices:
            # TODO - catch circular dependencies.
            d = devices.pop(0)
            depends = []
            for dependency in ['triggersource', 'analogsource']:
                other = d.config.get(dependency)
                if other:
                    depends.append(other)

            if any([other not in done for other in depends]):
                devices.append(d)
                continue
            self.initDevice(d)
            done.append(d.name)
            yield d.name

        # Add dummy devices as required.
        dummies = []
        # Dummy objectives
        if not getHandlersOfType(OBJECTIVE):
            import devices.objective
            if config.has_section('objectives'):
                objs = dict(config.items('objectives'))
            else:
                objs = {}
            dummies.append(devices.objective.ObjectiveDevice('objectives', objs))
        # Dummy stages
        axes = self.getSortedStageMovers().keys()
        if 2 not in axes:
            import devices.dummyZStage
            dummies.append(devices.dummyZStage.DummyZStage())
        if (0 not in axes) or (1 not in axes):
            import devices.dummyXYStage
            dummies.append(devices.dummyXYStage.DummyMover())
        # Cameras
        if not getHandlersOfType(CAMERA):
            import devices.dummyCamera
            dummies.append(devices.dummyCamera.DummyCamera())
        # Dummy imager
        if not getHandlersOfType(IMAGER):
            import devices.imager
            dummies.append(devices.imager.DummyImagerDevice())
        # Initialise dummies.
        for d in dummies:
            self.nameToDevice[d.name] = d
            self.initDevice(d)
        # Ambient light source
        from handlers.lightSource import LightHandler
        ambient = {'t': 100}
        h = LightHandler('ambient', 'ambient',
                         {'setExposureTime': lambda null, t: ambient.__setitem__('t', t),
                          'getExposureTime': lambda null: ambient['t'],
                          'setEnabled': lambda null, state: True,
                          }, 0, 100)
        self.addHandler(h)
        self.finalizeInitialization()
        yield 'dummy-devices'


    def addHandler(self, handler, device=None):
        if handler.deviceType not in self.deviceTypeToHandlers:
            self.deviceTypeToHandlers[handler.deviceType] = []
        self.deviceTypeToHandlers[handler.deviceType].append(handler)
        if handler.name in self.nameToHandler:
            # We enforce unique names, but multiple devices may reference
            # the same handler, e.g. where a device A is triggered by signals
            # from device B, device B provides the handler that generates the
            # signals, and device A will reference that handler.
            otherHandler = self.nameToHandler[handler.name]
            if handler is not otherHandler:
                otherDevice = self.handlerToDevice[otherHandler]
                raise RuntimeError("Multiple handlers with the same name [%s] from devices [%s] and [%s]" %
                                   (handler.name, str(device), str(otherDevice)))
        self.nameToHandler[handler.name] = handler
        self.handlerToDevice[handler] = device
        if handler.groupName not in self.groupNameToHandlers:
            self.groupNameToHandlers[handler.groupName] = []
        self.groupNameToHandlers[handler.groupName].append(handler)


    ## Initialize a Device.
    def initDevice(self, device):
        device.initialize()
        device.performSubscriptions()

        handlers = device.getHandlers()
        if not handlers:
            # device is not used
            return
        self.deviceToHandlers[device] = handlers
        self.handlersList.extend(handlers)
        for handler in handlers:
            self.addHandler(handler, device)

    ## Let each device publish any initial events it needs. It's assumed this
    # is called after all the handlers have set up their UIs, so that they can
    # be adjusted to match the current configuration. 
    def makeInitialPublications(self):
        for device in self.nameToDevice.values():
            device.makeInitialPublications()
        for handler in self.handlersList:
            handler.makeInitialPublications()


    ## Do any extra initialization needed now that everything is properly
    # set up.
    def finalizeInitialization(self):
        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(max_workers=4)
        for device in self.nameToDevice.values():
            pool.submit(device.finalizeInitialization)
        for handler in self.handlersList:
            pool.submit(handler.finalizeInitialization)
        pool.shutdown(wait=True)
        

    ## Return a mapping of axis to a sorted list of positioners for that axis.
    # We sort by range of motion, with the largest range coming first in the
    # list.
    def getSortedStageMovers(self):
        movers = self.deviceTypeToHandlers.get(STAGE_POSITIONER, [])
        axisToMovers = {}
        for mover in movers:
            if mover.axis not in axisToMovers:
                axisToMovers[mover.axis] = []
            axisToMovers[mover.axis].append(mover)

        for axis, handlers in iteritems(axisToMovers):
            handlers.sort(reverse = True,
                    key = lambda a: a.getHardLimits()[1] - a.getHardLimits()[0]
            )
        return axisToMovers



## Global singleton
deviceDepot = DeviceDepot()


## Simple passthrough
def loadConfig():
    deviceDepot.loadConfig()


## Simple passthrough.
def getNumModules():
    return deviceDepot.getNumModules()


## Simple passthrough.
def initialize(config):
    for device in deviceDepot.initialize(config):
        yield device


## Simple passthrough.
def makeInitialPublications():
    deviceDepot.makeInitialPublications()


## Return the handler with the specified name.
def getHandlerWithName(name):
    d = deviceDepot.nameToHandler.get(name, None)
    if d is None:
        # try case mangling
        keys = {k.lower(): k for k in deviceDepot.nameToHandler.keys()}
        d = deviceDepot.nameToHandler.get( keys.get(name.lower()), None)
    return d


## Return all registered device handlers of the appropriate type.
def getHandlersOfType(deviceType):
    return deviceDepot.deviceTypeToHandlers.get(deviceType, [])


## Return all registered device handlers in the appropriate group.
def getHandlersInGroup(groupName):
    return deviceDepot.groupNameToHandlers.get(groupName, [])


## Get all registered device handlers.
def getAllHandlers():
    return deviceDepot.nameToHandler.values()


## Get all registered devices.
def getAllDevices():
    return deviceDepot.nameToDevice.values()


## Simple passthrough.
def getSortedStageMovers():
    return deviceDepot.getSortedStageMovers()


## Get all cameras that are currently in use.
def getActiveCameras():
    cameras = getHandlersOfType(CAMERA)
    result = []
    for camera in cameras:
        if camera.getIsEnabled():
            result.append(camera)
    return result


## Add a handler
def addHandler(handler, device=None):
    return deviceDepot.addHandler(handler, device)

## Get a device by its name.
def getDeviceWithName(name):
    return deviceDepot.nameToDevice.get(name)


## Get the handlers of a specific type for a device.
def getHandler(nameOrDevice, handlerType):
    if isinstance(nameOrDevice, DeviceHandler):
        if nameOrDevice.deviceType == handlerType:
            return nameOrDevice
    if isinstance(nameOrDevice, string_types):
        dev = getDeviceWithName(nameOrDevice)
    else:
        dev = nameOrDevice

    handlers = set(getHandlersOfType(handlerType))
    devHandlers = set(deviceDepot.deviceToHandlers.get(dev, []))
    handlers = handlers.intersection(devHandlers)
    if len(handlers) == 0:
        return None
    elif len(handlers) == 1:
        return handlers.pop()
    else:
        return list(handlers)


## Sort handlers in order of abstraction
def getSortedHandlers():
    h = getAllHandlers()

## Get the Device instance associated with the given module.
#def getDevice(module):
#    return deviceDepot.moduleToDevice[module]


## Debugging function: reload the specified module to pick up any changes to 
# the code. This requires us to cleanly shut down the associated Device and 
# then re-create it without disturbing the associated Handlers (which may be
# referred to in any number of places in the rest of the code). Most Devices
# won't support this (reflected by the base Device class's shutdown() function
# raising an exception). 
# def reloadModule(module):
#     device = deviceDepot.moduleToDevice[module]
#     handlers = deviceDepot.deviceToHandlers[device]
#     device.shutdown()
#     reload(module)
#     newDevice = module.__dict__[module.CLASS_NAME]()
#     newDevice.initFromOldDevice(device, handlers)


