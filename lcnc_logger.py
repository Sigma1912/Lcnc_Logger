#! /usr/bin/python3
#    This is a position logger for LinuxCNC
#    Copyright 2024
#    David Mueller <david_mueller@hotmail.com> 
#
#    Based on earlier work by John Thornton
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os, sys, math

if sys.version_info[0] > 3:
    raise Exception("Python 3 is required.")

import linuxcnc
from PyQt5 import QtCore, uic
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QCheckBox, QRadioButton,
QMessageBox, QFileDialog, QMenu, QWidget)
from PyQt5.QtCore import Qt, QTimer, QEvent, QSettings, QPoint, QRectF 
from PyQt5.QtGui import QCursor, QPainter, QPen, QColor, QImage, QPixmap

from PIL import ImageGrab

#print(os.environ)

print('\n')
print('--- Starting Postion Logger ---')
# the python path will tell us where to point the default file path to
if os.environ.get('PYTHONPATH') == None:
    print('No Python environment variable set. Assuming a deb installation.')    
    FILE_PATH = os.path.expanduser('~') + '/linuxcnc/nc_files'
else:
    PYTHON_PATH = os.environ["PYTHONPATH"]
    print('Python-path is', PYTHON_PATH)
    if 'usr' in PYTHON_PATH:
        print('Detected a package installation.')
        FILE_PATH = os.path.expanduser('~') + '/linuxcnc/nc_files'
    else:
        print('Detected a RIP installation.') 
        FILE_PATH = os.environ["LINUXCNC_NCFILES_DIR"]
print('File-Path is ', FILE_PATH)

GUI_PATH = os.path.dirname(os.path.realpath(__file__)) + '/lcnc_logger.ui'
print('Gui-Path is', GUI_PATH)

global snippingArea
snippingArea = None

# Refer to https://github.com/harupy/snipping-tool
class SnippingWidget(QWidget):
    is_snipping = False

    def __init__(self, parent=None, app=None):
        super(SnippingWidget, self).__init__()
        self.parent = parent
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.screen = app.primaryScreen()
        self.setGeometry(0, 0, self.screen.size().width(), self.screen.size().height())
        self.begin = QPoint()
        self.end = QPoint()
        self.onSnippingCompleted = None

    def takeScreenShot(self):
        global snippingArea
        (x1, y1, x2, y2) = snippingArea
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        if self.onSnippingCompleted is not None:
            self.onSnippingCompleted(img)

    def start(self):
        SnippingWidget.is_snipping = True
        self.setWindowOpacity(0.3)
        QApplication.setOverrideCursor(QCursor(Qt.CrossCursor))
        self.show()

    def paintEvent(self, event):
        if SnippingWidget.is_snipping:
            brush_color = (128, 128, 255, 100)
            lw = 3
            opacity = 0.3
        else:
            self.begin = QPoint()
            self.end = QPoint()
            brush_color = (0, 0, 0, 0)
            lw = 0
            opacity = 0
        self.setWindowOpacity(opacity)
        qp = QPainter(self)
        qp.setPen(QPen(QColor('black'), lw))
        qp.setBrush(QColor(*brush_color))
        rect = QRectF(self.begin, self.end)
        qp.drawRect(rect)

    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.end = self.begin
        self.update()

    def mouseMoveEvent(self, event):
        self.end = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        global snippingArea
        SnippingWidget.is_snipping = False
        QApplication.restoreOverrideCursor()
        x1 = min(self.begin.x(), self.end.x())
        y1 = min(self.begin.y(), self.end.y())
        x2 = max(self.begin.x(), self.end.x())
        y2 = max(self.begin.y(), self.end.y())
        snippingArea = (x1, y1, x2, y2)
        self.repaint()
        QApplication.processEvents()
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
        self.onSnippingCompleted(None)
        self.close()

