#!/usr/bin/env python
# -*- coding: utf-8 -*-

## Copyright (C) 2018 Mick Phillips <mick.phillips@gmail.com>
## Copyright (C) 2018 Ian Dobbie <ian.dobbie@bioch.ox.ac.uk>
## Copyright (C) 2018 David Pinto <david.pinto@bioch.ox.ac.uk>
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


import depot
import events
import util.datadoc
import util.logger
import util.threads

import numpy
from six.moves import queue
import threading
import time

from six import iteritems

## Unique ID for identifying saver instances
uniqueID = 0

# cast to long
try:
    # python 2
    LCAST = long
except:
    # python 3
    LCAST = int


## This class simply records all data received during an experiment and saves
# it to disk in MRC format.
class DataSaver:
    ## \param cameras List of CameraHandler instances for the cameras that
    #         will be generating images
    # \param numReps How many times the experiment will be repeated.
    # \param cameraToImagesPerRep Maps camera handlers to how many images to 
    #        expect for that camera in a single repeat of the experiment.
    # \param cameraToIgnoredImageIndices Maps camera handlers to indices of 
    #        images that we don't actually want to keep.
    # \param runThread Thread that is executing the experiment. When it exits,
    #        we know to stop expecting more images.
    # \param savePath Path to save the incoming data to.
    # \param pixelSizeZ Size of the Z "pixel" (i.e. distance between Z slices).
    # \param titles List of strings to insert into the MRC file's header.
    #        Per the file format, each string can be up to 80 characters long
    #        and there can be up to 10 of them. 
    def __init__(self, cameras, numReps, cameraToImagesPerRep, 
            cameraToIgnoredImageIndices, runThread,
            savePath, pixelSizeZ, titles):
        self.cameras = cameras
        self.numReps = numReps
        self.cameraToImagesPerRep = cameraToImagesPerRep
        self.cameraToIgnoredImageIndices = cameraToIgnoredImageIndices
        self.runThread = runThread
        ## Maximum size, in megabytes, of each file generated.  If the
        # experiment data exceeds this, then a new file will be opened, and
        # each file will have a suffix appended to it (e.g.  ".001", ".002",
        # etc.). This is not a precise cap, since it only considers the amount
        # of space allocated to image data -- not the header or extended
        # header.
        # The default of a googol megabytes ought to be enough to avoid 
        # splitting files if no cap is specified. :)
        self.maxFilesize = 10**100
        config = depot.getHandlersOfType(depot.CONFIGURATOR)[0]
        try:
            self.maxFilesize = config.getValue('maxFilesizeMegabytes')
        except KeyError:
            # No max filesize specified; leave it as-is.
            pass
        
        global uniqueID
        ## Unique ID for our instance
        self.uniqueID = uniqueID
        uniqueID += 1
        # Find the maximum image size (in pixels) in X and Y. While we're at it,
        # assign a number to each camera, for indexing into our data array
        # later, and figure out how many images per camera we'll actually be 
        # *keeping*. 
        self.maxWidth, self.maxHeight = 0, 0
        ## We need to establish a consistent ordering for cameras so that
        # each image gets stored in the correct part of the file. This
        # maps camera handlers to indices.
        self.cameraToIndex = {}
        ## Maps camera handlers to total images kept per rep.
        self.cameraToImagesKeptPerRep = {}
        for i, camera in enumerate(self.cameras):
            width, height = camera.getImageSize()
            self.maxWidth = max(width, self.maxWidth)
            self.maxHeight = max(height, self.maxHeight)
            self.cameraToIndex[camera] = i
            self.cameraToImagesKeptPerRep[camera] = self.cameraToImagesPerRep[camera] - len(self.cameraToIgnoredImageIndices[camera])
        ## We need this for the upper bound on the array of data we write.
        self.maxImagesPerRep = max(self.cameraToImagesKeptPerRep.values())

        ## Number of bytes to allocate for each image in the file.
        # \todo Assuming unsigned 16-bit integer here.
        self.imageBytes = (self.maxWidth * self.maxHeight * 2)
        
        ## Number of timepoints per file, based on the above and 
        # self.maxFilesize.
        self.maxRepsPerFile = self.maxFilesize // (self.maxImagesPerRep * self.imageBytes * len(self.cameras) / 1024.0 / 1024.0)
        # Sanity check.
        self.maxRepsPerFile = max(self.maxRepsPerFile, 1)
        ## Whether or not we need to split the data into multiple files.
        self.doNeedToSplitFiles = (self.maxRepsPerFile < self.numReps)
        # For simplicity's sake, we bring self.maxRepsPerFile down to 
        # self.numReps in cases where we only need a single file anyway.
        self.maxRepsPerFile = min(self.numReps, self.maxRepsPerFile)

        ## Maps ints to cameras; the ints represent the order in which the 
        # images are stored. 
        self.indexToCamera = dict([(value, key) for key, value in iteritems(self.cameraToIndex)])
        ## Timestamp of the first image we receive. 
        # We need this so we can rebase the timestamps of images to
        # to be relative to the beginning of the experiment -- Python 
        # timestamps can't be stored directly as 32-bit floating points without
        # losing a lot of precision. And we want to store image timestamps in
        # the extended header, to help us identify when frames get dropped.
        self.firstTimestamp = None

        ## Time at which we last received an image, so we know when images
        # have stopped arriving.
        self.lastImageTime = time.time()

        ## Filehandles we will write the data to.
        self.filehandles = []
        ## Filenames for same.
        self.filenames = []
        if self.doNeedToSplitFiles:
            # We have multiple filehandles, each with a suffix.
            # A bit tricky here: we want a suffix that has only as many 
            # digits as needed, e.g. not doing ".001" when you're only going to
            # use 2 files.
            numFilehandles = int(numpy.ceil(float(self.numReps) / self.maxRepsPerFile))
            numDigits = int(numpy.ceil(numpy.log10(numFilehandles)))
            # Generates e.g. "%05d" if we need 5 digits, or "%01d" if we only 
            # need 1.
            formatString = "%0" + str(numDigits) + "d"
            for i in range(numFilehandles):
                filename = "%s.%s" % (savePath, formatString % i)
                self.filehandles.append(open(filename, 'wb'))
                self.filenames.append(filename)
        else:
            # We have just a single filehandle with the save path as specified.
            self.filehandles.append(open(savePath, 'wb'))
            self.filenames.append(savePath)
            
        ## Lock on writing to each file.
        self.fileLocks = [threading.Lock() for handle in self.filehandles]

        pixelSizeXY = depot.getHandlersOfType(depot.OBJECTIVE)[0].getPixelSize()
        lensID = depot.getHandlersOfType(depot.OBJECTIVE)[0].getLensID()
        ## TODO: handle missing drawer better.
        drawer = [depot.getHandlersOfType(depot.DRAWER) or None][0]
        if drawer:
            wavelengths = [c.wavelength for c in self.cameras]
        else:
            wavelengths = [0 for c in self.cameras]

        ## Size of one image's worth of metadata in the extended header.
        # We store 1 4-byte float per image.
        self.extendedBytes = 4
        
        ## MRC header objects for each file.
        self.headers = []
        for i in range(len(self.filehandles)):
            # Calculate how many timepoints fit into this particular file 
            # (potentially different for the final file).
            numTimepoints = self.maxRepsPerFile
            if i == len(self.filehandles) - 1:
                numTimepoints = self.numReps - (self.maxRepsPerFile * (len(self.filehandles) - 1))
            header = util.datadoc.makeHeaderForShape(
                (len(self.cameras), numTimepoints, self.maxImagesPerRep, 
                    self.maxHeight, self.maxWidth),
                numpy.uint16, pixelSizeXY, pixelSizeZ, wavelengths)
            #write the lensID to the header if not zero (meaning undefined)
            if (lensID != 0):
                header.LensNum = lensID
        

            # By default, the headers generated by DataDoc are for files in ZWT
            # order. But for efficient saving of large multi-wavelength files,
            # we need to store in WZT order (where the cameras are as close
            # together as possible).
            header.ImgSequence = 1
            # Write out the "titles" (metadata, like exposure settings)
            tempTitles = list(titles)
            if self.doNeedToSplitFiles and len(titles) < 8:
                # We have room for an extra title indicating where this file
                # falls in the sequence.
                tempTitles.append("File %d of %d; base timepoint %d" % (i + 1, 
                    len(self.filehandles), i * self.maxRepsPerFile))
            header.NumTitles = len(tempTitles)
            header.title[:len(tempTitles)] = tempTitles
            # Write the size of the extended header, in bytes. We'll be storing
            # a timestamp for each image, as a 32-bit floating point value.
            header.next = (self.extendedBytes * self.maxImagesPerRep *
                    len(self.cameras) * numTimepoints)
            # Number of 32-bit floats in the extended header, per image.
            header.NumFloats = 1 
            self.headers.append(header)

        # Write the headers, to get us started. We will re-write this at the 
        # end when we have more metadata to fill in (specifically, the min/max
        # values for each wavelength).
        for i, handle in enumerate(self.filehandles):
            with self.fileLocks[i]:
                util.datadoc.writeMrcHeader(self.headers[i], handle)
        
        ## List of how many images we've received, on a per-camera basis.
        self.imagesReceived = [0] * len(self.cameras)
        ## List of how many images we've written, on a per-camera basis.
        self.imagesKept = [0] * len(self.cameras)
        ## List of functions that receive image data and feed it into 
        # self.imagesReceived.
        self.lambdas = []
        ## List of (min, max) tuples, on a per-camera basis, tracking
        # the dimmest and brightest pixels.
        self.minMaxVals = []

        ## True if we should stop collecting data.
        self.shouldAbort = False
        ## True if we are done collecting data.
        self.amDone = False
        ## Queue of (camera index, image data, timestamp) tuples for images
        # that need to be saved
        self.imageQueue = queue.Queue()

        # Use dye name if available, otherwise use camera name.
        names = [camera.dye or camera.name for camera in self.cameras]
        totals = []
        for camera in self.cameras:
            totals.append(self.cameraToImagesKeptPerRep[camera] * self.numReps)
        ## Thread that handles updating the UI.
        self.statusThread = StatusUpdateThread(names, totals)

        # Start the data-saving thread.
        self.saveData()
        

    ## Subscribe to the new-camera-image events for the cameras we care about.
    # Save the functions we generate for handling the subscriptions, so we can
    # unsubscribe later. Initialize self.minMaxVals. Start our status-update
    # thread.
    def startCollecting(self):
        for camera in self.cameras:
            func = lambda data, timestamp, camera = camera: self.onImage(self.cameraToIndex[camera], data, timestamp)
            self.lambdas.append(func)
            events.subscribe('new image %s' % camera.name, func)

            # \todo Assuming no value will ever be over 2**128, which ought
            # to be safe since our cameras are only 16-bit anyway.
            self.minMaxVals.append((2 ** 128, -(2 ** 128)))
        events.subscribe('user abort', self.onAbort)
        self.statusThread.start()


    ## User aborted; stop saving data.
    def onAbort(self):
        self.shouldAbort = True
        self.statusThread.shouldStop = True


    ## Wait for the runThread to finish, then wait a bit longer in case some
    # images are laggardly, before we close our filehandles.
    def executeAndSave(self):
        # Joining the thread doesn't actually work until it has started,
        # hence the delay here.
        time.sleep(.5)
        self.runThread.join()

        # Wait until it's been a bit without getting any more images in, or
        # until we have all the images we expected to get for each camera.
        while time.time() - self.lastImageTime < .5 or not self.imageQueue.empty():
            amDone = True
            for camera in self.cameras:
                total = self.imagesKept[self.cameraToIndex[camera]]
                target = self.cameraToImagesKeptPerRep[camera] * self.numReps
                if total != target:
                    # There exists a camera for which we do not have all
                    # images yet.
                    amDone = False
                    break
            if amDone or self.shouldAbort:
                break
            time.sleep(.01)
        self.amDone = True
            
        self.cleanup()

        # Determine min/max vals for each wavelength.
        for header in self.headers:
            for i in range(len(self.cameras)):
                # HACK: camera 1 is supposed to get min/max/median. However,
                # computing the median of a large dataset takes a very long 
                # time (30s for a 2GB file on a fairly powerful computer), 
                # so we just store 0.
                minVal, maxVal = self.minMaxVals[i]
                if i == 0:
                    setattr(header, 'mmm1', (minVal, maxVal, 0))
                else:
                    setattr(header, 'mm%d' % (i + 1), (minVal, maxVal))
        # Rewrite the headers, now that we know what the min/max values are.
        # Of course, these won't be precisely accurate for every file.
        # \todo Track min/max values on a per-file basis.
        # Then, close the filehandle.
        for i, handle in enumerate(self.filehandles):
            with self.fileLocks[i]:
                util.datadoc.writeMrcHeader(self.headers[i], handle)
                handle.close()
        

    ## Clean up once saving is completed.
    def cleanup(self):
        self.statusThread.shouldStop = True
        for i, camera in enumerate(self.cameras):
            events.unsubscribe('new image %s' % camera.name, self.lambdas[i])
        events.unsubscribe('user abort', self.onAbort)
        

    ## Receive new data, and add it to the queue.
    def onImage(self, cameraIndex, imageData, timestamp):
        self.imageQueue.put((cameraIndex, imageData, timestamp))


    ## Continually poll our imageQueue and save data to the file.
    @util.threads.callInNewThread
    def saveData(self):
        while not self.amDone:
            if self.shouldAbort:
                # Do nothing.
                return
            cameraIndex, imageData, timestamp = self.imageQueue.get()
            if self.firstTimestamp is None:
                self.firstTimestamp = timestamp
            # Store the timestamp as a rebased 32-bit float; we can't use
            # 64-bit due to the file format restriction, and if we don't
            # rebase then the numbers are big enough that we lose decimal
            # precision.
            timestamp = timestamp - self.firstTimestamp
            self.writeImage(cameraIndex, imageData, timestamp)


    ## Write a single image to the file.
    def writeImage(self, cameraIndex, imageData, timestamp):
        self.imagesReceived[cameraIndex] += 1
        camera = self.indexToCamera[cameraIndex]
        # First determine if we actually want to keep this image.
        if self.imagesReceived[cameraIndex] % self.cameraToImagesPerRep[camera] in self.cameraToIgnoredImageIndices[camera]:
            # This image is one that should be discarded.
            return
        # Convert the timestamp into something we can cleanly write.
        timestamp = numpy.float32(timestamp)
        # Calculate the time and Z indices for the new image. This will in turn
        # help us to calculate which file to write to and the offset of the
        # image in the file.
        numImages = self.imagesKept[cameraIndex]
        timepoint = numImages // self.maxImagesPerRep
        fileIndex = timepoint // self.maxRepsPerFile
        # Rebase the timepoint to be relative to the beginning of this specific
        # file.
        timepoint -= fileIndex * self.maxRepsPerFile
        zIndex = numImages % self.cameraToImagesKeptPerRep[camera]

        numCameras = len(self.cameras)
        # Index of the image into the 1D array of images we are effectively 
        # generating as we write data to the file. Note casting to long, since
        # these numbers can be big and by default Python doesn't always pick
        # the right type.

        imageOffset = LCAST(timepoint * self.maxImagesPerRep * numCameras) + \
                (zIndex * numCameras) + cameraIndex
        
        height, width = imageData.shape

        # Pad with zeros. I wouldn't normally think this would be
        # necessary, but we get "invalid argument" errors when writing
        # to the filehandle if we don't.
        # \todo Figure out why this is necessary.
        paddedBuffer = numpy.zeros((self.maxHeight, self.maxWidth),
                dtype = numpy.uint16)
        paddedBuffer[:height, :width] = imageData

        with self.fileLocks[fileIndex]:
            handle = self.filehandles[fileIndex]
            # Seek to the appropriate byte offset for the timestamp; write
            # it; repeat for the image data.
            try:
                # Write the timestamp. 1024 is the size of the standard header.
                handle.seek(LCAST(1024 + self.extendedBytes * imageOffset))
                handle.write(timestamp)

                header = self.headers[fileIndex]
                # Offset in the file of the first image. The standard header
                # takes 1024 bytes and the extended header takes a variable
                # amount (depending on how many timepoints are in this file).
                headerOffset = 1024 + header.next
                # Write the image data.
                byteOffset = LCAST(headerOffset +
                        imageOffset * self.imageBytes)
                handle.seek(byteOffset)
                handle.write(paddedBuffer)
                self.imagesKept[cameraIndex] += 1
                self.lastImageTime = time.time()
                curMin, curMax = self.minMaxVals[cameraIndex]
                self.minMaxVals[cameraIndex] = (min(curMin, imageData.min()), 
                        max(curMax, imageData.max()))
            except Exception as e:
                print ("Error writing image:",e)
                raise e
                
        # Update the status text. But first, check for abort/experiment
        # completion, since we may actually be done now and we don't want
        # a misleading status text.
        if self.shouldAbort or self.amDone:
            return
        self.statusThread.newImage(cameraIndex)


    ## Return a list of the filenames we are writing to.
    def getFilenames(self):
        return self.filenames



