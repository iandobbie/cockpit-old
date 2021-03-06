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


from . import actionTable
import depot
from . import experiment
import gui.guiUtils
import util.userConfig

import decimal
import math
import wx

## Provided so the UI knows what to call this experiment.
EXPERIMENT_NAME = "Multi-exposure Z-stack"



## Just like a standard Z-stack experiment, but we do multiple exposure times
# at each Z slice. Hacked all to hell though since we rely on OMXT's
# delay generator being set up for us ahead of time.
class ZStackMultiExperiment(experiment.Experiment):
    def __init__(self, exposureMultiplier = 10, exposureDelay = 1, *args, **kwargs):
        experiment.Experiment.__init__(self, *args, **kwargs)
        ## Amount to multiply subsequent exposures by.
        self.exposureMultiplier = decimal.Decimal(exposureMultiplier)
        ## Amount of time to wait after the *beginning* of the first exposure
        # before *beginning* the second exposure.
        self.exposureDelay = decimal.Decimal(exposureDelay)

        
    ## Create the ActionTable needed to run the experiment. We simply move to 
    # each Z-slice in turn, take our images, then move to the next.
    def generateActions(self):
        table = actionTable.ActionTable()
        # Open all light sources for the duration of the experiment.
        # Normally the delay generator logic would do this for us.
        for cameras, exposures in self.exposureSettings:
            for light, exposureTime in exposures:
                table.addAction(0, light, True)
        shutter = depot.getHandlerWithName('488 shutter')
        delayGen = depot.getHandlerWithName('Delay generator trigger')
        curTime = 0
        table.addAction(curTime, shutter, True)
        prevAltitude = None
        numZSlices = int(math.ceil(self.zHeight / self.sliceHeight))
        for zIndex in range(numZSlices):
            # Move to the next position, then wait for the stage to 
            # stabilize.
            zTarget = self.zStart + self.sliceHeight * zIndex
            motionTime, stabilizationTime = 0, 0
            if prevAltitude is not None:
                motionTime, stabilizationTime = self.zPositioner.getMovementTime(prevAltitude, zTarget)
            table.addAction(curTime + motionTime, self.zPositioner, 
                    zTarget)
            curTime += motionTime + stabilizationTime            
            prevAltitude = zTarget

            # Trigger the delay generator. Do it slightly *after* the trigger
            # of the cameras below, so that we ensure the first exposure, which
            # may be very brief, is fully-contained in a camera exposure.
            table.addToggle(curTime + decimal.Decimal('.5'), delayGen)
            # Trigger the cameras twice. Lazy; only allow one set of cameras.
            cameras = self.exposureSettings[0][0]
            for camera in cameras:
                table.addToggle(curTime, camera)
                table.addToggle(curTime + self.exposureDelay, camera)
                self.cameraToImageCount[camera] += 2
            maxCamDelay = max(c.getTimeBetweenExposures(isExact = True) for c in cameras)
            # Wait for the exposure to complete and/or for the cameras to be
            # ready again.
            longExposureTime = self.exposureSettings[0][1][0][1] * self.exposureMultiplier
            curTime += self.exposureDelay + max(maxCamDelay,
                    self.exposureDelay + longExposureTime)
            # Plus a little extra for the cameras to recover.
            # \todo This seems a bit excessive; why do we need to wait so
            # long for the Zyla to be ready?
            curTime += decimal.Decimal('10')
            # Hold the Z motion flat during the exposure.
            table.addAction(curTime, self.zPositioner, zTarget)

        # Close all light sources we opened at the start.
        # Normally the delay generator logic would do this for us.
        for cameras, exposures in self.exposureSettings:
            for light, exposureTime in exposures:
                table.addAction(curTime, light, False)
                
        # Move back to the start so we're ready for the next rep.
        motionTime, stabilizationTime = self.zPositioner.getMovementTime(
                self.zHeight, 0)
        curTime += motionTime
        table.addAction(curTime, self.zPositioner, 0)
        
        # Hold flat for the stabilization time, and any time needed for
        # the cameras to be ready. Only needed if we're doing multiple
        # reps, so we can proceed immediately to the next one.
        cameraReadyTime = 0
        if self.numReps > 1:
            for cameras, lightTimePairs in self.exposureSettings:
                for camera in cameras:
                    cameraReadyTime = max(cameraReadyTime,
                            self.getTimeWhenCameraCanExpose(table, camera))
        table.addAction(max(curTime + stabilizationTime, cameraReadyTime),
                self.zPositioner, 0)

        return table



## A consistent name to use to refer to the class itself.
EXPERIMENT_CLASS = ZStackMultiExperiment


## Generate the UI for special parameters used by this experiment.
class ExperimentUI(wx.Panel):
    def __init__(self, parent, configKey):
        wx.Panel.__init__(self, parent)
        self.configKey = configKey
        self.settings = self.loadSettings()

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.exposureMultiplier = gui.guiUtils.addLabeledInput(self, 
                sizer, label = "Exposure multiplier",
                defaultValue = self.settings['exposureMultiplier'],
                helperString = "Amount to multiply the normal exposure duration by to get the second exposure duration.")

        self.exposureDelay = gui.guiUtils.addLabeledInput(self,
                sizer, label = "Delay between exposures",
                defaultValue = self.settings['exposureDelay'],
                helperString = "Amount of time to wait, in milliseconds, between the beginning of the first exposure and the beginning of the second exposure. Should be long enough for the camera to recover from taking the first image!")

        self.SetSizerAndFit(sizer)


    ## Given a parameters dict to hand to the experiment instance, augment
    # it with our special parameters.
    def augmentParams(self, params):
        self.saveSettings()
        params['exposureMultiplier'] = gui.guiUtils.tryParseNum(
                self.exposureMultiplier, float)
        params['exposureDelay'] = gui.guiUtils.tryParseNum(self.exposureDelay, float)
        return params


    ## Load saved experiment settings, if any.
    def loadSettings(self):
        return util.userConfig.getValue(
                self.configKey + 'ZStackMultiSettings',
                default = {
                    'exposureMultiplier': '10',
                    'exposureDelay': '5',
                }
        )


    ## Generate a dict of our settings.
    def getSettingsDict(self):
        return {
                'exposureMultiplier': self.exposureMultiplier.GetValue(),
                'exposureDelay': self.exposureDelay.GetValue(),
        }


    ## Save current experiment settings to config.
    def saveSettings(self, settings = None):
        if settings is None:
            settings = self.getSettingsDict()
        util.userConfig.setValue(
                self.configKey + 'ZStackMultiSettings', settings
        )

