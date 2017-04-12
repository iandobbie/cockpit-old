#Cockpit Device file for Alpao AO device.
#Copyright Ian Dobbie, 2017
#released under the GPL 3+
#
#This file provides the cockpit end of the driver for the Alpao deformable
#mirror as currently mounted on DeepSIM in Oxford

import device
import depot
import events
import Pyro4
from config import config
import wx
import interfaces.stageMover
import socket
import util
import time

CLASS_NAME = 'AO'
CONFIG_NAME = 'alpao'



#the AO device subclasses Device to provide compatibility with microscope. 
class AO(device.Device):
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
        self.socket=socket.socket()
        self.socket.bind(('129.67.73.152',8867))
        self.socket.listen(2)
        self.listenthread()
        #No using a connection, using a listening socket.
        #self.connectthread()
    @util.threads.callInNewThread
    def listenthread(self):
        while 1:
            (self.clientsocket, address)=self.socket.accept()
            if self.clientsocket:
                print "socket connected", address
                noerror=True
                while noerror:
                    try:
                        input=self.clientsocket.recv(100)
                    except socket.error,e:
                        noerror=False
                        print 'Labview socket disconnected'
                        break
                    
                    if(input[:4]=='getZ'):
                        reply=str(self.getPiezoPos())+'\r\n'
                    elif (input[:4]=='setZ'):
                        pos=float(input[4:])
                        reply=str(self.movePiezoAbsolute(pos))+'\r\n'
                    else:
                        reply='Unknown command\r\n'
                    #print reply    
                    try:
                        self.clientsocket.send(reply)
                    except socket.error,e:
                        noerror=False
                        print 'Labview socket disconnected'
                        break
#                    print "sent" 
 #                   time.sleep(.01)

    @util.threads.callInNewThread                   
    def connectthread(self):
        self.socket=socket.socket()
        self.socket.connect(('129.67.77.21',8868))
 #       self.socket.setblocking(0)
        i=0
        while 1:
            i=i+1        
            input=self.recv_end(self.socket)
            
            print input

            output=self.socket.send('hello'+str(i)+'\r\n')
            print "sent bytes",output 
            time.sleep(1)
            

            
    def recv_end(self,the_socket):
        End='crlf'
        total_data=[];data=''
        while True:
            data=the_socket.recv(100)
            print data
            if End in data:
                total_data.append(data[:data.find(End)])
                break
            total_data.append(data)
            if len(total_data)>1:
                #check if end_of_data was split
                last_pair=total_data[-2]+total_data[-1]
                if End in last_pair:
                    total_data[-2]=last_pair[:last_pair.find(End)]
                    total_data.pop()
                    break
        return ''.join(total_data)
        
        
                
    def getPiezoPos(self):
        return(interfaces.stageMover.getAllPositions()[1][2])

    def movePiezoRelative(self, distance):
        current=self.getPiezoPos()
        currentpos=self.movePiezoAbsolute(current+distance)
        return currentpos

        
    def movePiezoAbsolute(self, position):
#        originalHandlerIndex= interfaces.stageMover.mover.curHandlerIndex
#        interfaces.stageMover.mover.curHandlerIndex=1
        handler=interfaces.stageMover.mover.axisToHandlers[2][1]
        handler.moveAbsolute(position)
#        interfaces.stageMover.mover.curHandlerIndex=originalHandlerIndex
        return (self.getPiezoPos())
        
## This debugging window lets each digital lineout of the DSP be manipulated
# individually.
class alpaoOutputWindow(wx.Frame):
    def __init__(self, AoDevice, parent, *args, **kwargs):
        wx.Frame.__init__(self, parent, *args, **kwargs)
        ## alpao Device instance.
        self.alpao = AoDevice
        self.SetTitle("Alpao AO device control")
        # Contains all widgets.
        self.panel = wx.Panel(self)
        font=wx.Font(12,wx.FONTFAMILY_DEFAULT,wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        allPositions = interfaces.stageMover.getAllPositions()
        self.piezoPos = allPositions[1][2]
        textSizer=wx.BoxSizer(wx.VERTICAL)
        self.piezoText=wx.StaticText(self.panel,-1,str(self.piezoPos),
                style=wx.ALIGN_CENTER)
        self.piezoText.SetFont(font)
        textSizer.Add(self.piezoText, 0, wx.EXPAND|wx.ALL,border=5)
        mainSizer.Add(textSizer, 0,  wx.EXPAND|wx.ALL,border=5)
        self.panel.SetSizerAndFit(mainSizer)
        events.subscribe('stage position', self.onMove)


    def onMove(self, axis, *args):
        if axis != 2:
            # We only care about the Z axis.
            return
        self.piezoText.SetLabel(
            str(interfaces.stageMover.getAllPositions()[1][2]))


## Debugging function: display a DSPOutputWindow.
def makeOutputWindow(self):
    # HACK: the _deviceInstance object is created by the depot when this
    # device is initialized.
    global _deviceInstance
    alpaoOutputWindow(_deviceInstance, parent = wx.GetApp().GetTopWindow()).Show()
    