## This thread handles telling the saving status light to update twice per
# second.
class StatusUpdateThread(threading.Thread):
    def __init__(self, cameraNames, totals):
        threading.Thread.__init__(self)
        ## List of names of the cameras.
        self.cameraNames = cameraNames
        ## List of images received per camera.
        self.imagesReceived = [0 for name in self.cameraNames]
        ## Lock on updating the above.
        self.imageCountLock = threading.Lock()
        ## List of total images expected per camera.
        self.totals = totals
        ## Set to True to end the thread.
        self.shouldStop = False


    def run(self):
        prevCounts = list(self.imagesReceived)
        self.updateText()
        while not self.shouldStop:
            if prevCounts != self.imagesReceived:
                # Have received new images since the last update; update the display.
                with self.imageCountLock:
                    self.updateText()
                    prevCounts = list(self.imagesReceived)
            else:
                # No images; wait a bit.
                time.sleep(.1)
        # Clear the status light.
        events.publish('update status light', 'image count', '',
                (170, 170, 170))


    ## Push a new text to the status light.
    def updateText(self):
        statusText = ''
        for i, name in enumerate(self.cameraNames):
            curCount = self.imagesReceived[i]
            maxCount = self.totals[i]
            statusText += '%s: %d/%d\n' % (name, curCount, maxCount)
        events.publish('update status light', 'image count', statusText,
                (255, 255, 0))


    ## Update our image count.
    def newImage(self, index):
        with self.imageCountLock:
            self.imagesReceived[index] += 1
            
        
