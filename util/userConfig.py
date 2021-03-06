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


from . import logger
from . import files
import os
# We could use pickle here instead, but I prefer config
# files that I can read myself.
import pprint
import sys
import traceback

from six import iteritems

## @package userConfig 
# This module handles loading and saving changes to user configuration, which
# is used to remember individual users' settings (and a few global settings)
# for dialogs and the like.

## Directory that contains config files. Will be set when loadConfig is called.
CONFIG_ROOT_PATH = None
## Username for config settings that don't belong to a specific user.
GLOBAL_USERNAME = 'global'
## Suffix we append to each username to help avoid name conflicts
CONFIG_SUFFIX = "-MUI-config"

## In-memory version of the config; program singleton.
config = {}
## Indicates if the config has changed during a function call
didChange = False

## Printer for saving the config to file
printer = pprint.PrettyPrinter()

## Open the config file and unserialize its contents.
def loadConfig():
    from . import user
    global CONFIG_ROOT_PATH
    CONFIG_ROOT_PATH = files.getConfigDir()
    global config
    sys.path.append(CONFIG_ROOT_PATH)
    # Ensure that the config directory exists. Normally the util.files
    # directory does this, but it depends on config...
    if not os.path.exists(CONFIG_ROOT_PATH):
        os.mkdir(CONFIG_ROOT_PATH)
    # Ensure config exists for all users.
    userList = user.getUsers() + [GLOBAL_USERNAME]
    for u in userList:
        pathToModule = getConfigPath(u)
        if not os.path.exists(pathToModule):
            # Create a default (blank) config file.
            outHandle = open(pathToModule, 'w')
            outHandle.write("config = {}\n")
            outHandle.close()

        try:
            modulename = u + CONFIG_SUFFIX
            module = __import__(modulename, globals(), locals(), ['config'])
            config[u] = module.config
        except Exception as e:
            logger.log.error("Failed to load configuration file %s: %s", modulename, e)


## Serialize the current config state for the specified user
# to the appropriate config file.
def writeConfig(user):
    outFile = open(getConfigPath(user), 'w')
    # Do this one key-value pair at a time, to reduce the likelihood
    # that the printer will fail to print something really big.
    outFile.write("config = {\n")
    for key, value in iteritems(config[user]):
        outFile.write(" %s: %s,\n" % (printer.pformat(key), printer.pformat(value)))
    outFile.write("}\n")
    outFile.close()


## Generate the path to the specified user's config file
def getConfigPath(user):
    return os.path.join(CONFIG_ROOT_PATH, user + CONFIG_SUFFIX + ".py")


## Retrieve the config value referenced by key. If isGlobal is true, look 
# under the global config entry; otherwise look under the entry for 
# the current user. If key is not found, default is inserted and returned.
# If the value changed as a result of the lookup (because we wrote the
# default value to config), then write config back to the file.
def getValue(key, isGlobal = False, default = None):
    global config, didChange
    didChange = False
    user = getUser(isGlobal)
    if user not in config:
        config[user] = {}
    result = getValueFromConfig(config[user], key, default)
    if didChange:
        writeConfig(user)
    return result


## Second-level, potentially-recursive config getter. Allows clients to
# muck around with deep dicts.
def getValueFromConfig(config, key, default):
    global didChange
    if key not in config:
        didChange = True
        config[key] = default
    if type(default) == type(dict()):
        # Ensure all values in default are in result.
        for name, value in iteritems(default):
            if name not in config[key]:
                didChange = True
                config[key][name] = value
            # Recurse for nested dicts
            if type(value) == type(dict()):
                getValueFromConfig(config[key], name, value)
    return config[key]


## Set the entry referenced by key to the given value. Users are set as
# in getValue.
def setValue(key, value, isGlobal = False):
    global config
    user = getUser(isGlobal)
    if user not in config:
        config[user] = {}
    config[user][key] = value
    writeConfig(user)


## Remove the given key from config
def removeValue(key, isGlobal = False):
    global config
    user = getUser(isGlobal)
    del config[user][key]
    writeConfig(user)


## Simple chooser to reduce code duplication.
def getUser(isGlobal):
    from . import user
    if isGlobal:
        return GLOBAL_USERNAME

    curName = user.getUsername()
    if curName is not None:
        return curName
    # Nobody logged in yet; have to use global controls
    logger.log.warning("Trying to use non-global config when no user is logged in")
    logger.log.warning("%s", traceback.format_list(traceback.extract_stack()))
    return GLOBAL_USERNAME


def initialize():
    loadConfig()
