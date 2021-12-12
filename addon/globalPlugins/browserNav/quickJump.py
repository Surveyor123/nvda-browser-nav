#A part of the BrowserNav addon for NVDA
#Copyright (C) 2017-2021 Tony Malykh
#This file is covered by the GNU General Public License.
#See the file LICENSE  for more details.

import api
from collections import namedtuple, defaultdict
import controlTypes
from controlTypes import OutputReason
import copy
import dataclasses
from dataclasses import dataclass
#from dataclasses_json import dataclass_json
from enum import Enum
import functools
import globalVars
import gui
from gui import guiHelper, nvdaControls
from gui.settingsDialogs import SettingsPanel
import json
import os
import re
import textInfos
import tones
from typing import List, Tuple
import ui
import weakref
import wx

from . beeper import *

try:
    REASON_CARET = controlTypes.REASON_CARET
except AttributeError:
    REASON_CARET = controlTypes.OutputReason.CARET



debug = True
if debug:
    f = open("C:\\Users\\tony\\drp\\2.txt", "w")
    def mylog(s):
        if debug:
            print(str(s), file=f)
            f.flush()
else:
    def mylog(s):
        pass


def weakMemoize(func):
    cache = weakref.WeakKeyDictionary()

    def memoized_func(*args):
        arg = args[0]
        if len(args) > 1:
            raise Exception("Only supports single argument!")
        value = cache.get(arg)
        if value is not None:
            return value
        result = func(*args)
        cache.update({arg: result})
        return result

    return memoized_func

class BookmarkCategory(Enum):
    QUICK_JUMP = 1
    QUICK_JUMP_2 = 2
    QUICK_JUMP_3 = 3
    SKIP_CLUTTER = 4
    AUTO_PRESS = 5

BookmarkCategoryNames = {
    BookmarkCategory.QUICK_JUMP: _('QuickJump - assigned to J by default'),
    BookmarkCategory.QUICK_JUMP_2: _('QuickJump2'),
    BookmarkCategory.QUICK_JUMP_3: _('QuickJump3'),
    BookmarkCategory.SKIP_CLUTTER: _('SkipClutter - will automatically skip this paragraph or line when navigating via Control+Up/Down or Up/Down keystrokes; must match the whole paragraph. or '),
    BookmarkCategory.AUTO_PRESS: _('AutoPress'),
}

class URLMatch(Enum):
    IGNORE = 0
    DOMAIN = 1
    SUBDOMAIN = 2
    SUBSTRING = 3
    EXACT = 4
    REGEX = 5

urlMatchNames = {
    URLMatch.IGNORE: _('Match all sites (domain field ignored) '),
    URLMatch.DOMAIN: _('Match domain name'),
    URLMatch.SUBDOMAIN: _('Match domain and its subdomains'),
    URLMatch.SUBSTRING: _('Match substring in URL'),
    URLMatch.EXACT: _('Exact URL match'),
    URLMatch.REGEX: _('Regex match of URL'),
}

class FocusMode(Enum):
    UNCHANGED = 0
    DONT_ENTER_FORM_MODE = 1
    DISABLE_FOCUS = 2

focusModeNames = {
    FocusMode.UNCHANGED: _('Keep default NVDA focus behavior'),
    FocusMode.DONT_ENTER_FORM_MODE: _('React to focus event, but prevent entering focus mode'),
    FocusMode.DISABLE_FOCUS: _('Ignore all focus events - good for websites that misuse focus events'),
}



class PatternMatch(Enum):
    EXACT = 1
    SUBSTRING = 2
    REGEX = 3

patterMatchNames = {
    PatternMatch.EXACT: _('Exact paragraph match'),
    PatternMatch.SUBSTRING: _('Substring paragraph match'),
    PatternMatch.REGEX: _('Regex paragraph match'),
}

class ParagraphAttribute(Enum):
    ROLE = 'role'
    FONT_SIZE = 'font-size'

class  QJImmutable:
    def __setattr__(self, *args):
        raise TypeError
    def __delattr__(self, *args):
        raise TypeError

class QJAttribute(QJImmutable):
    attribute: ParagraphAttribute
    value: any

    def __init__(
        self,
        d=None,
        role=None,
        userString=None
    ):
        if d is not None:
            object.__setattr__(self, 'attribute', ParagraphAttribute(d['attribute']))
            value = d['value']
            if self.attribute == ParagraphAttribute.ROLE:
                value = controlTypes.Role(self.value)
            object.__setattr__(self, 'value', value)
        elif userString is not None:
            s = userString.strip()
            if s.startswith("!"):
                s.invert = True
                s = s[1:]
            else:
                self.invert = False
            tokens = s.split(":")
            if len(tokens) != 2:
                raise ValueError(f"Invalid format of attribute! After splitting by : found {len(tokens)} tokens, but expected 2. userString='{s}'")
            try:
                object.__setattr__(self, 'attribute', ParagraphAttribute(tokens[0]))
            except ValueError as e:
                raise ValueError(f"Invalid attribute {tokens[0]}. User string='{userString}'.", e)
            if self.attribute == ParagraphAttribute.ROLE:
                roleName = tokens[2].lower()
                roles = [
                    role
                    for role.name in controlTypes.roleLabels.items()
                    if name.lower() == roleName
                ]
                if len(roles) == 0:
                    raise ValueError(f"Invalid role '{roleName}'.")
                value = roles[0]
            else:
                value = tokens[1]
            object.__setattr__(self, 'value', value)
        elif role is not None:
            object.__setattr__(self, 'attribute', ParagraphAttribute.ROLE)
            object.__setattr__(self, 'value', role)
        else:
            raise Exception("Impossible!")


    def asDict(self):
        return {
            'attribute': self.attribute.value,
            'value': self.value.value if self.attribute == ParagraphAttribute.ROLE else selv.value,

        }


    def asString(self):
        if self.attribute == ParagraphAttribute.ROLE:
            value = controlTypes.roleLabels[self.value]
        else:
            value = self.value
        return f"{self.attribute.value}:{value}"


