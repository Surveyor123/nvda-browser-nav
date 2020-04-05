#A part of the BrowserNav addon for NVDA
#Copyright (C) 2017-2019 Tony Malykh
#This file is covered by the GNU General Public License.
#See the file LICENSE  for more details.

# This addon allows to navigate documents by indentation or offset level.
# In browsers you can navigate by object location on the screen.
# In editable text fields you can navigate by the indentation level.
# This is useful for editing source code.
# Author: Tony Malykh <anton.malykh@gmail.com>
# https://github.com/mltony/nvda-indent-nav/
# Original author: Sean Mealin <spmealin@gmail.com>

import addonHandler
import api
import browseMode
import controlTypes
import config
import core
import ctypes
import globalPluginHandler
import gui
import inputCore
import keyboardHandler
from logHandler import log
import nvwave
import NVDAHelper
import operator
import re
import scriptHandler
from scriptHandler import script
import speech
import struct
import textInfos
import time
import tones
import types
import ui
import winUser
import wx

debug = True
if debug:
    f = open("C:\\Users\\tony\\Dropbox\\2.txt", "w")
def mylog(s):
    if debug:
        print(str(s), file=f)
        f.flush()


def myAssert(condition):
    if not condition:
        raise RuntimeError("Assertion failed")


def initConfiguration():
    confspec = {
        "crackleVolume" : "integer( default=25, min=0, max=100)",
        "noNextTextChimeVolume" : "integer( default=50, min=0, max=100)",
        "noNextTextMessage" : "boolean( default=True)",
        "browserMode" : "integer( default=0, min=0, max=2)",
        "useFontFamily" : "boolean( default=True)",
        "useColor" : "boolean( default=True)",
        "useBackgroundColor" : "boolean( default=True)",
        "useBoldItalic" : "boolean( default=True)",
        "marks" : "string( default='(^upvote$|^up vote$)')",
    }
    config.conf.spec["browsernav"] = confspec

browseModeGestures = {
    "kb:NVDA+Alt+DownArrow" :"moveToNextSibling",
}

def getConfig(key):
    value = config.conf["browsernav"][key]
    return value

def setConfig(key, value):
    config.conf["browsernav"][key] = value


addonHandler.initTranslation()
initConfiguration()

class SettingsDialog(gui.SettingsDialog):
    # Translators: Title for the settings dialog
    title = _("BrowserNav settings")

    def __init__(self, *args, **kwargs):
        super(SettingsDialog, self).__init__(*args, **kwargs)

    def makeSettings(self, settingsSizer):
        sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
      # crackleVolumeSlider
        sizer=wx.BoxSizer(wx.HORIZONTAL)
        # Translators: volume of crackling slider
        label=wx.StaticText(self,wx.ID_ANY,label=_("Crackling volume"))
        slider=wx.Slider(self, wx.NewId(), minValue=0,maxValue=100)
        slider.SetValue(getConfig("crackleVolume"))
        sizer.Add(label)
        sizer.Add(slider)
        settingsSizer.Add(sizer)
        self.crackleVolumeSlider = slider

      # noNextTextChimeVolumeSlider
        sizer=wx.BoxSizer(wx.HORIZONTAL)
        # Translators: End of document chime volume
        label=wx.StaticText(self,wx.ID_ANY,label=_("Volume of chime when no more sentences available"))
        slider=wx.Slider(self, wx.NewId(), minValue=0,maxValue=100)
        slider.SetValue(getConfig("noNextTextChimeVolume"))
        sizer.Add(label)
        sizer.Add(slider)
        settingsSizer.Add(sizer)
        self.noNextTextChimeVolumeSlider = slider

      # Checkboxes
        # Translators: Checkbox that controls spoken message when no next or previous text paragraph is available in the document
        label = _("Speak message when no next paragraph containing text available in the document")
        self.noNextTextMessageCheckbox = sHelper.addItem(wx.CheckBox(self, label=label))
        self.noNextTextMessageCheckbox.Value = getConfig("noNextTextMessage")

        # Translators: Checkbox that controls whether font family should be used for style
        label = _("Use font family for style")
        self.useFontFamilyCheckBox = sHelper.addItem(wx.CheckBox(self, label=label))
        self.useFontFamilyCheckBox.Value = getConfig("useFontFamily")

        # Translators: Checkbox that controls whether font color should be used for style
        label = _("Use font color for style")
        self.useColorCheckBox = sHelper.addItem(wx.CheckBox(self, label=label))
        self.useColorCheckBox.Value = getConfig("useColor")

        # Translators: Checkbox that controls whether background color should be used for style
        label = _("Use background color for style")
        self.useBackgroundColorCheckBox = sHelper.addItem(wx.CheckBox(self, label=label))
        self.useBackgroundColorCheckBox.Value = getConfig("useBackgroundColor")

        # Translators: Checkbox that controls whether bold and italic should be used for style
        label = _("Use bold and italic attributes for style")
        self.useBoldItalicCheckBox = sHelper.addItem(wx.CheckBox(self, label=label))
        self.useBoldItalicCheckBox.Value = getConfig("useBoldItalic")
      # BrowserMarks regexp text edit
        self.marksEdit = gui.guiHelper.LabeledControlHelper(self, _("Browser marks regexp"), wx.TextCtrl).control
        self.marksEdit.Value = getConfig("marks")


    def onOk(self, evt):
        config.conf["browsernav"]["crackleVolume"] = self.crackleVolumeSlider.Value
        config.conf["browsernav"]["noNextTextChimeVolume"] = self.noNextTextChimeVolumeSlider.Value
        config.conf["browsernav"]["noNextTextMessage"] = self.noNextTextMessageCheckbox.Value
        config.conf["browsernav"]["useFontFamily"] = self.useFontFamilyCheckBox.Value
        config.conf["browsernav"]["useColor"] = self.useColorCheckBox.Value
        config.conf["browsernav"]["useBackgroundColor"] = self.useBackgroundColorCheckBox.Value
        config.conf["browsernav"]["useBoldItalic"] = self.useBoldItalicCheckBox.Value
        config.conf["browsernav"]["marks"] = self.marksEdit.Value
        super(SettingsDialog, self).onOk(evt)


