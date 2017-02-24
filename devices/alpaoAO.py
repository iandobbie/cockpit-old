#Cockpit Device file for Alpao AO device.
#Copyright Ian Dobbie, 2017
#released under the GPL 3+
#
#This file provides the cockpit end of the driver for the Alpao deformable
#mirror as currently mounted on DeepSIM in Oxford

import device
from config import config
import wx
import interfaces.stageMover

CLASS_NAME = 'AO'
CONFIG_NAME = 'alpao'



#the AO device subclasses Device to provide compatibility with microscope. 
class AoDevice(device.Device):
    def __init__(self):
        self.isActive = config.has_section(CONFIG_NAME)
        self.priority = 10000
        if not self.isActive:
            return
        else:
            self.ipAddress = config.get(CONFIG_NAME, 'ipAddress')
            self.port = config.get(CONFIG_NAME, 'port')

        self.AlpaoConnection = None

        		
        self.makeOutputWindow = makeOutputWindow
        self.buttonName='Alpao'

        ## Connect to the remote program
    def initialize(self):
#        self.AlpaoConnection = Pyro4.Proxy('PYRO:%s@%s:%d' %
#                                           ('alpao', self.ipAddress, self.port))

        pass
        
## This debugging window lets each digital lineout of the DSP be manipulated
# individually.
class alpaoOutputWindow(wx.Frame):
    def __init__(self, AoDevice, parent, *args, **kwargs):
        wx.Frame.__init__(self, parent, *args, **kwargs)
        ## alpao Device instance.
        self.alpao = AoDevice
        # Contains all widgets.
        panel = wx.Panel(self)
        font=wx.Font(12,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        allPositions = interfaces.stageMover.getAllPositions()
        self.piezoPos = allPositions[1][2]
        textSizer=wx.BoxSizer(wx.VERTICAL)
        piezoText=wx.StaticText(self.panel,str(piezoPos),
                                    style=wx.ALIGN_CENTER)
        piezoText.SetFont(font)
        textSizer.Add(piezoText, 0, wx.EXPAND|wx.ALL,border=5)
        mainSizer.Add(textSizer, 0,  wx.EXPAND|wx.ALL,border=5)
        panel.SetSizerAndFit(mainSizer)
        events.subscribe('objective change', self.onMove)


    def onMove(self, axis, position):
        if axis != 2:
            # We only care about the Z axis.
            return
        self.piezoText.SetLabel(interfaces.stageMover.getAllPositions()[1][2])


## Debugging function: display a DSPOutputWindow.
def makeOutputWindow(self):
    # HACK: the _deviceInstance object is created by the depot when this
    # device is initialized.
    global _deviceInstance
    alpoaOutputWindow(_deviceInstance, parent = wx.GetApp().GetTopWindow()).Show()
    


