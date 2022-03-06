from functools import partial
import re

import anki
from aqt import mw, editor, gui_hooks
from aqt.qt import QDialog, QGridLayout, QPushButton, QLabel

from . import definitionGetter

# stores the entries that need to be added when dialogs end
finalEntries = []
config = mw.addonManager.getConfig(__name__)

# adds the selected dictionary entry and closes dialog
def buttonPressed(entry,window):
    global finalEntries
    finalEntries.append(entry)
    window.close()

def get_bold_words(html):
    return re.findall(r'<b>(.+?)</b>', html)

def get_cloze_words(html):
    return re.findall(r'{{c[1-9]+\:\:(.+?)(?:\:\:|}})', html)

def get_cloze_hints(html):
    return re.findall(r'{{c[1-9]+\:\:[^}}]+?\:\:(.+?)}}', html)

def remove_cloze(html):
    """
    Remove any cloze and leave the content of the
    non-hint part.
    """
    return [re.sub(r'{{c[1-9]+\:\:(.+?)(?:}}|\:\:.+?}})',
                   lambda x: x.group(1), html)]


def getNoteType(name):
    global config
    notetypes = []
    for notetype in config['notetypes']:
        if(name == notetype['name']): 
            notetypes.append(notetype)
    return notetypes

def getActiveWindow(note):
    for widget in mw.app.allWidgets():
        # finds the editor in use
        if isinstance(widget, editor.EditorWebView) and widget.editor.note is note:
            return widget
    return None

def getDefinitionChoiceDialog(aw, entries):
    d = QDialog(aw)
    grid = QGridLayout()

    # adds found definitions to dialog window
    for x in range(len(entries)):
        button = QPushButton(entries[x].word)
        button.clicked.connect(partial(buttonPressed, entries[x],d))
        label = QLabel()
        label.setText(entries[x].shortDef)
        label.setWordWrap(True)
        grid.addWidget(button,x,0)
        grid.addWidget(label,x,1,1,5)
    d.setLayout(grid)
    return d

def _get_words(config_entry: dict, input_str: str) -> list[str]:
    """
    Parse the 'type' entry in the config and extract the corresponding words
    from the note.
    """
    if config_entry["type"] == "Bold font":
        return get_bold_words(input_str)

    if config_entry["type"] == "Cloze":
        return get_cloze_words(input_str)

    if config_entry["type"] == "Cloze hint":
        return get_cloze_hints(input_str)

    if config_entry["type"] == "Ignore cloze":
        return remove_cloze(input_str)

    if config_entry["type"] == "Single":
        return [input_str]

    raise ValueError(f"Unkown config type entry in {config_entry}")

def theMagic(changed: bool, note: anki.notes.Note, current_field_idx: int):
    global finalEntries, config
    fields = mw.col.models.field_names(note.note_type())
    notetypes = getNoteType(note.note_type()['name'])
    if not notetypes:
        # not a notetype that has the add-on enabled, don't do anything
        return changed

    for notetype in notetypes:
        if fields[current_field_idx] != notetype["src"]:
            # not the src field that has been edited, don't do anything
            continue
        src = fields[current_field_idx]
        dst = notetype["dst"]

        if not dst:
            raise ValueError("The dst and src fields in config don't match those on the card")
        
        if note[dst]:
            # dst isn't empty, to avoid overwriting data, don't do anything
            continue

        aw = getActiveWindow(note)
        if not aw:
            continue

        if not note[src]:
            # the relevant field is empty
            continue
        

        # runs the dialogs
        entries = _get_words(notetype, note[src])

        for entry in entries:
            definitions = definitionGetter.parseSearch(entry)
            if(len(definitions) == 1):
                finalEntries.append(definitions[0])
            else:
                getDefinitionChoiceDialog(aw, definitions).exec_()

        # puts the output into the note and saves
        output = ""
        for entry in finalEntries:
            output += "<div><b>"+entry.word+":</b> " + entry.getFullDef() + "</div>"
        note[dst] = output
        try:
            note._to_backend_note()
        except AttributeError:
            note.flush()
        aw.editor.loadNote(focusTo=current_field_idx+1)
        finalEntries = []

        # prevents focus from advancing and messing the edits up
        return False
    return changed

# tells anki to call theMagic when focus is lost (you move out of a text field or something)
gui_hooks.editor_did_unfocus_field.append(theMagic)