def getMode():
    return getConfig("browserMode")

# Browse mode constants:
BROWSE_MODES = [
    _("horizontal offset"),
    _("font size"),
    _("font size and same style"),
]

PARENT_OPERATORS = [operator.lt, operator.gt, operator.gt]
CHILD_OPERATORS = [operator.gt, operator.lt, operator.lt]
OPERATOR_STRINGS = {
    operator.lt: _("smaller"),
    operator.gt: _("greater"),
}

controlCharacter = "➉" # U+2789, Dingbat circled sans-serif digit ten
kbdControlC = keyboardHandler.KeyboardInputGesture.fromName("Control+c")
kbdControlV = keyboardHandler.KeyboardInputGesture.fromName("Control+v")
kbdControlA = keyboardHandler.KeyboardInputGesture.fromName("Control+a")
kbdControlHome = keyboardHandler.KeyboardInputGesture.fromName("Control+Home")
kbdControlEnd = keyboardHandler.KeyboardInputGesture.fromName("Control+End")
kbdBackquote = keyboardHandler.KeyboardInputGesture.fromName("`")
kbdDelete = keyboardHandler.KeyboardInputGesture.fromName("Delete")

allModifiers = [
    winUser.VK_LCONTROL, winUser.VK_RCONTROL,
    winUser.VK_LSHIFT, winUser.VK_RSHIFT, winUser.VK_LMENU,
    winUser.VK_RMENU, winUser.VK_LWIN, winUser.VK_RWIN,
]

def executeAsynchronously(gen):
    """
    This function executes a generator-function in such a manner, that allows updates from the operating system to be processed during execution.
    For an example of such generator function, please see GlobalPlugin.script_editJupyter.
    Specifically, every time the generator function yilds a positive number,, the rest of the generator function will be executed
    from within wx.CallLater() call.
    If generator function yields a value of 0, then the rest of the generator function
    will be executed from within wx.CallAfter() call.
    This allows clear and simple expression of the logic inside the generator function, while still allowing NVDA to process update events from the operating system.
    Essentially the generator function will be paused every time it calls yield, then the updates will be processed by NVDA and then the remainder of generator function will continue executing.
    """
    if not isinstance(gen, types.GeneratorType):
        raise Exception("Generator function required")
    try:
        value = gen.__next__()
    except StopIteration:
        return
    l = lambda gen=gen: executeAsynchronously(gen)
    if value == 0:
        wx.CallAfter(l)
    else:
        wx.CallLater(value, l)

class EditBoxUpdateError(Exception):
    def __init__(self, *args, **kwargs):
        super(EditBoxUpdateError, self).__init__(*args, **kwargs)

