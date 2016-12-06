import device
import depot
import events
import threading
import time
import opc
import math
import numpy as N


from config import config
CLASS_NAME = 'StatusLED'
CONFIG_NAME = 'statusled'

# Open Pixel Control client: All lights to solid white

PI = 3.14159
ringLEDs=range(8)

class StatusLED(device.Device):
    def __init__(self):
        self.isActive = config.has_section(CONFIG_NAME)
        self.priority = 10000
        if not self.isActive:
            return
        else:
            self.ipAddress = config.get(CONFIG_NAME, 'ipAddress')
            self.port = int(config.get(CONFIG_NAME, 'port'))

        self.client = opc.Client(self.ipAdress+':'+self.port)

        #inital ppower level is 100 (out of 255)
        self.power = 100

        #events that trigger Status LEDs - need to populate these functions. 
#        events.subscribe('new image', self.onNewImage)
#        events.subscribe('camera enable',self.onCameraEnable)
#        events.subscribe('light source enable',self.onLightEnable)
#        events.subscribe('user abort', self.onStopVideo)
#        events.subscribe("stage mover", self.onMotion)
#        events.subscribe("stage stopped", self.onStop)
#        events.subscribe("status update", self.onEvent)

        



        client.put_pixels(intensity)