class QJAttributeMatch(QJImmutable):
    invert: bool
    attribute: QJAttribute

    def __init__(
        self,
        d=None,
        userString=None
    ):
        if d is not None:
            object.__setattr__(self, 'invert', d['invert'])
            object.__setattr__(self, 'attribute', QJAttribute(d['attribute']))
        elif userString is not None:
            s = userString.strip()
            if len(s) == 0:
                raise ValueError("Empty string!")
            object.__setattr__(self, 'invert', s.startswith("!"))
            if s.startswith("!"):
                s = s[1:]
            object.__setattr__(self, 'attribute', QJAttribute(userString=s))
        else:
            raise Exception("Impossible!")


    def asDict(self):
        return {
            'invert': self.invert,
            'attribute': self.attribute.asDict(),
        }


    def asString(self):
        invertString = "!" if self.invert else ""
        return f"{invertString}{self.attribute.asString()}"

    def __hash__(self):
        return id(self)
        
    def matches(self, attributes):
        if not self.invert:
            return self.attribute in attributes
        else:
            return self.attribute not in attributes


class QJBookmark(QJImmutable):
    enabled: bool
    category: BookmarkCategory
    name: str
    pattern: str
    patternMatch: PatternMatch
    attributes: Tuple[QJAttributeMatch]

    def __init__(self, d):
        object.__setattr__(self, 'enabled', d['enabled'])
        object.__setattr__(self, 'category', BookmarkCategory(d['category']))
        object.__setattr__(self, 'name', d['name'])
        object.__setattr__(self, 'pattern', d['pattern'])
        object.__setattr__(self, 'patternMatch', PatternMatch(d['patternMatch']))
        object.__setattr__(self, 'attributes', tuple([
            QJAttributeMatch(attrDict)
            for attrDict in d['attributes']
        ]))

    def asDict(self):
        return {
            'enabled': self.enabled,
            'category': self.category.value,
            'name': self.name,
            'pattern': self.pattern,
            'patternMatch': self.patternMatch.value,
            'attributes': [
                attr.toDict()
                for attr in self.attributes
            ]
        }

    def getDisplayName(self):
        if self.name is not None and len(self.name) > 0:
            return self.name
        return self.pattern

    def __hash__(self):
        return id(self)



class QJSite(QJImmutable):
    domain: str
    urlMatch: URLMatch
    name: str
    focusMode: FocusMode
    bookmarks: Tuple[QJBookmark]

    def __init__(self, d):
        object.__setattr__(self, 'domain', d['domain'])
        object.__setattr__(self, 'urlMatch', URLMatch(d['urlMatch']))
        object.__setattr__(self, 'name', d['name'])
        object.__setattr__(self, 'focusMode', FocusMode(d['focusMode']))
        object.__setattr__(self, 'bookmarks', tuple([
            QJBookmark(bookmarkDict)
            for bookmarkDict in d['bookmarks']
        ]))

    def asDict(self):
        return {
            'domain': self.domain,
            'urlMatch': self.urlMatch.value,
            'name': self.name,
            'focusMode': self.focusMode.value,
            'bookmarks': [bookmark.asDict() for bookmark in self.bookmarks]
        }


    def postLoad(self):
        self.urlMatch = URLMatch(self.urlMatch)
        return self

    def getDisplayName(self):
        if self.name is not None and len(self.name) > 0:
            return self.name
        return self.domain

    def __hash__(self):
        return id(self)

    def updateBookmarks(self, bookmarks):
        d = self.asDict()
        d['bookmarks'] = [
            bookmark.asDict()
            for bookmark in bookmarks
        ]
        return QJSite(d)

class QJConfig(QJImmutable):
    sites: Tuple[QJSite]

    def __init__(self, d):
        object.__setattr__(self, 'sites', tuple([
                QJSite(item)
                for item in d['sites']
        ]))

    def asDict(self):
        return {
            'sites': [
                site.asDict()
                for site in self.sites
            ],
        }

    def __hash__(self):
        return id(self)

    def updateSites(self, sites):
        d = self.asDict()
        d['sites'] = [
            site.asDict()
            for site in sites
        ]
        return QJConfig(d)

rulesFileName = os.path.join(globalVars.appArgs.configPath, "browserNavRules.json")
defaultRulesFileName = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "browserNavRules.json"
)

def loadConfig():
    try:
        rulesConfig = open(rulesFileName, "r").read()
        mylog(rulesFileName)
    except FileNotFoundError:
        rulesConfig = open(defaultRulesFileName, "r").read()
        mylog(defaultRulesFileName)
    return QJConfig(json.loads(rulesConfig))


def saveConfig():
    global globalConfig
    configDict = globalConfig.asDict()
    rulesJson = json.dumps(configDict, indent=4, sort_keys=True)
    rulesFile = open(rulesFileName, "w")
    try:
        rulesFile.write(rulesJson)
    finally:
        rulesFile.close()

globalConfig  = loadConfig()

if False:
    from dataclasses import dataclass, asdict
    from enum import Enum


    @dataclass
    class Foobar:
      name: str
      template: "FoobarEnum"


    class FoobarEnum(Enum):
      FIRST = "foobar"
      SECOND = "baz"


    def custom_asdict_factory(data):

        def convert_value(obj):
            if isinstance(obj, Enum):
                return obj.value
            return obj

        return dict((k, convert_value(v)) for k, v in data)


    foobar = Foobar(name="John", template=FoobarEnum.FIRST)

    print(asdict(foobar, dict_factory=custom_asdict_factory))
    # {'name': 'John', 'template': 'foobar'}

@functools.lru_cache()
def re_compile(s):
    return re.compile(s)