class Beeper:
    BASE_FREQ = speech.IDT_BASE_FREQUENCY
    def getPitch(self, indent):
        return self.BASE_FREQ*2**(indent/24.0) #24 quarter tones per octave.

    BEEP_LEN = 10 # millis
    PAUSE_LEN = 5 # millis
    MAX_CRACKLE_LEN = 400 # millis
    MAX_BEEP_COUNT = MAX_CRACKLE_LEN // (BEEP_LEN + PAUSE_LEN)

    def __init__(self):
        self.player = nvwave.WavePlayer(
            channels=2,
            samplesPerSec=int(tones.SAMPLE_RATE),
            bitsPerSample=16,
            outputDevice=config.conf["speech"]["outputDevice"],
            wantDucking=False
        )



    def fancyCrackle(self, levels, volume):
        levels = self.uniformSample(levels, self.MAX_BEEP_COUNT )
        beepLen = self.BEEP_LEN
        pauseLen = self.PAUSE_LEN
        pauseBufSize = NVDAHelper.generateBeep(None,self.BASE_FREQ,pauseLen,0, 0)
        beepBufSizes = [NVDAHelper.generateBeep(None,self.getPitch(l), beepLen, volume, volume) for l in levels]
        bufSize = sum(beepBufSizes) + len(levels) * pauseBufSize
        buf = ctypes.create_string_buffer(bufSize)
        bufPtr = 0
        for l in levels:
            bufPtr += NVDAHelper.generateBeep(
                ctypes.cast(ctypes.byref(buf, bufPtr), ctypes.POINTER(ctypes.c_char)),
                self.getPitch(l), beepLen, volume, volume)
            bufPtr += pauseBufSize # add a short pause
        self.player.stop()
        self.player.feed(buf.raw)

    def simpleCrackle(self, n, volume):
        return self.fancyCrackle([0] * n, volume)


    NOTES = "A,B,H,C,C#,D,D#,E,F,F#,G,G#".split(",")
    NOTE_RE = re.compile("[A-H][#]?")
    BASE_FREQ = 220
    def getChordFrequencies(self, chord):
        myAssert(len(self.NOTES) == 12)
        prev = -1
        result = []
        for m in self.NOTE_RE.finditer(chord):
            s = m.group()
            i =self.NOTES.index(s)
            while i < prev:
                i += 12
            result.append(int(self.BASE_FREQ * (2 ** (i / 12.0))))
            prev = i
        return result

    def fancyBeep(self, chord, length, left=10, right=10):
        beepLen = length
        freqs = self.getChordFrequencies(chord)
        intSize = 8 # bytes
        bufSize = max([NVDAHelper.generateBeep(None,freq, beepLen, right, left) for freq in freqs])
        if bufSize % intSize != 0:
            bufSize += intSize
            bufSize -= (bufSize % intSize)
        self.player.stop()
        bbs = []
        result = [0] * (bufSize//intSize)
        for freq in freqs:
            buf = ctypes.create_string_buffer(bufSize)
            NVDAHelper.generateBeep(buf, freq, beepLen, right, left)
            bytes = bytearray(buf)
            unpacked = struct.unpack("<%dQ" % (bufSize // intSize), bytes)
            result = map(operator.add, result, unpacked)
        maxInt = 1 << (8 * intSize)
        result = map(lambda x : x %maxInt, result)
        packed = struct.pack("<%dQ" % (bufSize // intSize), *result)
        self.player.feed(packed)

    def uniformSample(self, a, m):
        n = len(a)
        if n <= m:
            return a
        # Here assume n > m
        result = []
        for i in range(0, m*n, n):
            result.append(a[i  // m])
        return result
    def stop(self):
        self.player.stop()

class EditTextDialog(wx.Dialog):
    def __init__(self, parent, text, onTextComplete):
        self.tabValue = "    "
        # Translators: Title of calibration dialog
        title_string = _("Edit text")
        super(EditTextDialog, self).__init__(parent, title=title_string)
        self.text = text
        self.onTextComplete = onTextComplete
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        sHelper = gui.guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)

        self.textCtrl = wx.TextCtrl(self, style=wx.TE_MULTILINE)
        self.textCtrl.Bind(wx.EVT_CHAR, self.onChar)
        self.Bind(wx.EVT_CHAR_HOOK, self.OnKeyUP)
        sHelper.addItem(self.textCtrl)
        self.textCtrl.SetValue(text)
        self.SetFocus()
        self.Maximize(True)

    def onChar(self, event):
        control = event.ControlDown()
        shift = event.ShiftDown()
        alt = event.AltDown()
        keyCode = event.GetKeyCode()
        if event.GetKeyCode() in [10, 13]:
            # 13 means Enter
            # 10 means Control+Enter
            modifiers = [
                control, shift, alt
            ]
            if not any(modifiers):
                # Just pure enter without any modifiers
                # Perform Autoindent
                curPos = self.textCtrl.GetInsertionPoint
                lineNum = len(self.textCtrl.GetRange( 0, self.textCtrl.GetInsertionPoint() ).split("\n")) - 1
                lineText = self.textCtrl.GetLineText(lineNum)
                m = re.search("^\s*", lineText)
                if m:
                    self.textCtrl.WriteText("\n" + m.group(0))
                else:
                    self.textCtrl.WriteText("\n")
            else:
                modifierNames = [
                    "control",
                    "shift",
                    "alt",
                ]
                modifierTokens = [
                    modifierNames[i]
                    for i in range(len(modifiers))
                    if modifiers[i]
                ]
                keystrokeName = "+".join(modifierTokens + ["Enter"])
                self.keystroke = keyboardHandler.KeyboardInputGesture.fromName(keystrokeName)
                self.text = self.textCtrl.GetValue()
                self.EndModal(wx.ID_OK)
                wx.CallAfter(lambda: self.onTextComplete(wx.ID_OK, self.text, self.keystroke))
        elif event.GetKeyCode() == wx.WXK_TAB:
            if alt or control:
                event.Skip()
            elif not shift:
                # Just Tab
                self.textCtrl.WriteText(self.tabValue)
            else:
                # Shift+Tab
                curPos = self.textCtrl.GetInsertionPoint()
                lineNum = len(self.textCtrl.GetRange( 0, self.textCtrl.GetInsertionPoint() ).split("\n")) - 1
                priorText = self.textCtrl.GetRange( 0, self.textCtrl.GetInsertionPoint() )
                text = self.textCtrl.GetValue()
                postText = text[len(priorText):]
                if priorText.endswith(self.tabValue):
                    newText = priorText[:-len(self.tabValue)] + postText
                    self.textCtrl.SetValue(newText)
                    self.textCtrl.SetInsertionPoint(curPos - len(self.tabValue))
        elif event.GetKeyCode() == 1:
            # Control+A
            self.textCtrl.SetSelection(-1,-1)
        elif event.GetKeyCode() == wx.WXK_HOME:
            if not any([control, shift, alt]):
                curPos = self.textCtrl.GetInsertionPoint()
                lineNum = len(self.textCtrl.GetRange( 0, self.textCtrl.GetInsertionPoint() ).split("\n")) - 1
                colNum = len(self.textCtrl.GetRange( 0, self.textCtrl.GetInsertionPoint() ).split("\n")[-1])
                lineText = self.textCtrl.GetLineText(lineNum)
                m = re.search("^\s*", lineText)
                if not m:
                    raise Exception("This regular expression must match always.")
                indent = len(m.group(0))
                if indent == colNum:
                    newColNum = 0
                else:
                    newColNum = indent
                self.textCtrl.SetInsertionPoint(curPos - colNum + newColNum)
            else:
                event.Skip()
        else:
            event.Skip()


    def OnKeyUP(self, event):
        keyCode = event.GetKeyCode()
        if keyCode == wx.WXK_ESCAPE:
            self.text = self.textCtrl.GetValue()
            self.EndModal(wx.ID_CANCEL)
            wx.CallAfter(lambda: self.onTextComplete(wx.ID_CANCEL, self.text, None))
        event.Skip()

jupyterUpdateInProgress = False

originalExecuteGesture = None
beeper = Beeper()
blockBeeper = Beeper()
blockKeysUntil = 0
def preExecuteGesture(selfself, gesture, *args, **kwargs):
    global blockKeysUntil
    now = time.time()
    if now < blockKeysUntil:
        # Block this keystroke!
        blockBeeper.fancyBeep("DG#", length=100, left=50, right=50)
        return
    return originalExecuteGesture(selfself, gesture, *args, **kwargs)

def blockAllKeys(timeoutSeconds):
    global blockKeysUntil
    now = time.time()
    if blockKeysUntil > now:
        raise Exception("Keys are already blocked")
    blockKeysUntil =now  + timeoutSeconds
    beeper.fancyBeep("CDGA", length=int(1000 * timeoutSeconds), left=5, right=5)

def unblockAllKeys():
    global blockKeysUntil
    blockKeysUntil = 0
    beeper.stop()




class GlobalPlugin(globalPluginHandler.GlobalPlugin):
    scriptCategory = _("BrowserNav")
    beeper = Beeper()

    def __init__(self, *args, **kwargs):
        super(GlobalPlugin, self).__init__(*args, **kwargs)
        self.createMenu()
        self.injectBrowseModeKeystrokes()
        self.lastJupyterText = ""
        global originalExecuteGesture
        originalExecuteGesture = inputCore.InputManager.executeGesture
        inputCore.InputManager.executeGesture = preExecuteGesture


    def createMenu(self):
        def _popupMenu(evt):
            gui.mainFrame._popupSettingsDialog(SettingsDialog)
        self.prefsMenuItem  = gui.mainFrame.sysTrayIcon.preferencesMenu.Append(wx.ID_ANY, _("BrowserNav..."))
        gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, _popupMenu, self.prefsMenuItem)

    def terminate(self):
        prefMenu = gui.mainFrame.sysTrayIcon.preferencesMenu
        prefMenu.Remove(self.prefsMenuItem)

    def script_moveToNextSibling(self, gesture):
        mode = getMode()
        # Translators: error message if next sibling couldn't be found
        errorMessage = _("No next paragraph with the same {mode} in the document").format(
            mode=BROWSE_MODES[mode])
        self.moveInBrowser(1, errorMessage, operator.eq)

    def script_moveToPreviousSibling(self, gesture):
        mode = getMode()
        # Translators: error message if previous sibling couldn't be found
        errorMessage = _("No previous paragraph with the same {mode} in the document").format(
            mode=BROWSE_MODES[mode])
        self.moveInBrowser(-1, errorMessage, operator.eq)


    def script_moveToParent(self, gesture):
        mode = getMode()
        op = PARENT_OPERATORS[mode]
        # Translators: error message if parent could not be found
        errorMessage = _("No previous paragraph  with {qualifier} {mode} in the document").format(
            mode=BROWSE_MODES[mode],
            qualifier=OPERATOR_STRINGS[op])
        self.moveInBrowser(-1, errorMessage, op)

    def script_moveToNextParent(self, gesture):
        mode = getMode()
        op = PARENT_OPERATORS[mode]
        # Translators: error message if parent could not be found
        errorMessage = _("No next paragraph  with {qualifier} {mode} in the document").format(
            mode=BROWSE_MODES[mode],
            qualifier=OPERATOR_STRINGS[op])
        self.moveInBrowser(1, errorMessage, op)


    def script_moveToChild(self, gesture):
        mode = getMode()
        op = CHILD_OPERATORS[mode]
        # Translators: error message if child could not be found
        errorMessage = _("No next paragraph  with {qualifier} {mode} in the document").format(
            mode=BROWSE_MODES[mode],
            qualifier=OPERATOR_STRINGS[op])
        self.moveInBrowser(1, errorMessage, op)

    def script_moveToPreviousChild(self, gesture):
        mode = getMode()
        op = CHILD_OPERATORS[mode]
        # Translators: error message if child could not be found
        errorMessage = _("No previous paragraph  with {qualifier} {mode} in the document").format(
            mode=BROWSE_MODES[mode],
            qualifier=OPERATOR_STRINGS[op])
        self.moveInBrowser(-1, errorMessage, op)

    def script_rotor(self, gesture):
        mode = getMode()
        mode = (mode + 1) % len(BROWSE_MODES)
        setConfig("browserMode", mode)
        ui.message("BrowserNav navigates by " + BROWSE_MODES[mode])

    def generateBrowseModeExtractors(self):
        def getFontSize(textInfo, formatting):
            try:
                size =float( formatting["font-size"].replace("pt", ""))
                return size
            except:
                return 0
        mode = getConfig("browserMode")
        if mode == 0:
            # horizontal offset
            extractFormattingFunc = lambda x: None
            extractIndentFunc = lambda textInfo,x: textInfo.NVDAObjectAtStart.location[0]
            extractStyleFunc = lambda x,y: None
        elif mode in [1,2]:
            extractFormattingFunc = lambda textInfo: self.getFormatting(textInfo)
            extractIndentFunc = getFontSize
            if mode == 1:
                # Font size only
                extractStyleFunc = lambda textInfo, formatting: None
            else:
                # Both font fsize and style
                extractStyleFunc = lambda textInfo, formatting: self.formattingToStyle(formatting)
        return (
            extractFormattingFunc,
            extractIndentFunc,
            extractStyleFunc
        )
    def getFormatting(self, info):
        formatField=textInfos.FormatField()
        formatConfig=config.conf['documentFormatting']
        for field in info.getTextWithFields(formatConfig):
            #if isinstance(field,textInfos.FieldCommand): and isinstance(field.field,textInfos.FormatField):
            try:
                formatField.update(field.field)
            except:
                pass
        return formatField

    def formattingToStyle(self, formatting):
        result = []
        if getConfig("useFontFamily"):
            result.append(formatting.get("font-family", None))
        if getConfig("useColor"):
            result.append(formatting.get("color", None))
        if getConfig("useBackgroundColor"):
            result.append(formatting.get("background-color", None))
        if getConfig("useBoldItalic"):
            result.append(formatting.get("bold", None))
            result.append(formatting.get("italic", None))
        return tuple(result)

    def moveInBrowser(self, increment, errorMessage, op):
        (
            extractFormattingFunc,
            extractIndentFunc,
            extractStyleFunc
        ) = self.generateBrowseModeExtractors()

        focus = api.getFocusObject()
        focus = focus.treeInterceptor
        textInfo = focus.makeTextInfo(textInfos.POSITION_CARET)
        textInfo.expand(textInfos.UNIT_PARAGRAPH)
        origFormatting = extractFormattingFunc(textInfo)
        origIndent = extractIndentFunc(textInfo, origFormatting)
        origStyle = extractStyleFunc(textInfo, origFormatting)
        distance = 0
        while True:
            result =textInfo.move(textInfos.UNIT_PARAGRAPH, increment)
            if result == 0:
                return self.endOfDocument(errorMessage)
            textInfo.expand(textInfos.UNIT_PARAGRAPH)
            text = textInfo.text
            if speech.isBlank(text):
                continue
            formatting = extractFormattingFunc(textInfo)
            indent = extractIndentFunc(textInfo, formatting)
            style = extractStyleFunc(textInfo, formatting)
            if style == origStyle:
                if op(indent, origIndent):
                    textInfo.updateCaret()
                    self.beeper.simpleCrackle(distance, volume=getConfig("crackleVolume"))
                    speech.speakTextInfo(textInfo, reason=controlTypes.REASON_CARET)
                    return
            distance += 1


    def endOfDocument(self, message):
        volume = getConfig("noNextTextChimeVolume")
        self.beeper.fancyBeep("HF", 100, volume, volume)
        if getConfig("noNextTextMessage"):
            ui.message(message)

    def findMark(self, direction, regexp, errorMessage):
        r = re.compile(regexp)
        focus = api.getFocusObject().treeInterceptor
        textInfo = focus.makeTextInfo(textInfos.POSITION_CARET)
        textInfo.expand(textInfos.UNIT_PARAGRAPH)
        distance = 0
        while True:
            distance += 1
            textInfo.collapse()
            result = textInfo.move(textInfos.UNIT_PARAGRAPH, direction)
            if result == 0:
                self.endOfDocument(errorMessage)
                return
            textInfo.expand(textInfos.UNIT_PARAGRAPH)
            m = r.search(textInfo.text)
            if m:
                textInfo.collapse()
                textInfo.move(textInfos.UNIT_CHARACTER, m.start(0))
                end = textInfo.copy()
                end.move(textInfos.UNIT_CHARACTER, len(m.group(0)))
                textInfo.setEndPoint(end, "endToEnd")
                textInfo.updateCaret()
                self.beeper.simpleCrackle(distance, volume=getConfig("crackleVolume"))
                speech.speakTextInfo(textInfo, reason=controlTypes.REASON_CARET)
                textInfo.collapse()
                focus._set_selection(textInfo)
                return

    def findByRole(self, direction, roles, errorMessage):
        focus = api.getFocusObject().treeInterceptor
        textInfo = focus.makeTextInfo(textInfos.POSITION_CARET)
        textInfo.expand(textInfos.UNIT_PARAGRAPH)
        distance = 0
        while True:
            distance += 1
            textInfo.collapse()
            result = textInfo.move(textInfos.UNIT_PARAGRAPH, direction)
            if result == 0:
                self.endOfDocument(errorMessage)
                return
            textInfo.expand(textInfos.UNIT_PARAGRAPH)
            obj = textInfo.NVDAObjectAtStart
            if obj is not None and obj.role in roles:
                textInfo.updateCaret()
                self.beeper.simpleCrackle(distance, volume=getConfig("crackleVolume"))
                speech.speakTextInfo(textInfo, reason=controlTypes.REASON_CARET)
                textInfo.collapse()
                focus._set_selection(textInfo)
                return

    def findByControlField(self, direction, role, errorMessage):
        def getUniqueId(info):
            fields = info.getTextWithFields()
            for field in fields:
                if (
                    isinstance(field, textInfos.FieldCommand)
                    and field.command == "controlStart"
                    and "role" in field.field
                    and field.field['role'] == role
                ):
                    return field.field.get('uniqueID', 0)
            return None
        focus = api.getFocusObject().treeInterceptor
        textInfo = focus.makeTextInfo(textInfos.POSITION_CARET)
        textInfo.expand(textInfos.UNIT_PARAGRAPH)
        originalId = getUniqueId(textInfo)
        distance = 0
        while True:
            distance += 1
            textInfo.collapse()
            result = textInfo.move(textInfos.UNIT_PARAGRAPH, direction)
            if result == 0:
                self.endOfDocument(errorMessage)
                return
            textInfo.expand(textInfos.UNIT_PARAGRAPH)
            newId = getUniqueId(textInfo)
            if newId is not None and (newId != originalId):
                textInfo.updateCaret()
                self.beeper.simpleCrackle(distance, volume=getConfig("crackleVolume"))
                speech.speakTextInfo(textInfo, reason=controlTypes.REASON_CARET)
                textInfo.collapse()
                focus._set_selection(textInfo)
                return

    def script_editJupyter(self, gesture, selfself):
        global jupyterUpdateInProgress
        if jupyterUpdateInProgress:
            ui.message("Jupyter cell update in progress!")
            self.beeper.fancyBeep("AF#", length=100, left=20, right=20)
            return
        fg=winUser.getForegroundWindow()
        if not config.conf["virtualBuffers"]["autoFocusFocusableElements"]:
            selfself._focusLastFocusableObject()
            obj = selfself._lastFocusableObj
            time.sleep(10/1000) # sleep a bit to make sure that this object has properly focused
        else:
            obj=selfself.currentNVDAObject
        if obj.role != controlTypes.ROLE_EDITABLETEXT:
            ui.message(_("Not editable"))
            return
        uniqueID = obj.IA2UniqueID
        self.startInjectingKeystrokes()
        try:
            kbdControlHome.send()
            kbdBackquote.send()
            try:
                kbdControlA.send()
                text = self.getSelection()
                if False:
                    # This alternative method doesn't work for large cells: apparently the selection is just "-" if your cell is too large :(
                    timeout = time.time() + 3
                    while True:
                        if time.time() > timeout:
                            raise EditBoxUpdateError(_("Time out while waiting for selection to appear."))
                        api.processPendingEvents(processEventQueue=False)
                        textInfo = obj.makeTextInfo(textInfos.POSITION_SELECTION)
                        text = textInfo.text
                        if len(text) != 0:
                            break
                        time.sleep(10/1000)
            finally:
                kbdControlHome.send()
                kbdDelete.send()
        finally:
            self.endInjectingKeystrokes()
        if (len(text) == 0) or (text[0] != '`'):
            ui.message("Failed to copy text from semi-accessible edit-box")
            return
        text = text[1:]
        def getFocusObjectVerified():
                focus = api.getFocusObject()
                if focus.role != controlTypes.ROLE_EDITABLETEXT:
                    raise EditBoxUpdateError(_("Browser state has changed. Focused element is not an edit box. Role: %d.") % focus.role)
                if (uniqueID is not None) and (uniqueID != 0):
                    if uniqueID != focus.IA2UniqueID:
                        raise EditBoxUpdateError(_("Browser state has changed. Different element on the page is now focused."))
                return focus
                
        def sleepAndPump():
            time.sleep(10/1000)
            api.processPendingEvents(processEventQueue=True)

        def updateText(result, text, keystroke):
            mylog('c10')
            global jupyterUpdateInProgress
            jupyterUpdateInProgress = True
            self.lastJupyterText = text
            timeoutSeconds = 5
            timeout = time.time() + timeoutSeconds
            #blockAllKeys(timeoutSeconds)
            try:
              # step 1. wait for all modifiers to be released
                mylog('c20')
                while True:
                    if time.time() > timeout:
                        raise EditBoxUpdateError(_("Timed out during release modifiers stage"))
                    status = [
                        winUser.getKeyState(k) & 32768
                        for k in allModifiers
                    ]
                    if not any(status):
                        break
                    sleepAndPump()
              # Step 2: switch back to that browser window
                mylog('c30')
                while  winUser.getForegroundWindow() != fg:
                    if time.time() > timeout:
                        raise EditBoxUpdateError(_("Timed out during switch to browser window stage"))
                    winUser.setForegroundWindow(fg)
                    winUser.setFocus(fg)
                    sleepAndPump()
              # Step 2.1: Ensure that the browser window is fully focused.
                # This is needed sometimes for Firefox - switching to it takes hundreds of milliseconds, especially when jupyter cells are large.
                mylog('c30')
                obj.setFocus()
                #step21timeout = time.time() + 1 # Leave 1 second for this step
                goodCounter = 0
                roles = []
                kbdControlHome.send()
                ii = 0
                while True:
                    ii += 1
                    mylog(f'ii={ii}')
                    if time.time() > timeout:
                        mylog('timeout waiting for role')
                        raise EditBoxUpdateError(_("Timed out during switch to window stage"))
                    focus = api.getFocusObject()
                    roles.append(focus.role)
                    if focus.role in [
                        controlTypes.ROLE_FRAME,
                        controlTypes.ROLE_DOCUMENT,
                        controlTypes.ROLE_PANE,
                    ]:
                        # All good, Firefox is burning cpu, keep sleeping!
                        sleepAndPump()
                        goodCounter = 0
                        continue
                    elif focus.role == controlTypes.ROLE_EDITABLETEXT:
                        goodCounter += 1
                        if goodCounter > 10:
                            tones.beep(1000, 100)
                            break
                        sleepAndPump()
                    else:
                        raise EditBoxUpdateError(_("Error during switch to window stage, focused element role is %d") % focus.role)

              # Step 3: start sending keys
                self.startInjectingKeystrokes()
                mylog('c40')
                try:
                    self.copyToClip(text)
                  # Step 3.1: Send Control+A and wait for the selection to appear
                    kbdControlHome.send()
                    # Sending backquote character to ensure that the edit box is not empty
                    kbdBackquote.send()
                    kbdControlA.send()
                    while True:
                        sleepAndPump()
                        focus = getFocusObjectVerified()
                        if focus.IA2UniqueID != uniqueID:
                            mylog('uniqueId mismatch!')
                        else:
                            mylog('unique id match!')
                        if time.time() > timeout:
                            raise EditBoxUpdateError(_("Timed out during Control+A stage"))
                        textInfo = focus.makeTextInfo(textInfos.POSITION_SELECTION)
                        text = textInfo.text
                        if len(text) > 0:
                            mylog(f'Found text "{text}"')
                            break
                  # Step 3.2 Send Control+V and wait for the selection to disappear
                    mylog('c50')
                    return
                    kbdControlV.send()
                    kbdControlHome.send()
                    return
                    while True:
                        sleepAndPump()
                        focus = getFocusObjectVerified()
                        if time.time() > timeout:
                            raise EditBoxUpdateError(_("Timed out during Control+V stage"))
                        textInfo = focus.makeTextInfo(textInfos.POSITION_SELECTION)
                        text = textInfo.text
                        mylog(f"text='{text}'")
                        if len(text) == 0:
                            break
                finally:
                  # Step 3.3. Sleep for a bit more just to make sure things have propagated.
                  # Apparently if we don't sleep, then either the previous value with ` would be used sometimes,
                  # or it will paste the original contents of clipboard.
                    time.sleep(100)
                    self.endInjectingKeystrokes()
              # Step 4: send the original keystroke, e.g. Control+Enter
                if keystroke is not None:
                    keystroke.send()
            except EditBoxUpdateError as e:
                #unblockAllKeys()
                tones.player.stop()
                jupyterUpdateInProgress = False
                self.copyToClip(text)
                message = ("BrowserNav failed to update edit box.")
                message += "\n" + str(e)
                message += "\n" + _("Last edited text has been copied to the clipboard.")
                #gui.messageBox(message)
            finally:
                #unblockAllKeys()
                jupyterUpdateInProgress = False
                mylog(str(roles))

        self.popupEditTextDialog(
            text,
            #lambda result, text, keystroke: executeAsynchronously(updateText(result, text, keystroke))
            lambda result, text, keystroke: core.callLater(1, updateText, result, text, keystroke)
        )

    def script_copyJupyterText(self, gesture, selfself):
        if len(self.lastJupyterText) > 0:
            self.copyToClip(self.lastJupyterText)
            ui.message(_("Last Jupyter text has been copied to clipboard."))
        else:
            ui.message(_("No last Jupyter text., or last Jupyter text is empty."))

    def startInjectingKeystrokes(self):
        self.restoreKeyboardState()
        self.clipboardBackup = api.getClipData()

    def endInjectingKeystrokes(self):
        self.copyToClip(self.clipboardBackup)

    def restoreKeyboardState(self):
        """
        Most likely this class is called from within a gesture. This means that Some of the modifiers, like
        Shift, Control, Alt are pressed at the moment.
        We need to virtually release them in order to send other keystrokes to VSCode.
        """
        modifiers = [winUser.VK_LCONTROL, winUser.VK_RCONTROL,
            winUser.VK_LSHIFT, winUser.VK_RSHIFT, winUser.VK_LMENU,
            winUser.VK_RMENU, winUser.VK_LWIN, winUser.VK_RWIN, ]
        for k in modifiers:
            if winUser.getKeyState(k) & 32768:
                winUser.keybd_event(k, 0, 2, 0)

    def copyToClip(self, text):
        lastException = None
        for i in range(10):
            try:
                api.copyToClip(text)
                return
            except PermissionError as e:
                lastException = e
                wx.Yield()
                continue
        raise Exception(lastException)

    def getSelection(self):
        self.copyToClip(controlCharacter)
        t0 = time.time()
        timeout = t0+3
        lastControlCTimestamp = 0
        while True:
            if time.time() - lastControlCTimestamp > 1:
                lastControlCTimestamp = time.time()
                kbdControlC.send()
            if time.time() > timeout:
                raise Exception("Time out while trying to copy data out of application.")

            try:
                data = api.getClipData()
                if data != controlCharacter:
                    return data
            except PermissionError:
                pass
            wx.Yield()
            time.sleep(10/1000)

    def popupEditTextDialog(self, text, onTextComplete):
        gui.mainFrame.prePopup()
        d = EditTextDialog(gui.mainFrame, text, onTextComplete)
        result = d.Show()
        gui.mainFrame.postPopup()

    def injectBrowseModeKeystroke(self, keystrokes, funcName, script=None, doc=None):
        gp = self
        cls = browseMode.BrowseModeTreeInterceptor
        scriptFuncName = "script_" + funcName
        if script is None:
            gpFunc = getattr(gp, scriptFuncName)
            script = lambda self, gesture: gpFunc(gesture)
        script.__name__ = scriptFuncName
        script.category = "BrowserNav"
        if doc is not None:
            script.__doc__ = doc
        setattr(cls, scriptFuncName, script)
        if not isinstance(keystrokes, list):
            keystrokes = [keystrokes]
        for keystroke in keystrokes:
            cls._BrowseModeTreeInterceptor__gestures[keystroke] = funcName

    def injectBrowseModeKeystrokes(self):
      # Indentation navigation
        self.injectBrowseModeKeystroke(
            "kb:NVDA+Alt+DownArrow",
            "moveToNextSibling",
            doc="Moves to next sibling in browser")
        self.injectBrowseModeKeystroke(
            "kb:NVDA+Alt+UpArrow",
            "moveToPreviousSibling",
            doc="Moves to previous sibling in browser")
        self.injectBrowseModeKeystroke(
            ["kb:NVDA+Alt+LeftArrow", "kb:NVDA+Alt+Home"],
            "moveToParent",
            doc="Moves to next parent in browser")
        self.injectBrowseModeKeystroke(
            ["kb:NVDA+Control+Alt+LeftArrow", "kb:NVDA+Alt+End"],
            "moveToNextParent",
            doc="Moves to next parent in browser")
        self.injectBrowseModeKeystroke(
            ["kb:NVDA+Alt+RightArrow", "kb:NVDA+Alt+PageDown"],
            "moveToChild",
            doc="Moves to next child in browser")
        self.injectBrowseModeKeystroke(
            ["kb:NVDA+Control+Alt+RightArrow", "kb:NVDA+Alt+PageUp"],
            "moveToPreviousChild",
            doc="Moves to previous child in browser")
      #Rotor
        self.injectBrowseModeKeystroke(
            "kb:NVDA+O",
            "rotor",
            doc="Adjusts BrowserNav rotor")

      # Marks
        self.injectBrowseModeKeystroke(
            "kb:j",
            "nextMark",
            script=lambda selfself, gesture: self.findMark(1, getConfig("marks"), "No next browser mark. To configure browser marks, go to BrowserNav settings."),
            doc="Jump to next browser mark.")
        self.injectBrowseModeKeystroke(
            "kb:Shift+j",
            "previousMark",
            script=lambda selfself, gesture: self.findMark(-1, getConfig("marks"), _("No previous browser mark. To configure browser marks, go to BrowserNav settings.")),
            doc="Jump to previous browser mark.")
        if False:
            self.injectBrowseModeKeystroke(
                "",
                "nextParagraph",
                script=lambda selfself, gesture: self.script_moveByParagraph_forward(gesture),
                doc="Jump to next paragraph")
            self.injectBrowseModeKeystroke(
                "",
                "previousParagraph",
                script=lambda selfself, gesture: self.script_moveByParagraph_back(gesture),
                doc="Jump to previous paragraph")
        # Example page with tabs:
        # https://wet-boew.github.io/v4.0-ci/demos/tabs/tabs-en.html
        self.injectBrowseModeKeystroke(
            "kb:Y",
            "nextTab",
            script=lambda selfself, gesture: self.findByRole(
                direction=1,
                roles=[controlTypes.ROLE_TAB],
                errorMessage=_("No next tab")),
            doc="Jump to next tab")
        self.injectBrowseModeKeystroke(
            "kb:Shift+Y",
            "previousTab",
            script=lambda selfself, gesture: self.findByRole(
                direction=-1,
                roles=[controlTypes.ROLE_TAB],
                errorMessage=_("No previous tab")),
            doc="Jump to previous tab")

        #Dialog
        dialogTypes = [controlTypes.ROLE_APPLICATION, controlTypes.ROLE_DIALOG]
        self.injectBrowseModeKeystroke(
            "kb:P",
            "nextDialog",
            script=lambda selfself, gesture: self.findByRole(
                direction=1,
                roles=dialogTypes,
                errorMessage=_("No next dialog")),
            doc="Jump to next dialog")
        self.injectBrowseModeKeystroke(
            "kb:Shift+P",
            "previousDialog",
            script=lambda selfself, gesture: self.findByRole(
                direction=-1,
                roles=dialogTypes,
                errorMessage=_("No previous dialog")),
            doc="Jump to previous dialog")

        menuTypes = [
            controlTypes.ROLE_MENU,
            controlTypes.ROLE_MENUBAR,
            controlTypes.ROLE_MENUITEM,
            controlTypes.ROLE_POPUPMENU,
            controlTypes.ROLE_CHECKMENUITEM,
            controlTypes.ROLE_RADIOMENUITEM,
            controlTypes.ROLE_TEAROFFMENU,
            controlTypes.ROLE_MENUBUTTON,
        ]
        self.injectBrowseModeKeystroke(
            "kb:Z",
            "nextMenu",
            script=lambda selfself, gesture: self.findByRole(
                direction=1,
                roles=menuTypes,
                errorMessage=_("No next menu")),
            doc="Jump to next menu")
        self.injectBrowseModeKeystroke(
            "kb:Shift+Z",
            "previousMenu",
            script=lambda selfself, gesture: self.findByRole(
                direction=-1,
                roles=menuTypes,
                errorMessage=_("No previous menu")),
            doc="Jump to previous menu")
        self.injectBrowseModeKeystroke(
            "kb:0",
            "nextTreeView",
            script=lambda selfself, gesture: self.findByRole(
                direction=1,
                roles=[controlTypes.ROLE_TREEVIEW],
                errorMessage=_("No next tree view")),
            doc="Jump to next tree view")
        self.injectBrowseModeKeystroke(
            "kb:Shift+0",
            "previousTreeView",
            script=lambda selfself, gesture: self.findByRole(
                direction=-1,
                roles=[controlTypes.ROLE_TREEVIEW],
                errorMessage=_("No previous tree view")),
            doc="Jump to previous tree view")
        self.injectBrowseModeKeystroke(
            "kb:9",
            "nextToolBar",
            script=lambda selfself, gesture: self.findByControlField(
                direction=1,
                role=controlTypes.ROLE_TOOLBAR,
                errorMessage=_("No next tool bar")),
            doc="Jump to next tool bar")
        self.injectBrowseModeKeystroke(
            "kb:Shift+9",
            "previousToolBar",
            script=lambda selfself, gesture: self.findByControlField(
                direction=-1,
                role=controlTypes.ROLE_TOOLBAR,
                errorMessage=_("No previous tool bar")),
            doc="Jump to previous tool bar")
        # Edit Jupyter
        self.injectBrowseModeKeystroke(
            "kb:NVDA+E",
            "editJupyter",
            script=lambda selfself, gesture: self.script_editJupyter(gesture, selfself),
            doc="Edit semi-accessible edit box.")
        self.injectBrowseModeKeystroke(
            "kb:NVDA+Control+E",
            "copyJupyterText",
            script=lambda selfself, gesture: self.script_copyJupyterText(gesture, selfself),
            doc="Copy the last text from semi-accessible edit box to clipboard.")
