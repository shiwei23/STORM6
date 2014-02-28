#!/usr/bin/python
# ----------------------------------------------------------------------------------------
# A master control class to implemented a series of automated flow protocols
# using a daisy chained valve system (and eventually syringe pumps)
# ----------------------------------------------------------------------------------------
# Jeff Moffitt
# 12/28/13
# jeffmoffitt@gmail.com
# ----------------------------------------------------------------------------------------

# ----------------------------------------------------------------------------------------
# Import
# ----------------------------------------------------------------------------------------
import sys
import os
import time
from PyQt4 import QtCore, QtGui
from valves.valveChain import ValveChain
from pumps.pumpControl import PumpControl
from kilroyProtocols import KilroyProtocols
from kilroyServer import KilroyServer
import sc_library.parameters as params

# ----------------------------------------------------------------------------------------
# Kilroy Class Definition
# ----------------------------------------------------------------------------------------
class Kilroy(QtGui.QMainWindow):
    def __init__(self, parameters):
        super(Kilroy, self).__init__()

        # Parse parameters into internal attributes
        self.verbose = parameters.verbose
        self.valve_com_port = parameters.valves_com_port
        self.tcp_port = parameters.tcp_port
        self.pump_com_port = parameters.pump_com_port
        self.pump_ID = parameters.pump_ID
        if not hasattr(parameters, "num_simulated_valves"):
            self.num_simulated_valves = 0
        else:
            self.num_simulated_valves = parameters.num_simulated_valves
        if not hasattr(parameters, "protocols_file"):
            self.protocols_file = "default_config.xml"
        else:
            self.protocols_file = parameters.protocols_file
        if not hasattr(parameters, "commands_file"):
            self.commands_file = "default_config.xml"
        else:
            self.commands_file = parameters.commands_file
        if not hasattr(parameters, "simulate_pump"):
            self.simulate_pump = False
        else:
            self.simulate_pump = parameters.simulate_pump

        # Define additional internal attributes
        self.sent_protocol_names = []
        self.sent_protocol_UIDs = []
        
        # Create ValveChain instance
        self.valveChain = ValveChain(com_port = self.valve_com_port,
                                     num_simulated_valves = self.num_simulated_valves,
                                     verbose = self.verbose)

        # Create PumpControl instance
        self.pumpControl = PumpControl(com_port = self.pump_com_port,
                                       pump_ID = self.pump_ID,
                                       simulate = self.simulate_pump,
                                       verbose = self.verbose)
                                       
        # Create KilroyProtocols instance and connect signals
        self.kilroyProtocols = KilroyProtocols(protocol_xml_path = self.protocols_file,
                                               command_xml_path = self.commands_file,
                                               verbose = self.verbose)

        self.kilroyProtocols.command_ready_signal.connect(self.sendCommand)
        self.kilroyProtocols.status_change_signal.connect(self.handleProtocolStatusChange)
        self.kilroyProtocols.completed_protocol_signal.connect(self.handleProtocolComplete)

        # Create Kilroy TCP Server and connect signals
        self.tcpServer = KilroyServer(port = self.tcp_port,
                                      verbose = self.verbose)
        
        self.tcpServer.data_ready.connect(self.handleTCPData)

        # Create GUI
        self.createGUI()

    # ----------------------------------------------------------------------------------------
    # Close
    # ----------------------------------------------------------------------------------------
    def close(self):
        self.kilroyProtocols.close()
        self.tcpServer.close()
        self.valveChain.close()
        self.pumpControl.close()
        print "\nKilroy was here!"

    # ----------------------------------------------------------------------------------------
    # Create master GUI
    # ----------------------------------------------------------------------------------------
    def createGUI(self):
        self.mainLayout = QtGui.QGridLayout()
        self.mainLayout.addWidget(self.kilroyProtocols.mainWidget, 0, 0, 2, 2)
        self.mainLayout.addWidget(self.kilroyProtocols.valveCommands.mainWidget, 2, 0, 1, 1)
        self.mainLayout.addWidget(self.kilroyProtocols.pumpCommands.mainWidget, 2, 1, 1, 1)
        self.mainLayout.addWidget(self.valveChain.mainWidget, 0, 2, 2, 2)
        self.mainLayout.addWidget(self.pumpControl.mainWidget, 0, 4, 2, 1)
        self.mainLayout.addWidget(self.tcpServer.mainWidget, 2, 2, 1, 4)

    # ----------------------------------------------------------------------------------------
    # Redirect protocol status change from kilroyProtocols to valveChain
    # ----------------------------------------------------------------------------------------
    def handleProtocolStatusChange(self):
        status = self.kilroyProtocols.getStatus()
        if status[0] >= 0: # Protocol is running
            self.valveChain.setEnabled(False)
            self.pumpControl.setEnabled(False)
        else:
            self.valveChain.setEnabled(True)
            self.pumpControl.setEnabled(True)

    # ----------------------------------------------------------------------------------------
    # Handle a protocol complete signal from the valve protocols
    # ----------------------------------------------------------------------------------------
    def handleProtocolComplete(self, protocol_UID):
        # If the protocol was sent by TCP pass on the complete signal
        if protocol_UID in self.sent_protocol_UIDs:
            list_ID = self.sent_protocol_UIDs.index(protocol_UID)
            protocol_name = self.sent_protocol_names.pop(list_ID)
            protocol_UID = self.sent_protocol_UIDs.pop(list_ID)
            self.tcpServer.sendProtocolComplete(protocol_name, protocol_UID)

    # ----------------------------------------------------------------------------------------
    # Handle protocol request sent via TCP server
    # ----------------------------------------------------------------------------------------
    def handleTCPData(self):
        # Get protocol from tcpServer
        [protocol_name, protocol_UID] = self.tcpServer.getProtocol()
        
        if self.verbose:
            print "Received Protocol from Kilroy Client: " + protocol_name
            print " with unique ID: " + protocol_UID
            
        if self.kilroyProtocols.isValidProtocol(protocol_name):
            # Keep track of protocols issued via TCP 
            self.sent_protocol_names.append(protocol_name)
            self.sent_protocol_UIDs.append(protocol_UID)
            
            # Start the protocol
            self.kilroyProtocols.startProtocolRemotely(protocol_name, protocol_UID)

        else: # Respond with a protocol complete to cancel the invalid protocol
            self.tcpServer.sendProtocolComplete(protocol_name, protocol_UID)
            
    # ----------------------------------------------------------------------------------------
    # Redirect commands from kilroy protocol class to valves or pump
    # ----------------------------------------------------------------------------------------
    def sendCommand(self):
        command_data = self.kilroyProtocols.getCurrentCommand()
        if command_data[0] == "valve":
            self.valveChain.receiveCommand(command_data[1])
        elif command_data[0] == "pump":
            self.pumpControl.receiveCommand(command_data[1])
        else:
            print "Received command of unknown type: " + str(command_data[0])