def getDomain(url):
    m = re_compile(
        # http://
            r'(\w+://)?'
        # username:password@
            + r'([\w.,:"-]+@)?'
        # google.com
            + r'(?P<domain>[\w.-]+)'
        # :80
            +r'(:\d+)?'
        # /rest/of/the/url#...
            +r'.*'
    ).match(url)
    if not m:
        raise ValueError(f"Domain not found in URL {url}")
    domain = m.group('domain').lower()
    return domain


@functools.lru_cache()
def isUrlMatch(url, site):
    if site.urlMatch == URLMatch.IGNORE:
        return True
    elif site.urlMatch in {URLMatch.DOMAIN, URLMatch.SUBDOMAIN}:
        try:
            domain = getDomain(url)
        except ValueError:
            return False
        siteDomain = site.domain.lower()
        if site.urlMatch == URLMatch.DOMAIN:
            return domain == site_domain
        elif site.urlMatch == URLMatch.SUBDOMAIN:
            return (
                domain == siteDomain
                or domain.endswith("." + siteDomain)
            )
        else:
            raise Exception("Impossible!")
    elif site.urlMatch == URLMatch.SUBSTRING:
        return site.domain.lower() in url.lower()
    elif site.urlMatch == URLMatch.EXACT:
        return site.domain.lower() ==  url.lower()
    elif site.urlMatch == URLMatch.REGEX:
        return re_compile(site.domain).search(url) is not None
    else:
        raise Exception("Impossible!")

@functools.lru_cache()
def findSites(url, config):
    return [
        site
        for site in config.sites
        if isUrlMatch(url, site)
    ]

@functools.lru_cache()
def getFocusMode(url, config):
    sites = findSites(url, config)
    if len(sites) == 0:
        return FocusMode.UNCHANGED
    mode = max([
        site.focusMode.value
        for site in sites
    ])
    return FocusMode(mode)
    
@weakMemoize
def getUrlFromObject(object):
    while object is not None:
        try:
            interceptor = object.treeInterceptor
        except AttributeError:
            pass
        if interceptor is not None:
            url = interceptor.documentConstantIdentifier
            if url is not None and len(url) > 0:
                return url
        object = object.simpleParent

@weakMemoize
def getUrl(self):
    url = self.documentConstantIdentifier
    if url is None or len(url) == 0:
        url = getUrlFromObject(self.currentNVDAObject)
        if url is None or len(url) == 0:
            return ""
    return url

originalShouldPassThrough = None
def newShouldPassThrough(self, obj, reason= None):
    focusMode = getFocusMode(getUrl(self), globalConfig)
    if reason == OutputReason.FOCUS and focusMode == FocusMode.DONT_ENTER_FORM_MODE:
        return self.passThrough
    else:
        return originalShouldPassThrough(self, obj, reason)

original_event_gainFocus = None
def new_event_gainFocus(self, obj, nextHandler):
    focusMode = getFocusMode(getUrl(self), globalConfig)
    if focusMode == FocusMode.DISABLE_FOCUS:
        return nextHandler()
    return original_event_gainFocus(self, obj, nextHandler)

@functools.lru_cache()
def getRegexForBookmark(rule):
    if rule.patternMatch == PatternMatch.EXACT:
        return f"^{re.escape(rule.pattern)}$"
    elif rule.patternMatch == PatternMatch.SUBSTRING:
        return re.escape(rule.pattern)
    elif rule.patternMatch == PatternMatch.REGEX:
        return rule.pattern
    else:
        raise Exception("Impossible!")

NAMED_REGEX_PREFIX = "QJ_"
BookmarkMatch = namedtuple('BookmarkMatch', ['bookmark', 'text', 'start', 'end'])
@functools.lru_cache()
def makeCompositeRegex(bookmarks):
    # Using named groups in regular expression to identify which bookmark has matched
    re_string = "|".join([
        f"(?P<{NAMED_REGEX_PREFIX}{i}>{getRegexForBookmark(bookmark)})"
        for i,bookmark in enumerate(bookmarks)
    ])
    mylog(f"re_string={re_string}")
    return re_compile(re_string)

def matchWidthCompositeRegex(bookmarks, text):
    mylog(f"matchWidthCompositeRegex")
    m = makeCompositeRegex(bookmarks).search(text)
    if m is None:
        mylog(f"no matches!")
        return None
    matchIndices = [
        int(key[len(NAMED_REGEX_PREFIX):])
        for key, value in m.groupdict().items()
        if key.startswith(NAMED_REGEX_PREFIX)
            and value is not None
    ]
    mylog(f"matchIndices={matchIndices}")
    if len(matchIndices) == 0:
        return
    i = matchIndices[0]

    groupName = f"{NAMED_REGEX_PREFIX}{i}"
    mylog(f"i={i}")
    mylog(f"groupName={groupName}")
    api.q=m
    return BookmarkMatch(
        bookmark=bookmarks[i],
        text=m.group(groupName),
        start=m.start(groupName),
        end=m.end(groupName),
    )
def matchAllWidthCompositeRegex(bookmarks, text):
    result = []
    while True:
        m = matchWidthCompositeRegex(bookmarks, text)
        if not m:
            return result
        result.append(m)
        bookmarks = [
            b
            for b in bookmarks
            if b != m.bookmark
        ]

@functools.lru_cache()
def findApplicableBookmarks(config, url, category=None):
    sites = findSites(url, config)
    bookmarks = [
        bookmark
        for site in sites
        for bookmark in site.bookmarks
        if (
            bookmark.category == category
            or category is None
        )
        and bookmark.enabled
    ]
    return tuple(bookmarks)

