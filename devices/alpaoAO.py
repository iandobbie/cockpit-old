#Cockpit Device file for Alpao AO device.
#Copyright Ian Dobbie, 2017
#released under the GPL 3+
#
#This file provides the cockpit end of the driver for the Alpao deformable
#mirror as currently mounted on DeepSIM in Oxford

import device
from config import config
import wx


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
        ## piDevice instance.
        self.alpao = AoDevice
        # Contains all widgets.
        panel = wx.Panel(self)




        
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        buttonSizer = wx.GridSizer(2, 4, 1, 1)

        ## Maps buttons to their lines.
        self.buttonToLine = {}

        # Set up the digital lineout buttons.
        for i in range(len(piDIO.lines)) :
            button = gui.toggleButton.ToggleButton(
                    parent = panel, label = str(piDIO.lines[i]),
                    activateAction = self.toggle,
                    deactivateAction = self.toggle,
                    size = (140, 80))
            buttonSizer.Add(button, 1, wx.EXPAND)
            self.buttonToLine[button] = i
        mainSizer.Add(buttonSizer)

        panel.SetSizerAndFit(mainSizer)
        self.SetClientSize(panel.GetSize())


    ## One of our buttons was clicked; update the DSP's output.
    def toggle(self):
        output = 0
        for button, line in self.buttonToLine.iteritems():
            if button.getIsActive():
                self.pi.RPiConnection.flipDownUp(line, 1)
            else:
                self.pi.RPiConnection.flipDownUp(line, 0)


## Debugging function: display a DSPOutputWindow.
def makeOutputWindow(self):
    # HACK: the _deviceInstance object is created by the depot when this
    # device is initialized.
    global _deviceInstance
    piOutputWindow(_deviceInstance, parent = wx.GetApp().GetTopWindow()).Show()
    