# ----------------------------------------------------------------------------------------
# Stand Alone Kilroy Class
# ----------------------------------------------------------------------------------------                                                                   
class StandAlone(QtGui.QMainWindow):
    def __init__(self, parameters, parent = None):
        super(StandAlone, self).__init__(parent)

        # Create kilroy
        self.kilroy = Kilroy(parameters)
                                          
        # central widget
        self.centralWidget = QtGui.QWidget()
        self.centralWidget.setLayout(self.kilroy.mainLayout)

        # set central widget
        self.setCentralWidget(self.centralWidget)

        # set window title
        self.setWindowTitle("Kilroy")

        # set window geometry
        self.setGeometry(50, 50, 1200, 800)

        # Define close menu item
        exit_action = QtGui.QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)

        # Add menu items
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        for menu_item in self.kilroy.kilroyProtocols.menu_items[0]:
            file_menu.addAction(menu_item)
        file_menu.addAction(exit_action)

        valve_menu = menubar.addMenu("&Valves")
        for menu_item in self.kilroy.valveChain.menu_items[0]:
            valve_menu.addAction(menu_item)

    # ----------------------------------------------------------------------------------------
    # Handle close event
    # ----------------------------------------------------------------------------------------
    def closeEvent(self, event):
        self.kilroy.close()
        self.close()

# ----------------------------------------------------------------------------------------
# Runtime code: Kilroy is meant to be run as a stand alone
# ----------------------------------------------------------------------------------------                                
if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)

    # Show splash screen (to allow for valve initialization)
    splash_pix = QtGui.QPixmap("kilroy_splash.jpg")
    splash = QtGui.QSplashScreen(splash_pix, QtCore.Qt.WindowStaysOnTopHint)
    splash.setMask(splash_pix.mask())
    splash.show()
    app.processEvents()
    time.sleep(.1) # Define minimum startup time

    # Load parameters
    if len(sys.argv) == 2:
        parameters = params.Parameters(sys.argv[1])
    else:
        parameters = params.Parameters("kilroy_settings_default.xml")

    # Create instance of StandAlone class
    window = StandAlone(parameters)

    # Remove splash screen
    splash.hide()

    # Run main app
    window.show()
    sys.exit(app.exec_())