def extractAttributes(textInfo):
    #result = defaultdict(set)
    result = set()
    fields = textInfo.getTextWithFields()
    for field in fields:
        if not isinstance(field, textInfos.FieldCommand):
            continue
        elif field.command == 'controlStart':
            role = field.field['role']
            #result[ParagraphAttribute.ROLE].add(role)
            result.add(QJAttribute(role=role))
        elif field.command == 'formatChange':
            try:
                #result[ParagraphAttribute.FONT_SIZE].add(field.field['font-size'])
                result.add(QJAttribute(attribute=ParagraphAttribute.FONT_SIZE, value=field.field['font-size']))
            except KeyError:
                pass
        else:
            pass
    return result


def quickJump(self, gesture, category, direction, errorMsg):
    bookmarks = findApplicableBookmarks(globalConfig, getUrl(self), category)
    if len(bookmarks) == 0:
        return endOfDocument(_('No quickJump bookmarks configured for current website. Please add QuickJump bookmarks in BrowserNav settings in NVDA settings window.'))
    textInfo = self.makeTextInfo(textInfos.POSITION_CARET)
    textInfo.collapse()
    textInfo.expand(textInfos.UNIT_PARAGRAPH)
    distance = 0
    while True:
        distance += 1
        textInfo.collapse()
        result = textInfo.move(textInfos.UNIT_PARAGRAPH, direction)
        if result == 0:
            endOfDocument(errorMsg)
            return
        textInfo.expand(textInfos.UNIT_PARAGRAPH)
        text = textInfo.text
        m = matchWidthCompositeRegex(bookmarks, text)
        if m:
            textInfo.collapse()
            textInfo.move(textInfos.UNIT_CHARACTER, m.start)
            textInfo.move(textInfos.UNIT_CHARACTER, len(m.text), endPoint='end')
            textInfo.updateCaret()
            beeper.simpleCrackle(distance, volume=getConfig("crackleVolume"))
            speech.speakTextInfo(textInfo, reason=REASON_CARET)
            textInfo.collapse()
            self._set_selection(textInfo)
            self.selection = textInfo
            return


def editOrCreateSite(self, site=None, url=None, domain=None):
    global globalConfig
    config = globalConfig
    try:
        index = config.sites.index(site)
        knownSites = config.sites[:index] + globalConfig.sites[index+1:]
    except ValueError:
        index = None
        knownSites = config.sites
    entryDialog=EditSiteDialog(None, knownSites=knownSites, site=site, url=url, domain=domain)
    if entryDialog.ShowModal()==wx.ID_OK:
        sites = list(config.sites)
        mylog(f"len(sites) = {len(sites)} index={index}")
        if index is not None:
            sites[index] = entryDialog.site
        else:
            sites.append(entryDialog.site)
        mylog(f"Afterwards len(sites) = {len(sites)} new name = {entryDialog.site.getDisplayName()}")
        config = config.updateSites(sites)
        globalConfig = config
        saveConfig()
        mylog(f"Config saved!")
def makeWebsiteSubmenu(self, frame):
    url = getUrl(self)
    sites = findSites(url, globalConfig)
    menu = wx.Menu()

    for site in sites:
        menuStr = _("Edit existing website %s") % site.getDisplayName()
        item = menu.Append(wx.ID_ANY, menuStr)
        frame.Bind(
            wx.EVT_MENU,
            lambda evt: editOrCreateSite(self, site=site),
            item,
        )

    try:
        domain = getDomain(url)
        menuStr = _("Create new website for domain %s") % domain
        item = menu.Append(wx.ID_ANY, menuStr)
        frame.Bind(
            wx.EVT_MENU,
            lambda evt: editOrCreateSite(self, domain=domain),
            item,
        )
    except ValueError:
        pass
    menuStr = _("Create new website with custom URL matching options")
    item = menu.Append(wx.ID_ANY, menuStr)
    frame.Bind(
        wx.EVT_MENU,
        lambda evt: editOrCreateSite(self, url=url),
        item,
    )
    return menu


def makeBookmarkSubmenu(self, frame):
    textInfo = self.selection.copy()
    textInfo.collapse()
    textInfo.expand(textInfos.UNIT_PARAGRAPH)
    text = textInfo.text
    url = getUrl(self)
    sites = findSites(url, globalConfig)
    bookmarks = findApplicableBookmarks(globalConfig, url, category=None)
    matches = matchAllWidthCompositeRegex(bookmarks, text)
    attributes = extractAttributes(textInfo)
    menu = wx.Menu()
    for m in matches:
        bookmark = m.bookmark
        site_ = [
            site 
            for site in sites
            if bookmark in sites
        ]
        if len(site_) != 1:
            raise Exception("Impossible!")
        site = site_[0]
        attributesMatch = all([
            am.matches(attributes)
            for am in bookmark.attributes
        ])