class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setupLcnc()
        self.setupGui()
        self.setupStyleSheet()
        self.setupConnections()
        self.setupFilters()
        self.setupVars()
        self.setupLogTimer()
        self.qclip = QApplication.clipboard()
        self.loadSettings()
        self.setupSnippingWidget()
        self.show()

    def setupLcnc(self):
        self.s = linuxcnc.stat() # create a connection to the status channel
        try: # make sure linuxcnc is running
            self.s.poll()
        except linuxcnc.error:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle('Error')
            msg.setText('LinuxCNC is not running')
            msg.setInformativeText('Start LinuxCNC first.')
            msg.setStandardButtons(QMessageBox.Ok)
            msg.exec_()
            exit()

    def setupGui(self):
        uic.loadUi(GUI_PATH, self)
        self.setupAxes()
        self.prescriptLW.hide()
        self.prescriptLB.hide()
        self.postscriptLW.hide()
        self.postscriptLB.hide()
        self.positionCB.addItem('Relative', 'relative')
        self.positionCB.addItem('Absolute', 'absolute')
        self.dinLogic.addItem('True', 'true')
        self.dinLogic.addItem('False', 'false')
        self.doutLogic.addItem('True', 'true')
        self.doutLogic.addItem('False', 'false')
        self.ainOnLogic.addItem('<', '<')
        self.ainOnLogic.addItem('>', '>')
        self.ainOnValue.setMaximum(10e6)
        self.ainOnValue.setMinimum(-10e6)
        self.ainOffValue.setMaximum(10e6)
        self.ainOffValue.setMinimum(-10e6)
        self.aoutOnLogic.addItem('<', '<')
        self.aoutOnLogic.addItem('>', '>')
        self.aoutOnValue.setMaximum(10e6)
        self.aoutOnValue.setMinimum(-10e6)
        self.aoutOffValue.setMaximum(10e6)
        self.aoutOffValue.setMinimum(-10e6)
        self.logintervalGB.hide()
        self.digitalinputGB.hide()
        self.analoginputGB.hide()
        self.screenShotGB.hide()
        self.logCommentGB.hide()
        self.moveTypeGB.hide()
        self.screenShotEnableCB.setDisabled(True)
        self.autoIncrementCB.setChecked(True)
        self.imgFileNameLE.setText('lcnc_logger_img')
        self.imgFileIndexInc = 0
        self.imgName = None

    def setupStyleSheet(self):
        self.setStyleSheet('QListWidget::item:selected{background: rgb(0,127,127);}')        

    def setupConnections(self):
        self.actionShow_Digital_Input_Log.changed.connect(self.clickAction)
        self.actionShow_Analog_Input_Log.changed.connect(self.clickAction)
        self.actionShow_Interval_Log.changed.connect(self.clickAction)
        self.actionOpen.triggered.connect(self.openFile)
        self.actionSave.triggered.connect(self.saveFile)
        self.actionSave_As.triggered.connect(self.saveFileAs)
        self.actionExit.triggered.connect(self.exit)
        self.screenShotDefineAreaPB.clicked.connect(self.snippingDefineArea)
        self.logPB.clicked.connect(self.log)
        self.actionCopy.triggered.connect(self.copy)
        self.startPB.clicked.connect(self.record)
        self.stopPB.clicked.connect(self.record)
        self.dinSB.valueChanged.connect(self.changeInput)
        self.doutSB.valueChanged.connect(self.changeInput)
        self.ainOnLogic.currentTextChanged.connect(self.aioLogicChanged)
        self.aoutOnLogic.currentTextChanged.connect(self.aioLogicChanged)
        self.gcodeLW.itemDoubleClicked.connect(self.doubleClickedGcode)
        self.prescriptLW.itemDoubleClicked.connect(self.doubleClickedPrescript)
        self.postscriptLW.itemDoubleClicked.connect(self.doubleClickedPostscript)
        self.prescriptCB.stateChanged.connect(self.prescriptCB_Clicked)
        self.postscriptCB.stateChanged.connect(self.postscriptCB_Clicked)
        self.autosaveCB.stateChanged.connect(self.autosaveCB_Clicked)
        self.savePB.clicked.connect(self.saveFile)
        self.g1RB.toggled.connect(self.check_feed_arc_radius)
        self.g2RB.toggled.connect(self.check_feed_arc_radius)
        self.g3RB.toggled.connect(self.check_feed_arc_radius)
        self.feedLE.textEdited.connect(self.check_feed_arc_radius)
        self.arcRadiusLE.textEdited.connect(self.check_feed_arc_radius)

    def setupFilters(self):
        self.gcodeLW.installEventFilter(self)
        self.prescriptLW.installEventFilter(self)
        self.postscriptLW.installEventFilter(self)

    def setupVars(self):
        self.filePath = FILE_PATH
        self.lastPosition = []
        self.dinLog = False
        self.doutLog = False
        self.ainLog = False
        self.aoutLog = False
        self.dinInput = self.dinSB.value()
        self.doutInput = self.doutSB.value()
        self.ainInput = self.ainSB.value()
        self.aoutInput = self.aoutSB.value()
        self.logToLine = None
        self.listWidgets=[self.gcodeLW, self.prescriptLW, self.postscriptLW]

    def setupLogTimer(self):
        self.timer = QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(100)
        self.recordTimer = QTimer()
        self.recordTimer.timeout.connect(self.log)

    def loadSettings(self):
        QSettings.setPath(QSettings.defaultFormat(), QSettings.UserScope, './lcnc_logger')
        self.settings = QSettings('lcnc_logger')
        print('Config path is ', self.settings.fileName())
        try:
            self.resize(self.settings.value('window size'))
            self.move(self.settings.value('window position'))
            self.lastFilePath = self.settings.value('last filepath')
            if self.settings.value('screenshot on log show') == 'true':
                self.actionShow_Screen_Shot.setChecked(True)
            if self.settings.value('add img file name to log comment') == 'true':
                self.imgFileName2CmntCB.setChecked(True)
            if self.settings.value('move type show') == 'true':
                self.actionShow_Move_Type.setChecked(True)
            if self.settings.value('move type enable') == 'true':
                self.moveTypeEnableCB.setChecked(True)
            if self.settings.value('log comment show') == 'true':
                self.actionShow_Log_Comment.setChecked(True)
            if self.settings.value('digital log show') == 'true':
                self.actionShow_Digital_Input_Log.setChecked(True)
            if self.settings.value('analog log show') == 'true':
                self.actionShow_Analog_Input_Log.setChecked(True)
            if self.settings.value('interval log show') == 'true':
                self.actionShow_Interval_Log.setChecked(True)
            self.feedLE.setText(self.settings.value('feed rate'))
            self.positionCB.setCurrentText((self.settings.value('position mode')).capitalize())
            self.intervalSB.setValue(int(self.settings.value('interval')))
            self.precisionSB.setValue(int(self.settings.value('precision')))
            self.dinSB.setValue(int(self.settings.value('digital input value')))
            self.doutSB.setValue(int(self.settings.value('digital output value')))            
            self.dinLogic.setCurrentText(self.settings.value('digital input logic').capitalize())
            self.doutLogic.setCurrentText(self.settings.value('digital output logic').capitalize())
            self.ainSB.setValue(int(self.settings.value('analog input value')))
            self.ainOnValue.setValue(float(self.settings.value('analog input on value')))
            self.ainOffValue.setValue(float(self.settings.value('analog input off value')))
            self.ainOnLogic.setCurrentText(self.settings.value('analog input on logic'))
            self.aoutSB.setValue(int(self.settings.value('analog output value')))
            self.aoutOnValue.setValue(float(self.settings.value('analog output on value')))
            self.aoutOffValue.setValue(float(self.settings.value('analog output off value')))
            self.aoutOnLogic.setCurrentText(self.settings.value('analog output on logic'))
            # update the off logic field 
            self.aioLogicChanged()
            if self.settings.value('prescript enable') == 'true':
                self.prescriptCB.setChecked(True)
            if self.settings.value('postscript enable') == 'true':
                self.postscriptCB.setChecked(True)
            if self.settings.value('prescript'):
                self.prescriptLW.addItems(self.settings.value('prescript'))
            if self.settings.value('postscript'):
                self.postscriptLW.addItems(self.settings.value('postscript'))
        except Exception as error:
            print(error)

    def closeEvent(self, event):
        prescript = []
        for i in range(self.prescriptLW.count()):
            prescript.append(self.prescriptLW.item(i).text()) 
        postscript = []
        for i in range(self.postscriptLW.count()):
            postscript.append(self.postscriptLW.item(i).text()) 
        self.settings.setValue('window size', self.size())
        self.settings.setValue('window position', self.pos())
        self.settings.setValue('last filepath', self.filePath)
        self.settings.setValue('digital log show', self.actionShow_Digital_Input_Log.isChecked())
        self.settings.setValue('analog log show', self.actionShow_Analog_Input_Log.isChecked())
        self.settings.setValue('interval log show', self.actionShow_Interval_Log.isChecked())
        self.settings.setValue('screenshot on log show', self.actionShow_Screen_Shot.isChecked())
        self.settings.setValue('add img file name to log comment', self.imgFileName2CmntCB.isChecked())
        self.settings.setValue('move type show', self.actionShow_Move_Type.isChecked())
        self.settings.setValue('move type enable', self.moveTypeEnableCB.isChecked())
        self.settings.setValue('log comment show', self.actionShow_Log_Comment.isChecked())
        self.settings.setValue('position mode', self.positionCB.currentData())
        self.settings.setValue('precision', self.precisionSB.value())
        self.settings.setValue('interval', self.intervalSB.value())
        self.settings.setValue('feed rate', self.feedLE.text())
        self.settings.setValue('digital input value', self.dinSB.value())
        self.settings.setValue('digital input logic', self.dinLogic.currentData())
        self.settings.setValue('digital output enable', self.doutCB.isChecked())
        self.settings.setValue('digital output value', self.doutSB.value())
        self.settings.setValue('digital output logic', self.doutLogic.currentData())
        self.settings.setValue('analog input value', self.ainSB.value())
        self.settings.setValue('analog input on value', self.ainOnValue.value())
        self.settings.setValue('analog input on logic', self.ainOnLogic.currentData())
        self.settings.setValue('analog input off value', self.ainOffValue.value())
        self.settings.setValue('analog output value', self.aoutSB.value())
        self.settings.setValue('analog output on value', self.aoutOnValue.value())
        self.settings.setValue('analog output on logic', self.aoutOnLogic.currentData())
        self.settings.setValue('analog output off value', self.aoutOffValue.value())
        self.settings.setValue('prescript enable', self.prescriptCB.isChecked())
        self.settings.setValue('postscript enable', self.postscriptCB.isChecked())
        self.settings.setValue('prescript', prescript)
        self.settings.setValue('postscript', postscript)       

    def eventFilter(self, source, event):
        if (event.type() == QEvent.ContextMenu and source in self.listWidgets):
            # we clear the selections of the other listWidgets in the list                     
            for listWidget in self.listWidgets:
                if listWidget != source: 
                    listWidget.clearSelection()
            contextMenu = QMenu()
            addLineAbove = contextMenu.addAction('Add Line Above')
            addLineBelow = contextMenu.addAction('Add Line Below')
            contextMenu.addSeparator()
            if source is self.gcodeLW: 
                logToLine = contextMenu.addAction('Log to this Line')
            contextMenu.addSeparator()
            deleteLine = contextMenu.addAction('Delete Line')
            deleteAll = contextMenu.addAction('Delete All Lines')
            action = contextMenu.exec_(self.mapToGlobal(event.pos()))
            if action == addLineAbove:
                source.insertItem(source.currentRow(),';new line')
            if action == addLineBelow:
                source.insertItem(source.currentRow()+1,';new line')
            if source is self.gcodeLW: 
                if action == logToLine: 
                    self.logToLine = source.currentRow()
                    self.setStyleSheet('QListWidget::item:selected{background: rgb(254,127,0);}')
            if action == deleteLine:
                source.takeItem(source.currentRow())
            if action == deleteAll:
                button = self.mbox('Delete all items in this list?', 'confirm')
                if button == '&Yes':
                    source.clear()
            return True
        return super(MainWindow, self).eventFilter(source, event)

    def clickAction(self):
        # resize needs to wait a bit for the widget to hide 
        QtCore.QTimer.singleShot(20, self.resizeWindow)

    def resizeWindow(self):
        # get current witdh
        width = QtCore.QSize.width(self.size())
        # get minimum height currently possible
        height = QtCore.QSize.height(self.minimumSizeHint())
        # we keep the width but minimize the window height
        self.resize(width, height)

    def prescriptCB_Clicked(self):
        if self.prescriptCB.isChecked():
            self.prescriptLW.show()
            self.prescriptLB.show()
        else:
            self.prescriptLW.hide()
            self.prescriptLB.hide()
        self.clickAction()

    def postscriptCB_Clicked(self):
        if self.postscriptCB.isChecked():
            self.postscriptLW.show()
            self.postscriptLB.show()
        else:
            self.postscriptLW.hide()
            self.postscriptLB.hide()
        self.clickAction()

    def aioLogicChanged(self):
        if self.ainOnLogic.currentData() == '>':
            self.ainOffLogicLB.setText(' <')
        else:
            self.ainOffLogicLB.setText(' >')
        if self.aoutOnLogic.currentData() == '>':
            self.aoutOffLogicLB.setText(' <')
        else:
            self.aoutOffLogicLB.setText(' >')

    def autosaveCB_Clicked(self):
        if not os.path.isfile(self.filePath):
            self.saveFileAs()

    def doubleClickedGcode(self,item):
        self.logToLine = None
        #QMessageBox.information(self, "ListWidget", "You clicked: "+item.text())
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        self.gcodeLW.editItem(item)
        self.setStyleSheet('QListWidget::item:selected{background: rgb(0,127,127);}')

    def doubleClickedPrescript(self,item):
        self.logToLine = None
        #QMessageBox.information(self, "ListWidget", "You clicked: "+item.text())
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        self.prescriptLW.editItem(item)
        self.setStyleSheet('QListWidget::item:selected{background: rgb(0,127,127);}')

    def doubleClickedPostscript(self,item):
        self.logToLine = None
        #QMessageBox.information(self, "ListWidget", "You clicked: "+item.text())
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        self.postscriptLW.editItem(item)
        self.setStyleSheet('QListWidget::item:selected{background: rgb(0,127,127);}')

    def setupAxes(self):
        self.axes = [(i) for i in range(9)if self.s.axis_mask & (1<<i)]
        self.axes_letters = ['X', 'Y', 'Z', 'A', 'B', 'C', 'U', 'V', 'W']
        # initialize variables for the axis-checkboxes and position-labels
        for i in range(9):
            setattr(self, 'axisCB_' + str(i), None)                    
            setattr(self, 'positionLB_' + str(i), None)
        # organize the checkboxes and labels in two lists
        self.axis_cbs = [self.axisCB_0, self.axisCB_1, self.axisCB_2, self.axisCB_3,
                         self.axisCB_4, self.axisCB_5, self.axisCB_6, self.axisCB_7, self.axisCB_8]
        self.position_lbs = [self.positionLB_0, self.positionLB_1, self.positionLB_2, self.positionLB_3,
                             self.positionLB_4, self.positionLB_5, self.positionLB_6, self.positionLB_7,
                             self.positionLB_8]
        # for each active axis we create a QCheckBox and a QLabel widget using the respective list 
        # and arrange them in a grid
        (row, col) = (0,0)
        self.activeAxesdLayout.setSpacing(2)          
        for i in range(9):
            if self.s.axis_mask & (1<<i):
                self.axis_cbs[i] = QCheckBox(self.axes_letters[i]+':')
                self.activeAxesdLayout.addWidget(self.axis_cbs[i],row,col)
                self.axis_cbs[i].setChecked(True)
                self.position_lbs[i] = QLabel('pos'+str(i))
                self.activeAxesdLayout.addWidget(self.position_lbs[i],row,col+1)
                self.position_lbs[i].setMinimumWidth(60)
                row += 1
                if row == 6: 
                    (col,row) = (2,0)

    def setupSnippingWidget(self):
        self.snippingWidget = SnippingWidget(app=QApplication.instance())
        self.snippingWidget.onSnippingCompleted = self.onSnippingCompleted
        self._pixmap = None

    def onSnippingCompleted(self, frame):
        self.setWindowState(Qt.WindowActive)
        if frame is None:
            return 
        if self.filePath is tuple:
            path = self.filePath[0]
        else:
            path = self.filePath
        if os.path.isfile(path):
            path = os.path.dirname(path)
        print('path is: ',path)
        img_dir_path = os.path.join(path, 'lcnc_logger_images') 
        try: 
            os.makedirs(img_dir_path, exist_ok = True) 
            print("Directory '%s' created successfully" % img_dir_path) 
        except OSError as error: 
            print("Directory '%s' can not be created" % img_dir_path) 
       
        img_file_path = os.path.join(img_dir_path, self.imgName) 
        frame.save(img_file_path)
        if self.autoIncrementCB.isChecked():
            self.imgFileIndexSB.setValue(self.imgFileIndexSB.value() + 1)
        
    def snipArea(self):
        self.setWindowState(Qt.WindowMinimized)
        self.snippingWidget.start()    

    def snipFull(self):
        self.setWindowState(Qt.WindowMinimized)
        self.snippingWidget.takeScreenShot()   

    def resizeImage(self, pixmap):
        lwidth = self.ui.label.width()
        pwidth = pixmap.width()
        lheight = self.ui.label.height()
        pheight = pixmap.height()

        wratio = pwidth * 1.0 / lwidth
        hratio = pheight * 1.0 / lheight

        if pwidth > lwidth or pheight > lheight:
            if wratio > hratio:
                lheight = pheight / wratio
            else:
                lwidth = pwidth / hratio

            scaled_pixmap = pixmap.scaled(lwidth, lheight)
            return scaled_pixmap
        else:
            return pixmap

    def snippingDefineArea(self): 
        global snippingArea
        self.snipArea()
        if snippingArea != (0,0,0,0):
            self.screenShotEnableCB.setEnabled(True)

    def check_feed_arc_radius(self):
        # check feed entry
        if (self.g1RB.isChecked() == True or self.g2RB.isChecked() == True or self.g3RB.isChecked() == True): 
            self.check_lineEdit(self.feedLE)
        else:
            self.feedLE.setStyleSheet("background: white;")
        # check arc-radius entry  
        if (self.g2RB.isChecked() == True or self.g3RB.isChecked() == True): 
            self.check_lineEdit(self.arcRadiusLE)
        else:
            self.arcRadiusLE.setStyleSheet("background: white;")

    def check_lineEdit(self, lineEdit):
        if not lineEdit.text() or float(lineEdit.text() == 0):
            lineEdit.setStyleSheet("background: yellow;")
            return
        try:
            float(lineEdit.text())
        except:
            lineEdit.setStyleSheet("background: red;")
            return
        if float(lineEdit.text()) < 0:
            lineEdit.setStyleSheet("background: red;")
            return            
        lineEdit.setStyleSheet("background: white;")

    def changeInput(self):
        self.dinInput = self.dinSB.value()
        self.doutInput = self.doutSB.value()

    def openFile(self):
        if not os.path.isfile(self.filePath) and self.lastFilePath and os.path.isfile(self.lastFilePath):
            path = self.lastFilePath
        else:
            path = self.filePath
        print('my path: ', path)
        fileName = QFileDialog.getOpenFileName(self,
            caption="Select a G code File",
            directory = path,
            filter='GCode(*.ngc);;TextLog(*.txt)',
            options=QFileDialog.DontUseNativeDialog,)
        if fileName[0]:
            self.gcodeLW.clear()
            if self.prescriptCB.isChecked(): 
                self.prescriptLW.clear()
            if self.postscriptCB.isChecked(): 
                self.postscriptLW.clear()
            gcode_type = 'log'
            with open(fileName[0], 'r') as f:
                for line in f:  
                    line=line.strip('\n')
                    if line == ';prescript_start':
                        gcode_type = 'prescript'
                    elif line == ';prescript_end':
                        gcode_type = 'log'
                    elif line == ';postscript_start':
                        gcode_type = 'postscript'
                    elif line == ';postscript_end':
                        gcode_type = 'log'
                    elif gcode_type == 'prescript':
                        if self.prescriptCB.isChecked(): 
                            self.prescriptLW.addItem(line)
                    elif gcode_type == 'log': 
                        self.gcodeLW.addItem(line)
                    elif gcode_type == 'postscript': 
                        if self.postscriptCB.isChecked(): 
                            self.postscriptLW.addItem(line)
            # update the file path 
            self.filePath = fileName[0]
            self.gcodeLB.setText(fileName[0])

    def saveFile(self):
        if self.filePath and os.path.isfile(self.filePath):
            self.save(self.filePath)
        else:
            self.saveFileAs()

    def saveFileAs(self):
        if self.filePath is tuple:
            path = self.filePath[0]
        else:
            path = self.filePath
        fileName, _ = QFileDialog.getSaveFileName(self,
        caption="Save G Code",
        directory = path,
        filter=("GCode(*.ngc);;TextLog(*.txt)"),
        options=QFileDialog.DontUseNativeDialog)
        if fileName:
            # update the file path 
            self.filePath = fileName
            self.gcodeLB.setText(fileName)
            self.save(fileName)

    def save(self, fileName):
        prescript = '\n'.join(self.prescriptLW.item(i).text() for i in range(self.prescriptLW.count()))
        gcode = '\n'.join(self.gcodeLW.item(i).text() for i in range(self.gcodeLW.count()))
        postscript = '\n'.join(self.postscriptLW.item(i).text() for i in range(self.postscriptLW.count()))
        with open(self.filePath, 'w') as f:
            if self.prescriptCB.isChecked():
                f.write(';prescript_start\n')
                f.write(prescript) 
                f.write('\n;prescript_end\n')
            f.write(gcode)
            if self.postscriptCB.isChecked():
                f.write('\n;postscript_start\n')
                f.write(postscript)
                f.write('\n;postscript_end\n')

    def record(self):
        if self.startPB.isChecked():
            print('Starting {}'.format(self.intervalSB.value()))
            timerInterval = self.intervalSB.value() * 1000
            self.recordTimer.start(timerInterval)
        elif self.stopPB.isChecked():
            print('Stopping')
            self.recordTimer.stop()

    def log(self):
        self.logComment = self.logCommentLE.text()
        if self.screenShotEnableCB.isChecked(): 
            img_index = self.imgFileIndexSB.value()
            self.imgName = self.imgFileNameLE.text() + '_' + str(self.imgFileIndexSB.value()) + '.png'
            if self.imgFileName2CmntCB.isChecked():
                self.logComment = self.logCommentLE.text() + ' ' +  self.imgName
            self.snipFull()
        axes = []
        for cb in range(len(self.axis_cbs)): # get axes list
            if self.axis_cbs[cb] != None and self.axis_cbs[cb].isChecked():
                axes.append(cb)
        currentPosition = []
        gcode = []
        if self.moveTypeEnableCB.isChecked():
            for radio in self.moveTypeGB.findChildren(QRadioButton):
                if radio.isChecked(): # add the move type
                    gcode.append(str(radio.property('gcode')) + ' ')
                    moveType = str(radio.property('gcode'))
            for axis in axes: # add each axis position
                position = self.position_lbs[axis].text()
                currentPosition.append(float(position))
                gcode.append(self.axes_letters[axis] + position + ' ')

            if moveType in ['G1', 'G2', 'G3']: # check for a feed rate
                if not 'background: white' in self.feedLE.styleSheet():
                    self.mbox('A feed rate must be entered for a {} move'.format(moveType), 'critical')
                    return
                gcode.append('F{}'.format(str(self.feedLE.text())))
                if moveType in ['G2', 'G3']:
                    if not 'background: white' in self.arcRadiusLE.styleSheet():
                        self.mbox('{} moves require an arc radius'.format(moveType), 'critical')
                        return
                    if len(self.lastPosition) == 0:
                        self.mbox('A G0 or G1 move must be done before a {} move'.format(moveType), 'critical')
                    dx = currentPosition[0] - self.lastPosition[0]
                    dy = currentPosition[1] - self.lastPosition[1]
                    if dx == 0 and dy == 0:
                        self.mbox('{} move needs a different end point'.format(moveType), 'critical')
                        return
                    # calculate angle of travel
                    angle = math.atan2(dy,dx)
                    # calculate the midpoint of the segment
                    (dxMid,dyMid) = (dx/2, dy/2)
                    # calculate the distance traveled 
                    distance = math.sqrt(dx**2 + dy**2)
                    # get requested radius
                    radius = float(self.arcRadiusLE.text())
                    if radius < (distance / 2):
                        self.mbox('Radius can not be smaller than {0:0.4f}'.format(distance/2), 'critical')
                        return
                    # calculate the distance of the arc-center from the mid-point
                    center_offset = math.sqrt(radius**2-(distance/2)**2)
                    if moveType == 'G2':
                        # arc-center is offset -90° from midpoint of the traveled segment 
                        offset_angle = angle-math.pi/2
                        i = dxMid + center_offset * math.cos(offset_angle)
                        j = dyMid + center_offset * math.sin(offset_angle)
                        gcode.append(' I{0:.{2}f} J{1:.{2}f}'.format(i, j, self.precisionSB.value()))
                    elif moveType == 'G3':
                        # arc-center is offset +90° from midpoint of the traveled segment
                        offset_angle = angle+math.pi/2
                        i = dxMid + center_offset * math.cos(offset_angle)
                        j = dyMid + center_offset * math.sin(offset_angle)
                        gcode.append(' I{0:.{2}f} J{1:.{2}f}'.format(i, j, self.precisionSB.value()))
            if self.logCommentLE.text() != '':    
                gcode.append(' ;' + self.logComment)
        else:
            for axis in axes: # add each axis position
                position = self.position_lbs[axis].text()
                currentPosition.append(float(position))
                gcode.append(position + ', ')
            gcode.append(self.logComment)
        if self.logToLine != None:
            # insert the logged values 
            self.gcodeLW.insertItem(self.logToLine, ''.join(gcode))
            # remove the original line that is now below
            self.gcodeLW.takeItem(self.logToLine+1)
            self.setStyleSheet('QListWidget::item:selected{background: rgb(0,127,127);}')
        else:
            self.gcodeLW.addItem(''.join(gcode))
        self.lastPosition = []
        for axis in axes:
            self.lastPosition.append(float(self.position_lbs[axis].text()))
        self.logToLine = None
        if self.autosaveCB.isChecked():
            self.saveFile()

    def update(self):
        self.s.poll()
        if self.positionCB.currentData() == 'relative':
            # sum the offsets with a negative sign
            offsets = tuple(-sum(i) for i in zip(self.s.g5x_offset,self.s.g92_offset,self.s.tool_offset))
            display = tuple(sum(i) for i in zip(offsets,self.s.actual_position))
        else:
            display = self.s.actual_position
        for i in self.axes:
            if self.position_lbs[i] != None:
                self.position_lbs[i].setText('{0:0.{1}f}'.format(display[i],
                    self.precisionSB.value()))
        # log on digital input
        if self.dinLogic.currentData() == 'true':
            if self.s.din[self.dinInput] and self.dinCB.isChecked() and not self.dinLog:
                self.log()
                self.dinLog = True
            elif not self.s.din[self.dinInput] and self.dinLog:
                self.dinLog = False
        else:
            if not self.s.din[self.dinInput] and self.dinCB.isChecked() and not self.dinLog:
                self.log()
                self.dinLog = True
            elif self.s.din[self.dinInput] and self.dinLog:
                self.dinLog = False
        # log on digital output
        if self.doutLogic.currentData() == 'true':
            if self.s.dout[self.doutInput] and self.doutCB.isChecked() and not self.doutLog:
                self.log()
                self.doutLog = True
            elif not self.s.dout[self.doutInput] and self.doutLog:
                self.doutLog = False
        else:
            if not self.s.dout[self.doutInput] and self.doutCB.isChecked() and not self.doutLog:
                self.log()
                self.doutLog = True
            elif self.s.dout[self.doutInput] and self.doutLog:
                self.doutLog = False
        # log on analog input
        if self.ainOnLogic.currentData() == '>' and (self.ainOnValue.value() > self.ainOffValue.value()):
            if self.s.ain[self.ainInput] > self.ainOnValue.value() and self.ainCB.isChecked() and not self.ainLog:
                self.log()
                self.ainLog = True
            elif  self.s.ain[self.ainInput] < self.ainOffValue.value() and self.ainLog:
                self.ainLog = False
            self.ainOnValue.setStyleSheet("background: white;")
            self.ainOffValue.setStyleSheet("background: white;")
        elif self.ainOnLogic.currentData() == '<' and (self.ainOnValue.value() < self.ainOffValue.value()):
            if self.s.ain[self.ainInput] < self.ainOnValue.value() and self.ainCB.isChecked() and not self.ainLog:
                self.log()
                self.ainLog = True
            elif  self.s.ain[self.ainInput] > self.ainOffValue.value() and self.ainLog:
                self.ainLog = False
            self.ainOnValue.setStyleSheet("background: white;")
            self.ainOffValue.setStyleSheet("background: white;")
        else:
            self.ainOnValue.setStyleSheet("background: yellow;")
            self.ainOffValue.setStyleSheet("background: yellow;")
        # log on analog output
        if self.aoutOnLogic.currentData() == '>' and (self.aoutOnValue.value() > self.aoutOffValue.value()):
            if self.s.aout[self.aoutInput] > self.aoutOnValue.value() and self.aoutCB.isChecked() and not self.aoutLog:
                self.log()
                self.aoutLog = True
            elif  self.s.aout[self.aoutInput] < self.aoutOffValue.value() and self.aoutLog:
                self.aoutLog = False
            self.aoutOnValue.setStyleSheet("background: white;")
            self.aoutOffValue.setStyleSheet("background: white;")
        elif self.aoutOnLogic.currentData() == '<' and (self.aoutOnValue.value() < self.aoutOffValue.value()):
            if self.s.aout[self.aoutInput] < self.aoutOnValue.value() and self.aoutCB.isChecked() and not self.aoutLog:
                self.log()
                self.aoutLog = True
            elif  self.s.aout[self.aoutInput] > self.aoutOffValue.value() and self.aoutLog:
                self.aoutLog = False
            self.aoutOnValue.setStyleSheet("background: white;")
            self.aoutOffValue.setStyleSheet("background: white;")
        else:
            self.aoutOnValue.setStyleSheet("background: yellow;")
            self.aoutOffValue.setStyleSheet("background: yellow;")

    def copy(self):
        items = []
        gcode = [str(self.gcodeLW.item(i).text()) for i in range(self.gcodeLW.count())]
        self.qclip.setText('\n'.join(gcode))

    def mbox(self, message, style):
        msg = QMessageBox()
        if style == 'critical':
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle('Error')
            msg.setText(message)
            msg.setStandardButtons(QMessageBox.Ok)
        elif style == 'confirm':
            msg.setIcon(QMessageBox.Question)
            msg.setWindowTitle('User Confirmation')
            msg.setText(message)
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.exec_()
        button = msg.clickedButton()
        if button is not None:
            return button.text()

    def exit(self):
        exit()

def main():
    app = QApplication(sys.argv)
    ex = MainWindow()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