class EditBookmarkDialog(wx.Dialog):
    def __init__(self, parent, bookmark=None, config=None, site=None, allowSiteSelection=False, textInfo=None):
        title=_("Edit browserNav bookmark")
        super(EditBookmarkDialog,self).__init__(parent,title=title)
        self.config=config
        self.oldSite = site
        mainSizer=wx.BoxSizer(wx.VERTICAL)
        sHelper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
        if bookmark is  not None:
            self.bookmark = bookmark
        else:
            self.bookmark = QJBookmark({
                'enabled': True,
                'category': BookmarkCategory.QUICK_JUMP,
                'name': "",
                'pattern': "",
                'patternMatch': PatternMatch.SUBSTRING,
                'attributes': [],
            })

      # Translators: pattern
        patternLabelText = _("&Pattern")
        self.patternTextCtrl=sHelper.addLabeledControl(patternLabelText, wx.TextCtrl)
        self.patternTextCtrl.SetValue(self.bookmark.pattern)

      # Translators: Pattern match type comboBox
        matchModeLabelText=_("Pattern &match type:")
        self.matchModeCategory=guiHelper.LabeledControlHelper(
            self,
            matchModeLabelText,
            wx.Choice,
            choices=[
                patterMatchNames[m]
                for m in PatternMatch
            ],
        )
        self.matchModeCategory.control.SetSelection(list(PatternMatch).index(self.bookmark.patternMatch))
      # Translators:  Category radio buttons
        categoryText = _("&Category:")
        self.categoryComboBox = guiHelper.LabeledControlHelper(
            self,
            categoryText,
            wx.Choice,
            choices=[BookmarkCategoryNames[i] for i in BookmarkCategory],
        )
        self.categoryComboBox.control.SetSelection(list(BookmarkCategory).index(self.bookmark.category))
      # Translators: site  comboBox
        labelText=_("&Site this bookmark belongs to:")
        self.siteComboBox=guiHelper.LabeledControlHelper(
            self,
            labelText,
            wx.Choice,
            choices=[
                site.getDisplayName()
                for site in self.config.sites
            ],
        )
        self.siteComboBox.control.SetSelection(
            self.config.sites.index(self.oldSite)
        )
        if not allowSiteSelection:
            self.siteComboBox.control.Disable()
      # Translators: label for enabled checkbox
        enabledText = _("Bookmark enabled")
        self.enabledCheckBox=sHelper.addItem(wx.CheckBox(self,label=enabledText))
        self.enabledCheckBox.SetValue(self.bookmark.enabled)

      # Translators: label for comment edit box
        commentLabelText = _("&Display name (optional)")
        self.commentTextCtrl=sHelper.addLabeledControl(commentLabelText, wx.TextCtrl)
        self.commentTextCtrl.SetValue(self.bookmark.name)
      # attributes
        labelText = _("&Attributes (space separated list):")
        self.attributesTextCtrl=sHelper.addLabeledControl(labelText, wx.TextCtrl)
        self.attributesTextCtrl.SetValue(" ".join([
            attr.asString()
            for attr in self.bookmark.attributes
        ]))
      # available attributes in current paragraph
        labelText=_("Available attributes in current paragraph (Enter to add to current bookmark):")
        self.attrChoices = [
            attr.asString()
            for attr in extractAttributes(textInfo)
        ] if textInfo is not None else []
        self.availableAttributesListBox=guiHelper.LabeledControlHelper(
            self,
            labelText,
            wx.ListBox,
            choices=self.attrChoices,
        )
        #self.availableAttributesListBox.control.Bind(wx.EVT_LISTBOX, self.onAvailableAttributeListChoice)
        self.availableAttributesListBox.control.Bind(wx.EVT_CHAR, self.onChar)
        if textInfo is None:
            self.availableAttributesListBox.control.Disable()
      #  OK/cancel buttons
        sHelper.addDialogDismissButtons(self.CreateButtonSizer(wx.OK|wx.CANCEL))

        mainSizer.Add(sHelper.sizer,border=20,flag=wx.ALL)
        mainSizer.Fit(self)
        self.SetSizer(mainSizer)
        self.patternTextCtrl.SetFocus()
        self.Bind(wx.EVT_BUTTON,self.onOk,id=wx.ID_OK)

    def make(self):
        patternMatch = list(PatternMatch)[self.matchModeCategory.control.GetSelection()]
        pattern = self.patternTextCtrl.Value
        errorMsg = None
        if len(pattern) == 0:
            errorMsg = _('Pattern cannot be empty!')
        elif patternMatch == PatternMatch.REGEX:
            try:
                re.compile(pattern)
            except re.error as e:
                errorMsg = _('Failed to compile regular expression: %s') % str(e)

        if errorMsg is not None:
            # Translators: This is an error message to let the user know that the pattern field is not valid.
            gui.messageBox(errorMsg, _("Bookmark entry error"), wx.OK|wx.ICON_WARNING, self)
            self.patternTextCtrl.SetFocus()
            return
        try:
            attributes = [
                QJAttributeMatch(userString=attr)
                for attr in self.attributesTextCtrl.GetValue().strip().split()
            ]
        except ValueError as e:
            errorMsg = _(f'Cannot parse attribute: {e}')
            gui.messageBox(errorMsg, _("Bookmark Entry Error"), wx.OK|wx.ICON_WARNING, self)
            self.attributesTextCtrl.SetFocus()
            return

        bookmark = QJBookmark({
            'enabled': self.enabledCheckBox.Value,
            'category': list(BookmarkCategory)[self.categoryComboBox.control.GetSelection()],
            'name':self.commentTextCtrl.Value,
            'pattern': pattern,
            'patternMatch': patternMatch.value,
            'attributes': attributes,
        })
        return bookmark
        
    def makeNewSite(self):
        newSite = self.config.sites[self.siteComboBox.control.GetSelection()]
        if newSite != self.oldSite:
            result = gui.messageBox(
                _("Warning: you are about to move this bookmark to site %s. This bookmark will disappear from the old site %s. Would you like to proceed?") % (newSite.getDisplayName(), self.oldSite.getDisplayName()), 
                _("Bookmark Entry warning"), 
                wx.YES|wx.NO|wx.ICON_WARNING,
                self
            )
            if result == wx.YES:
                return newSite
            else:
                self.siteComboBox.control.SetFocus()
                return None
        return newSite

    def onChar(self, event):
        keyCode = event.GetKeyCode ()
        if keyCode == 32: #space
            tones.beep(500, 50)
            index = self.availableAttributesListBox.control.Selection
            if index >= 0:
                item = self.attrChoices[index]
                s = self.attributesTextCtrl.GetValue()
                if len(s) > 0 and not s.endswith(' '):
                    s += ' '
                s += item
                self.attributesTextCtrl.SetValue(s)
                ui.message(_("Added '{item} to matched attributes edit box.'"))
        else:
            event.Skip()

    def onOk(self,evt):
        bookmark = self.make()
        if bookmark is not None:
            newSite = self.makeNewSite()
            if newSite is  not None:
                self.bookmark = bookmark
                self.newSite = newSite
                evt.Skip()

class BookmarksListDialog(
    gui.dpiScalingHelper.DpiScalingHelperMixinWithoutInit,
    wx.Dialog,
):
    def __init__(self, parent, site, config):
        title=_("Edit bookmarks for %s") % site.getDisplayName()
        super(BookmarksListDialog,self).__init__(parent,title=title)
        self.site = site
        self.bookmarks = list(site.bookmarks)
        self.config = config
        mainSizer=wx.BoxSizer(wx.VERTICAL)
        sHelper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
      # Bookmarks table
        rulesText = _("&Bookmarks")
        self.rulesList = sHelper.addLabeledControl(
            rulesText,
            nvdaControls.AutoWidthColumnListCtrl,
            autoSizeColumn=2,
            itemTextCallable=self.getItemTextForList,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VIRTUAL
        )

        self.rulesList.InsertColumn(0, _("Name"), width=self.scaleSize(150))
        self.rulesList.InsertColumn(1, _("Pattern"))
        self.rulesList.InsertColumn(2, _("Match type"))
        self.rulesList.InsertColumn(3, _("Category"))
        self.rulesList.InsertColumn(4, _("Enabled"))
        self.rulesList.Bind(wx.EVT_LIST_ITEM_FOCUSED, self.onListItemFocused)
        self.rulesList.ItemCount = len(self.bookmarks)

        bHelper = sHelper.addItem(guiHelper.ButtonHelper(orientation=wx.HORIZONTAL))
      # Buttons
        self.addButton = bHelper.addButton(self, label=_("&Add"))
        self.addButton.Bind(wx.EVT_BUTTON, self.OnAddClick)
        self.editButton = bHelper.addButton(self, label=_("&Edit"))
        self.editButton.Bind(wx.EVT_BUTTON, self.OnEditClick)
        self.removeButton = bHelper.addButton(self, label=_("&Remove bookmark"))
        self.removeButton.Bind(wx.EVT_BUTTON, self.OnRemoveClick)
        self.moveUpButton = bHelper.addButton(self, label=_("Move &up"))
        self.moveUpButton.Bind(wx.EVT_BUTTON, lambda evt: self.OnMoveClick(evt, -1))
        self.moveDownButton = bHelper.addButton(self, label=_("Move &down"))
        self.moveDownButton.Bind(wx.EVT_BUTTON, lambda evt: self.OnMoveClick(evt, 1))
        self.sortButton = bHelper.addButton(self, label=_("&Sort"))
        self.sortButton.Bind(wx.EVT_BUTTON, self.OnSortClick)
      # OK/Cancel buttons
        sHelper.addDialogDismissButtons(self.CreateButtonSizer(wx.OK|wx.CANCEL))
        self.rulesList.SetFocus()

    def getItemTextForList(self, item, column):
        bookmark = self.bookmarks[item]
        if column == 0:
            return bookmark.getDisplayName()
        elif column == 1:
            return bookmark.pattern
        elif column == 2:
            return patterMatchNames[bookmark.patternMatch]
        elif column == 3:
            return BookmarkCategoryNames[bookmark.category]
        elif column == 4:
            return _('Enabled') if bookmark.enabled else _('Disabled')
        else:
            raise ValueError("Unknown column: %d" % column)

    def onListItemFocused(self, evt):
        if self.rulesList.GetSelectedItemCount()!=1:
            return
        index=self.rulesList.GetFirstSelected()
        bookmark = self.bookmarks[index]

    def OnAddClick(self,evt):
        entryDialog=EditBookmarkDialog(
            self,
            config=self.config,
            site=self.site,
        )
        if entryDialog.ShowModal()==wx.ID_OK:
            self.bookmarks.append(entryDialog.bookmark)
            self.rulesList.ItemCount = len(self.bookmarks)
            index = self.rulesList.ItemCount - 1
            self.rulesList.Select(index)
            self.rulesList.Focus(index)
            # We don't get a new focus event with the new index.
            self.rulesList.sendListItemFocusedEvent(index)
            self.rulesList.SetFocus()
            entryDialog.Destroy()

    def OnEditClick(self,evt):
        if self.rulesList.GetSelectedItemCount()!=1:
            return
        editIndex=self.rulesList.GetFirstSelected()
        if editIndex<0:
            return
        entryDialog=EditBookmarkDialog(
            self,
            bookmark=self.bookmarks[editIndex],
            config=self.config,
            site=self.site,
            allowSiteSelection=True,
        )
        if entryDialog.ShowModal()==wx.ID_OK:
            if self.site != entryDialog.newSite:
                # moving to newSite!
                del self.bookmarks[editIndex]
                #self.rulesList.DeleteItem(editIndex)
                self.rulesList.ItemCount = len(self.bookmarks)
                newSite = entryDialog.newSite
                bookmarks = list(newSite.bookmarks)
                bookmarks.append(entryDialog.bookmark)
                newSite2 = newSite.updateBookmarks(bookmarks)
                sites = list(self.config.sites)
                index = sites.index(newSite)
                sites[index] = newSite2
                self.config = self.config.updateSites(sites)
            else:
                self.bookmarks[editIndex] = entryDialog.bookmark
            self.rulesList.SetFocus()
        entryDialog.Destroy()

    def OnRemoveClick(self,evt):
        index=self.rulesList.GetFirstSelected()
        while index>=0:
            self.rulesList.DeleteItem(index)
            del self.bookmarks[index]
            index=self.rulesList.GetNextSelected(index)
        self.rulesList.SetFocus()

    def OnMoveClick(self,evt, increment):
        if self.rulesList.GetSelectedItemCount()!=1:
            return
        index=self.rulesList.GetFirstSelected()
        if index<0:
            return
        newIndex = index + increment
        if 0 <= newIndex < len(self.bookmarks):
            # Swap
            tmp = self.bookmarks[index]
            self.bookmarks[index] = self.bookmarks[newIndex]
            self.bookmarks[newIndex] = tmp
            self.rulesList.Select(newIndex)
            self.rulesList.Focus(newIndex)
        else:
            return

    def OnSortClick(self,evt):
        self.bookmarks.sort(key=QJSite.getDisplayName)

    def onOk(self,evt):
        evt.Skip()

class EditSiteDialog(wx.Dialog):
    def __init__(self, parent, site=None, config=None, knownSites=None, url=None, domain=None):
        title=_("Edit site configuration")
        super(EditSiteDialog,self).__init__(parent,title=title)
        mainSizer=wx.BoxSizer(wx.VERTICAL)
        sHelper = guiHelper.BoxSizerHelper(self, orientation=wx.VERTICAL)
        if site is  not None:
            self.site = site
        else:
            self.site = QJSite({
                'domain':domain or url or "",
                'name':'',
                'urlMatch':URLMatch.EXACT.value if url is not None else URLMatch.SUBDOMAIN.value,
                'focusMode':FocusMode.UNCHANGED.value,
                'bookmarks': [],
            })
        self.config = config
        self.knownSites = knownSites
      # Translators: label for comment edit box
        commentLabelText = _("&Display name (optional)")
        self.commentTextCtrl=sHelper.addLabeledControl(commentLabelText, wx.TextCtrl)
        self.commentTextCtrl.SetValue(self.site.name)
      # Translators: domain
        patternLabelText = _("&URL")
        self.patternTextCtrl=sHelper.addLabeledControl(patternLabelText, wx.TextCtrl)
        self.patternTextCtrl.SetValue(self.site.domain)
      # Translators:  label for type selector radio buttons
        typeText = _("&Match type")
        self.typeComboBox = guiHelper.LabeledControlHelper(
            self,
            typeText,
            wx.Choice,
            choices=[urlMatchNames[i] for i in URLMatch],
        )
        self.typeComboBox.control.SetSelection(list(URLMatch).index(self.site.urlMatch))

      # Edit bookmarks button
        self.editRulesButton = sHelper.addItem (wx.Button (self, label = _("Edit &bookmarks")))
        self.editRulesButton.Bind(wx.EVT_BUTTON, self.OnEditRulesClick)

      # Translators: Focus Mode comboBox
        focusModeLabelText=_("&Focus mode")
        self.focusModeCategory=guiHelper.LabeledControlHelper(
            self,
            focusModeLabelText,
            wx.Choice,
            choices=[
                focusModeNames[m]
                for m in FocusMode
            ],
        )
        self.focusModeCategory.control.SetSelection(list(FocusMode).index(self.site.focusMode))
      #  OK/cancel buttons
        sHelper.addDialogDismissButtons(self.CreateButtonSizer(wx.OK|wx.CANCEL))

        mainSizer.Add(sHelper.sizer,border=20,flag=wx.ALL)
        mainSizer.Fit(self)
        self.SetSizer(mainSizer)
        self.patternTextCtrl.SetFocus()
        self.Bind(wx.EVT_BUTTON,self.onOk,id=wx.ID_OK)

    def make(self):
        urlMatch = list(URLMatch)[self.typeComboBox.control.GetSelection()]
        domain = self.patternTextCtrl.Value
        errorMsg = None
        if urlMatch == URLMatch.IGNORE:
            if len(domain) > 0:
                errorMsg = _("You must specify blank domain in order to match all sites.")
        else:
            if len(domain) == 0:
                errorMsg = _("You must specify non-empty string as domain")
            elif urlMatch in [URLMatch.DOMAIN, URLMatch.SUBDOMAIN]:
                m = re.match(r'[\w.-]+(:\d+)?', domain)
                if not m:
                    errorMsg = _("Wrong domain format. An example is: en.wikipedia.com ")
            elif urlMatch == URLMatch.REGEX:
                try:
                    re.compile(domain)
                except re.error as e:
                    errorMsg = _("Failed to compile regular expression: %s") % str(e)

        if errorMsg is None and self.knownSites is not None:
            for other in self.knownSites:
                if (
                    domain == other.domain
                    and urlMatch == other.urlMatch
                ):
                    errorMsg = (
                        _("This site is a duplicate of another existing site %s")
                        % other.getDisplayName()
                    )
        if errorMsg is not None:
            # Translators: This is an error message to let the user know that the pattern field is not valid.
            gui.messageBox(errorMsg, _("Dictionary Entry Error"), wx.OK|wx.ICON_WARNING, self)
            self.patternTextCtrl.SetFocus()
            return
        if urlMatch in {URLMatch.DOMAIN, URLMatch.SUBDOMAIN}:
            domain = domain.lower()
        site = QJSite({
            'domain':domain,
            'urlMatch':urlMatch,
            'name':self.commentTextCtrl.Value,
            'focusMode': list(FocusMode)[self.focusModeCategory.control.GetSelection()],
            'bookmarks': [
                b.asDict()
                for b in self.site.bookmarks
            ]
        })
        return site

    def OnEditRulesClick(self,evt):
        mylog(f"EditSiteDialog.editBookmarks nb={len(self.site.bookmarks)}")
        entryDialog=BookmarksListDialog(
            self,
            site=self.site,
            config=self.config,
        )
        if entryDialog.ShowModal()==wx.ID_OK:
            self.site = self.site.updateBookmarks(entryDialog.bookmarks)
            self.config = entryDialog.config
            mylog(f"EditSiteDialog.editBookmarks2 nb={len(self.site.bookmarks)}")
        entryDialog.Destroy()

    def onOk(self,evt):
        site = self.make()
        if site is not None:
            self.site = site
            evt.Skip()


class SettingsDialog(SettingsPanel):
    title = _("BrowserNav QuickSearch websites and bookmarks")

    def __init__(self, *args, **kwargs):
        super(SettingsDialog, self).__init__(*args, **kwargs)

    def makeSettings(self, settingsSizer):
        global globalConfig
        self.config = copy.deepcopy(globalConfig)

        sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
      # Sites table
        sitesText = _("&Sites")
        self.sitesList = sHelper.addLabeledControl(
            sitesText,
            nvdaControls.AutoWidthColumnListCtrl,
            autoSizeColumn=2,
            itemTextCallable=self.getItemTextForList,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_VIRTUAL
        )

        self.sitesList.InsertColumn(0, _("Name"), width=self.scaleSize(150))
        self.sitesList.InsertColumn(1, _("Domain"))
        self.sitesList.InsertColumn(2, _("Type"))
        self.sitesList.Bind(wx.EVT_LIST_ITEM_FOCUSED, self.onListItemFocused)
        self.sitesList.ItemCount = len(self.config.sites)

        bHelper = sHelper.addItem(guiHelper.ButtonHelper(orientation=wx.HORIZONTAL))
      # Buttons
        self.addButton = bHelper.addButton(self, label=_("&Add"))
        self.addButton.Bind(wx.EVT_BUTTON, self.OnAddClick)
        self.editButton = bHelper.addButton(self, label=_("&Edit site"))
        self.editButton.Bind(wx.EVT_BUTTON, self.OnEditClick)
        self.editRulesButton = bHelper.addButton(self, label=_("Edit &bookmarks"))
        self.editRulesButton.Bind(wx.EVT_BUTTON, self.OnEditRulesClick)
        self.removeButton = bHelper.addButton(self, label=_("&Remove site"))
        self.removeButton.Bind(wx.EVT_BUTTON, self.OnRemoveClick)
        self.moveUpButton = bHelper.addButton(self, label=_("Move &up"))
        self.moveUpButton.Bind(wx.EVT_BUTTON, lambda evt: self.OnMoveClick(evt, -1))
        self.moveDownButton = bHelper.addButton(self, label=_("Move &down"))
        self.moveDownButton.Bind(wx.EVT_BUTTON, lambda evt: self.OnMoveClick(evt, 1))
        self.sortButton = bHelper.addButton(self, label=_("&Sort"))
        self.sortButton.Bind(wx.EVT_BUTTON, self.OnSortClick)

    def postInit(self):
        self.sitesList.SetFocus()

    def getItemTextForList(self, item, column):
        site = self.config.sites[item]
        if column == 0:
            return site.getDisplayName()
        elif column == 2:
            return urlMatchNames[site.urlMatch]
        elif column == 1:
            return site.domain
        else:
            raise ValueError("Unknown column: %d" % column)

    def onListItemFocused(self, evt):
        if self.sitesList.GetSelectedItemCount()!=1:
            return
        index=self.sitesList.GetFirstSelected()
        site = self.config.sites[index]

    def OnAddClick(self,evt):
        entryDialog=EditSiteDialog(self, knownSites=self.config.sites, config=self.config)
        if entryDialog.ShowModal()==wx.ID_OK:
            sites = list(self.config.sites) + [entryDialog.site]
            self.config = entryDialog.config
            self.config = self.config.updateSites(sites)
            self.sitesList.ItemCount = len(self.config.sites)
            index = self.sitesList.ItemCount - 1
            self.sitesList.Select(index)
            self.sitesList.Focus(index)
            # We don't get a new focus event with the new index.
            self.sitesList.sendListItemFocusedEvent(index)
            self.sitesList.SetFocus()
            entryDialog.Destroy()

    def OnEditClick(self,evt):
        if self.sitesList.GetSelectedItemCount()!=1:
            return
        editIndex=self.sitesList.GetFirstSelected()
        if editIndex<0:
            return
        entryDialog=EditSiteDialog(
            self,
            site=self.config.sites[editIndex],
            knownSites=self.config.sites[:editIndex] + self.config.sites[editIndex+1:],
            config=self.config,
        )
        if entryDialog.ShowModal()==wx.ID_OK:
            self.config = entryDialog.config
            sites = list(self.config.sites)
            sites[editIndex] = entryDialog.site
            self.config = self.config.updateSites(sites)
            self.sitesList.SetFocus()
        entryDialog.Destroy()

    def OnEditRulesClick(self,evt):
        if self.sitesList.GetSelectedItemCount()!=1:
            return
        editIndex=self.sitesList.GetFirstSelected()
        if editIndex<0:
            return
        entryDialog=BookmarksListDialog(
            self,
            site=self.config.sites[editIndex],
            config=self.config,
        )
        if entryDialog.ShowModal()==wx.ID_OK:
            self.config = entryDialog.config
            sites = list(self.config.sites)
            sites[editIndex] = sites[editIndex].updateBookmarks(entryDialog.bookmarks)
            self.config = self.config.updateSites(sites)
            self.sitesList.SetFocus()
        entryDialog.Destroy()

    def OnRemoveClick(self,evt):
        sites = list(self.config.sites)
        index=self.sitesList.GetFirstSelected()
        while index>=0:
            self.sitesList.DeleteItem(index)
            del sites[index]
            index=self.sitesList.GetNextSelected(index)
        self.config = self.config.updateSites(sites)
        self.sitesList.SetFocus()

    def OnMoveClick(self,evt, increment):
        if self.sitesList.GetSelectedItemCount()!=1:
            return
        index=self.sitesList.GetFirstSelected()
        if index<0:
            return
        newIndex = index + increment
        if 0 <= newIndex < len(self.config.sites):
            sites = list(self.config.sites)
            # Swap
            tmp = sites[index]
            sites[index] = sites[newIndex]
            sites[newIndex] = tmp
            self.config = self.config.updateSites(sites)
            self.sitesList.Select(newIndex)
            self.sitesList.Focus(newIndex)
        else:
            return

    def OnSortClick(self,evt):
        sites = list(self.config.sites)
        sites.sort(key=QJSite.getDisplayName)
        self.config = self.config.updateSites(sites)

    def onSave(self):
        global globalConfig
        globalConfig = self.config
        saveConfig()
