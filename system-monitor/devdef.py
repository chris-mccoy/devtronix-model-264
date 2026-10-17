#!/usr/bin/env python3
"""Devtronix Model 264 organ definition ("D" file) reader.

The format was read out of System Monitor 2.6 (183): the loader at $57C6
(`Load Dn`), the saver at $5726, the list table at $182C and the definition
editor's field descriptors at $F3C4 (see README.md, "Definition files").

usage:
  devdef.py SIDE0 [SIDE1] [-d D1]                 summary of the definition
  devdef.py SIDE0 [SIDE1] -d D1 --list Stp        one list as the editor's /STP shows it
  devdef.py SIDE0 [SIDE1] -d D1 --list all        every list
  devdef.py SIDE0 [SIDE1] -d D1 --item Stp 12     every field of one item (/STP12)
  devdef.py --file def.bin ...                    same, from bytes extracted with devfs.py

Lists: Kbd Rnk Unt Stp Lnk Fnc Ctl Ind Pst Piz Rit Chn Cin Cot Spf.

A definition is a set of lists.  Items are numbered from 1 and referred to by
number (a stop number in a Track file is its index in the Stp list).  The
file is:

    word   version, $1A12..$1A15 (the monitor accepts these, writes $1A15)
    repeat
        word  list id (hash of the list name, see LISTS)
        word  item count
        per item:  byte len, len bytes of record body (trailing zeros trimmed)
                   byte len, len bytes of name (no terminator)
    word   $FFFF

16-bit fields are little-endian; versions before $1A15 use a word for the two
lengths and carry 8 extra bytes at the head of each body.  In RAM each item is
a list node {next.l, name.l, body...} of the size given in LISTS; the body is
padded with zeros to that size.
"""
import argparse, os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from devfs import Disk  # noqa: E402

# list id -> (name, body size).  Body size = node size at $182C minus the 8-byte
# node header.  $28A7 "Div" is an old division list that the loader converts
# into keyboard references ($6480 is an even older id for it).
LISTS = {
    0x4514: ("Kbd", 246), 0x72BB: ("Rnk", 244), 0x8584: ("Unt", 20), 0x79F0: ("Stp", 22),
    0x4D3B: ("Lnk", 50), 0x27B3: ("Fnc", 18), 0x15EC: ("Ctl", 6), 0x3A74: ("Ind", 4),
    0x670C: ("Pst", 4), 0x6582: ("Piz", 244), 0x71FC: ("Rit", 244), 0x140E: ("Chn", 4),
    0x1436: ("Cin", 10), 0x152C: ("Cot", 6), 0x7946: ("Spf", 60), 0x28A7: ("Div", 2),
    0x6480: ("Div", 2),
}
LIST_ORDER = ["Kbd", "Rnk", "Unt", "Stp", "Lnk", "Fnc", "Ctl", "Ind", "Pst", "Piz", "Rit",
              "Chn", "Cin", "Cot", "Spf", "Div"]

# Editor field descriptors (monitor $F3C4 hash table -> 12-byte entries).
# (label, kind, body offset, reference).  Kinds: 01 name string, 02 reference
# (item number in another list, or a value from TYPE_NAMES), 03 yes/no,
# 04 Active/Inactive byte, 05 number, 07 note (1..121, 0 = unset), 0A link
# algorithm, 0B milliseconds, 0E input address, 0F output address,
# 10/11 keyboard/rank note table, 12 signed pitch offset, 13 type selector
# (word at +0, selects the descriptor block), 14 console polarity.
FIELDS = {
    'Kbd': {None: [('Keyboard name', 0x01, 0, None), ('Key input addresses', 0x10, 0, None)]},
    'Rnk': {None: [('Rank name', 0x01, 0, None), ('Pipe output addresses', 0x11, 2, None)]},
    'Piz': {None: [('Pizzicato name', 0x01, 0, None), ('Timing table', 0x09, 0, None)]},
    'Rit': {None: [('Reiterate name', 0x01, 0, None), ('Random timing?', 0x03, 0, None),
                   ('Timing table', 0x08, 0, None)]},
    'Stp': {
        0: [('Stop name', 0x01, 0, None), ('Stop hardware type', 0x13, 0, 'StpTypes')],
        1: [('Stop name', 0x01, 0, None), ('Stop hardware type', 0x13, 0, 'StpTypes'),
            ('Button contact address', 0x0E, 8, None), ('Indicator address', 0x0F, 6, None),
            ('Debounce time', 0x0B, 16, None), ('Combination status', 0x04, 18, None),
            ('Record/play status', 0x04, 20, None)],
        2: [('Stop name', 0x01, 0, None), ('Stop hardware type', 0x13, 0, 'StpTypes'),
            ('Stop contact address', 0x0E, 8, None), ('ON magnet address', 0x0F, 12, None),
            ('OFF magnet address', 0x0F, 14, None), ('Indicator address', 0x0F, 6, None),
            ('Debounce time', 0x0B, 16, None), ('Combination status', 0x04, 18, None),
            ('Record/play status', 0x04, 20, None)],
        3: [('Stop name', 0x01, 0, None), ('Stop hardware type', 0x13, 0, 'StpTypes'),
            ('Button contact address', 0x0E, 8, None), ('Indicator address', 0x0F, 6, None),
            ('Debounce time', 0x0B, 16, None), ('Combination status', 0x04, 18, None),
            ('Record/play status', 0x04, 20, None)],
        4: [('Stop name', 0x01, 0, None), ('Stop hardware type', 0x13, 0, 'StpTypes'),
            ('ON contact address', 0x0E, 8, None), ('OFF contact address', 0x0E, 10, None),
            ('Indicator address', 0x0F, 6, None), ('Debounce time', 0x0B, 16, None),
            ('Combination status', 0x04, 18, None), ('Record/play status', 0x04, 20, None)],
    },
    'Fnc': {
        0: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes')],
        1: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
            ('Couple from division', 0x02, 4, 'Kbd'), ('Couple to division', 0x02, 2, 'Kbd'),
            ('Pitch offset', 0x12, 6, None), ('Bottom note limit', 0x07, 8, None),
            ('Top note limit', 0x07, 10, None), ('Couple the couplers', 0x03, 12, None),
            ('Special function', 0x02, 14, 'MelTypes')],
        2: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
            ('Couple from rank', 0x02, 4, 'Rnk'), ('Couple to rank', 0x02, 2, 'Rnk'),
            ('Pitch offset', 0x12, 6, None), ('Bottom note limit', 0x07, 8, None),
            ('Top note limit', 0x07, 10, None)],
        3: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
            ('Division name', 0x02, 2, 'Kbd'), ('Rank name', 0x02, 4, 'Rnk'),
            ('Pitch offset', 0x12, 6, None), ('Bottom note limit', 0x07, 8, None),
            ('Top note limit', 0x07, 10, None)],
        4: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
            ('Division name', 0x02, 2, 'Kbd'), ('Trap name', 0x02, 4, 'Unt')],
        5: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
            ('Unit name', 0x02, 2, 'Unt')],
        6: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
            ('Division name', 0x02, 2, 'Kbd')],
        7: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
            ('Keyboard name', 0x02, 2, 'Kbd')],
        8: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
            ('Keyboard name', 0x02, 2, 'Kbd')],
        9: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
            ('Transposer type', 0x02, 2, 'TrnTypes'), ('Change value', 0x05, 4, None)],
        10: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
             ('Couple from division', 0x02, 4, 'Kbd'), ('Couple to division', 0x02, 2, 'Kbd'),
             ('Pitch offset', 0x12, 6, None)],
        11: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
             ('Division name', 0x02, 2, 'Kbd'), ('Rank name', 0x02, 4, 'Rnk'),
             ('Pitch offset', 0x12, 6, None)],
        12: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes')] +
            [('Function list' if i == 0 else '', 0x02, 2 + 2 * i, 'Fnc') for i in range(8)],
        13: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
             ('Modified function', 0x02, 2, 'Fnc'), ('Pizzicato timing', 0x02, 4, 'Piz')],
        14: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
             ('Modified function', 0x02, 2, 'Fnc'), ('Reiterate timing', 0x02, 4, 'Rit'),
             ('Pitch offsets', 0x12, 6, None), ('', 0x12, 8, None), ('', 0x12, 10, None),
             ('', 0x12, 12, None)],
        15: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
             ('Couple from channel', 0x02, 4, 'Chn'), ('Couple to channel', 0x02, 2, 'Chn')],
        16: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
             ('Channel to output to', 0x02, 4, 'Chn'), ('Channel output value', 0x05, 2, None)],
        17: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes')] +
            [('Controlled stops' if i == 0 else '', 0x02, 2 + 2 * i, 'Stp') for i in range(4)],
        18: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
             ('Keyboard name', 0x02, 2, 'Kbd')],
        19: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
             ('Midi channel number', 0x05, 2, None), ('Midi program number', 0x05, 4, None)],
        20: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
             ('Midi channel number', 0x05, 2, None), ('Controller number', 0x05, 4, None)],
        21: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
             ('Midi channel number', 0x05, 2, None), ('Controller number', 0x05, 4, None),
             ('Velocity value', 0x05, 6, None)],
        22: [('Function name', 0x01, 0, None), ('Function type', 0x13, 0, 'FncTypes'),
             ('Midi channel number', 0x05, 2, None), ('Minimum velocity', 0x05, 4, None),
             ('Maximum velocity', 0x05, 6, None)],
    },
    'Unt': {
        0: [('Unit name', 0x01, 0, None), ('Signal type', 0x13, 0, 'UntTypes')],
        1: [('Unit name', 0x01, 0, None), ('Signal type', 0x13, 0, 'UntTypes'),
            ('Location', 0x02, 2, 'LocTypes'), ('Output address', 0x0F, 4, None)],
        2: [('Unit name', 0x01, 0, None), ('Signal type', 0x13, 0, 'UntTypes'),
            ('Location', 0x02, 2, 'LocTypes'), ('Output address', 0x0F, 4, None),
            ('Minimum "on" time', 0x0B, 6, None), ('Maximum "on" time', 0x0B, 8, None),
            ('Trigger on key-up', 0x03, 10, None)],
        3: [('Unit name', 0x01, 0, None), ('Signal type', 0x13, 0, 'UntTypes'),
            ('Location', 0x02, 2, 'LocTypes'), ('Output address', 0x0F, 4, None),
            ('Output address', 0x0F, 10, None), ('Reiterate cycle time', 0x0B, 6, None),
            ('Duty-cycle (1-9)', 0x05, 8, None)],
        4: [('Unit name', 0x01, 0, None), ('Signal type', 0x13, 0, 'UntTypes'),
            ('Location', 0x02, 2, 'LocTypes')] +
           [('Weighted output %d' % (i + 1), 0x0F, 4 + 2 * i, None) for i in range(8)],
        5: [('Unit name', 0x01, 0, None), ('Signal type', 0x13, 0, 'UntTypes'),
            ('Midi channel number', 0x05, 2, None), ('Midi note number', 0x05, 4, None),
            ('Velocity value', 0x05, 6, None)],
    },
    'Lnk': {None: [('Link name', 0x01, 0, None), ('Algorithm', 0x0A, 0, None)] +
                  [('Functions' if i == 0 else '', 0x02, 30 + 2 * i, 'Fnc') for i in range(8)]},
    'Ctl': {None: [('Control button name', 0x01, 0, None), ('Control button type', 0x02, 0, 'CtlTypes'),
                   ('Input address', 0x0E, 2, None), ('Debounce time', 0x0B, 4, None)]},
    'Ind': {None: [('Indicator type', 0x02, 0, 'IndTypes'), ('Output address', 0x0F, 2, None)]},
    'Pst': {None: [('Piston name', 0x01, 0, None), ('Piston input address', 0x0E, 0, None),
                   ('Debounce time', 0x0B, 2, None)]},
    'Chn': {None: [('Channel name', 0x01, 0, None), ('Channel type', 0x02, 0, 'ChnTypes'),
                   ('Record channel', 0x04, 2, None)]},
    'Cin': {None: [('Input item name', 0x01, 0, None), ('Output channel name', 0x02, 2, 'Chn'),
                   ('Input contact address', 0x0E, 0, None), ('Debounce time', 0x0B, 6, None),
                   ('Output value (0-255)', 0x05, 4, None), ('Analog sensitivity', 0x05, 8, None)]},
    'Cot': {None: [('Output item name', 0x01, 0, None), ('Channel name', 0x02, 0, 'Chn'),
                   ('Output function', 0x02, 2, 'Fnc'), ('Channel value', 0x05, 4, None)]},
    'Spf': {None: [('Set piston', 0x0E, 0, None), ('Range piston', 0x0E, 2, None),
                   ('Tempo button', 0x0E, 4, None), ('Tempo control', 0x0E, 6, None),
                   ('Metronome on/off', 0x0E, 26, None), ('Metronome unit', 0x02, 10, 'Unt'),
                   ('Downbeat unit', 0x02, 8, 'Unt'), ('Play/record switch', 0x0E, 12, None),
                   ('Magnet pulse time', 0x0B, 14, None), ('Panel up/down speed', 0x0B, 16, None),
                   ('Console polarity', 0x14, 18, None), ('"  sensitivity', 0x05, 20, None),
                   ('"  scan timing', 0x05, 24, None)]},
    'Div': {None: [('Division name', 0x01, 0, None), ('Keyboard', 0x02, 0, 'Kbd')]},
}

# Value names for type selectors and kind-02 references into these tables
# (monitor strings at $105A2..$10B00).
TYPE_NAMES = {
    'StpTypes': {1: 'Button or switch', 2: 'Dual magnetic stop', 3: 'Reversible button',
                 4: 'Dual-contact drawknob'},
    'FncTypes': {1: 'Divisional coupler', 2: 'Rank coupler (obsolete)', 3: 'Normal rank output',
                 4: 'Normal trap output', 5: 'Direct unit output', 6: 'Division unison off',
                 7: 'Keyboard sustain', 8: 'Keyboard legato', 9: 'Transposer',
                 10: 'Melody coupler (obsolete)', 11: 'Resultant (obsolete)',
                 12: 'Function multiplier', 13: 'Pizzicato modifier', 14: 'Reiterate modifier',
                 15: 'Channel coupler', 16: 'Channel output', 17: 'Stop reverser',
                 18: 'Keyboard sostenuto', 19: 'Midi program change',
                 20: 'Midi analog controller output', 21: 'Midi fixed controller output',
                 22: 'Midi set channel note velocity'},
    'UntTypes': {1: 'Normal output', 2: 'Controlled output', 3: 'Reiterate output',
                 4: 'Analog output', 5: 'Midi single note output'},
    'MelTypes': {1: 'Top note melody (auto-on)', 2: 'Top note melody (auto-off)',
                 3: 'Bottom note melody (auto-on)', 4: 'Bottom note melody (auto-off)'},
    'TrnTypes': {1: 'Absolute', 2: 'Relative', 3: 'Key sensing'},
    'LocTypes': {1: 'Pipe chambers', 2: 'Console'},
    'ChnTypes': {1: 'Expression', 2: 'Crescendo', 3: 'Tempo control'},
    'CtlTypes': {1: 'Keypad digit #1', 2: 'Keypad digit #2', 3: 'Keypad digit #3',
                 4: 'Keypad digit #4', 5: 'Keypad digit #5', 6: 'Keypad digit #6',
                 7: 'Keypad digit #7', 8: 'Keypad digit #8', 9: 'Keypad digit #9',
                 10: 'Keypad digit #0', 11: 'General clear', 12: 'Current file display',
                 13: 'Overwrite files', 14: 'Record setup', 15: 'Play setup',
                 16: 'Record/play start', 17: 'Record/play stop', 18: 'Record/play start/stop',
                 19: 'Record/play finish', 20: 'Combination load', 21: 'Combination save',
                 22: 'File number down', 23: 'File number up'},
    'IndTypes': {1: 'First hex digit', 2: 'Second hex digit', 3: 'Disk busy', 4: 'Organ running',
                 5: 'General wait', 6: 'Record active', 7: 'Playback active', 8: 'Record ready',
                 9: 'Record/play pause', 10: 'File overwrite', 11: 'Error',
                 12: 'Disk write protected', 13: 'Transposer active', 14: 'Display current file'},
}

# Notes.  Keyboard keys and rank pipes are numbered 1..121 on one absolute
# scale: note 1 is the C of the 32' octave (C0, MIDI 12), 25 is 8' C (the
# bottom key of a manual, C2, MIDI 36), 121 is the C ten octaves up.  Key
# numbers in Track files are these numbers.
NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
OCTAVES = ["32'", "16'", "8'", "4'", "2'", "1'", "1/2'", "1/4'", "1/8'", "1/16'", "1/32'"]
NOTES = 121

def note_name(n):
    if n <= 0 or n > NOTES:
        return str(n)
    return f"{OCTAVES[(n - 1) // 12]} {NOTE_NAMES[(n - 1) % 12]}"

def midi_note(n):
    return n + 11

def io_address(v):
    """Console I/O address word as the monitor prints it (sys_putaddr, $5DB6)."""
    if v == 0:
        return "-----"
    d = (v - 1) & 0xFFFF
    letters = (chr(65 + (d >> 11 & 15)) + chr(65 + (d >> 7 & 15)) + ("~" if d & 0x8000 else "-")
               + chr(65 + (d >> 3 & 15)) + chr(49 + (d & 7)))
    m = v & 0x7FFF                         # the relay masks bit 15 (polarity) before the MIDI test ($B45A)
    if 0x6001 <= m <= 0x6800:              # MIDI note: board letter M, channel, note (README "MIDI pseudo addresses")
        return f"{letters} (MIDI ch{((m - 1) >> 7 & 15) + 1} note {(m - 1) & 0x7F})"
    if 0x6801 <= m <= 0x7000:              # MIDI program change as an input: board letter N
        return f"{letters} (MIDI ch{((m - 1) >> 7 & 15) + 1} program {(m - 1) & 0x7F})"
    return letters

# ----------------------------------------------------------------------------- parsing
class Item:
    def __init__(self, listname, number, body, name):
        self.list, self.number, self.name = listname, number, name
        self.raw = body
        size = next((s for s, (n, s) in ((v[1], v) for v in LISTS.values()) if n == listname), 0)
        self.body = body + bytes(max(0, max(size, 2) - len(body)))

    def w(self, off):
        return struct.unpack_from("<H", self.body, off)[0] if off + 2 <= len(self.body) else 0

    def s(self, off):
        v = self.w(off)
        return v - 0x10000 if v >= 0x8000 else v

    def b(self, off):
        return self.body[off] if off < len(self.body) else 0

    @property
    def type(self):
        return self.w(0)

    def words(self, off, n):
        return [self.w(off + 2 * i) for i in range(n)]

    def __repr__(self):
        return f"{self.list} {self.number} {self.name!r}"

class Definition:
    def __init__(self, data):
        if len(data) < 4:
            raise ValueError(f"not a definition file ({len(data)} bytes)")
        self.version = struct.unpack_from("<H", data, 0)[0]
        if not 0x1A12 <= self.version <= 0x1A15:
            raise ValueError(f"not a definition file (version word ${self.version:04X})")
        self.lists = {}
        self.unknown = []
        pos = 2
        while True:
            lid = struct.unpack_from("<H", data, pos)[0]; pos += 2
            if lid == 0xFFFF:
                break
            count = struct.unpack_from("<H", data, pos)[0]; pos += 2
            name = LISTS.get(lid, (f"L{lid:04X}", 0))[0]
            if lid not in LISTS:
                self.unknown.append(lid)
            items = []
            for i in range(count):
                body, pos = self._counted(data, pos)
                if self.version < 0x1A15:
                    body = body[8:]
                nm, pos = self._counted(data, pos)
                items.append(Item(name, i + 1, body, nm.split(b"\0")[0].decode("latin-1")))
            self.lists[name] = items
        self.end = pos

    def _counted(self, data, pos):
        if self.version >= 0x1A15:
            n = data[pos]; pos += 1
        else:
            n = struct.unpack_from("<H", data, pos)[0]; pos += 2
        return data[pos:pos + n], pos + n

    def get(self, listname, number):
        items = self.lists.get(listname, [])
        return items[number - 1] if 1 <= number <= len(items) else None

    def name_of(self, listname, number):
        it = self.get(listname, number)
        if it is None:
            return f"{listname} {number}?" if number else "-"
        return f"{listname} {number} {it.name}" if it.name else f"{listname} {number}"

    # -- links / functions
    def link_expression(self, lnk, names=False):
        """The RPN stop expression at the head of a Lnk body, as infix text.
        Words: n = stop n, $4000+n = control button n, $8000 or, $8001 not,
        $8002 and, 0 = end (stop_event, $AE34)."""
        stack = []
        for i in range(15):
            v = lnk.w(2 * i)
            if v == 0:
                break
            if v & 0x8000:
                op = v & 0xFF
                try:
                    if op == 1:
                        a = stack.pop(); stack.append(f"not {a}")
                    elif op == 2:
                        b_, a = stack.pop(), stack.pop(); stack.append(f"({a} and {b_})")
                    else:
                        b_, a = stack.pop(), stack.pop(); stack.append(f"({a} or {b_})")
                except IndexError:
                    stack.append("?")
            elif v & 0x4000:
                stack.append(f"Ctl {v & 0x3FFF}")
            else:
                stack.append((f"[{self.name_of('Stp', v)}]" if names else f"Stp {v}"))
        return " ".join(stack) if stack else "-"

    def link_stops(self, lnk):
        """Stop numbers an expression refers to."""
        out = []
        for i in range(15):
            v = lnk.w(2 * i)
            if v == 0:
                break
            if not v & 0xC000:
                out.append(v)
        return out

    def link_functions(self, lnk):
        return [v for v in lnk.words(30, 10) if v]

    def links_of_stop(self, stop_number):
        return [l for l in self.lists.get("Lnk", []) if stop_number in self.link_stops(l)]

    def keyboard_keys(self, kbd):
        """Key numbers that have an input address."""
        return [k for k in range(1, 122) if kbd.w(2 * k)]

    def rank_notes(self, rnk):
        return [n for n in range(1, 122) if rnk.w(2 * n)]

# ----------------------------------------------------------------------------- display
def fmt_field(d, item, label, kind, off, ref):
    if kind == 0x01:
        return item.name
    if kind == 0x13:
        v = item.w(off)
        return f"{v} {TYPE_NAMES.get(ref, {}).get(v, '?')}"
    if kind == 0x02:
        v = item.w(off)
        if ref in TYPE_NAMES:
            return f"{v} {TYPE_NAMES[ref].get(v, '?')}" if v else "-"
        return d.name_of(ref, v) if v else "-"
    if kind in (0x0E, 0x0F):
        return io_address(item.w(off))
    if kind == 0x0B:
        return f"{item.w(off)} milliseconds"
    if kind == 0x05:
        return str(item.w(off))
    if kind == 0x04:
        return "Inactive" if item.b(off) else "Active"
    if kind == 0x03:
        return "yes" if item.b(off) else "no"
    if kind == 0x14:
        return "Hot" if item.w(off) else "Ground"
    if kind == 0x07:
        v = item.w(off)
        return f"{v} ({note_name(v)})" if v else "- (default)"
    if kind == 0x12:
        v = item.s(off)
        return f"{v:+d} semitones" if v else "0"
    if kind == 0x0A:
        return d.link_expression(item, names=True)
    if kind in (0x10, 0x11):
        return grid(item, 0 if kind == 0x10 else 2)
    if kind in (0x08, 0x09):
        ws = item.words(0, 122)
        return "timing table: " + " ".join(str(w) for w in ws)
    return f"${item.w(off):04X}"

def grid(item, base):
    """The editor's 12-row octave grid of note addresses."""
    lines = ["\n        " + "".join(f"{o:>12}" for o in OCTAVES[:10]) + f"{'':>12}"]
    for row in range(12):
        cells = []
        for col in range(11):
            n = col * 12 + row + 1
            cells.append(io_address(item.w(base + 2 * n)) if n <= NOTES else "")
        lines.append(f"   {NOTE_NAMES[row]:<3} " + "".join(f"{c:>12}" for c in cells))
    return "\n".join(lines)

def item_fields(d, item):
    spec = FIELDS.get(item.list)
    if spec is None:
        return [("Body", item.raw.hex(" "))]
    fields = spec.get(None) or spec.get(item.type) or spec.get(0) or []
    return [(label, fmt_field(d, item, label, kind, off, ref)) for label, kind, off, ref in fields]

def summary_line(d, item):
    """One line per item, like the editor's list screens."""
    t = item.type
    if item.list == "Kbd":
        keys = d.keyboard_keys(item)
        return (f"{len(keys)} keys {note_name(keys[0])}..{note_name(keys[-1])} "
                f"(key numbers {keys[0]}..{keys[-1]})" if keys else "no keys")
    if item.list == "Rnk":
        notes = d.rank_notes(item)
        return (f"{len(notes)} pipes {note_name(notes[0])}..{note_name(notes[-1])} "
                f"(notes {notes[0]}..{notes[-1]}, first {io_address(item.w(2 * notes[0]))})"
                if notes else "no pipes")
    if item.list == "Stp":
        links = d.links_of_stop(item.number)
        return (f"{TYPE_NAMES['StpTypes'].get(t, 'type %d' % t)}, contact {io_address(item.w(8))}"
                + (f", links {','.join(str(l.number) for l in links)}" if links else ""))
    if item.list == "Lnk":
        fn = d.link_functions(item)
        return f"{d.link_expression(item)} -> Fnc {','.join(map(str, fn)) if fn else '-'}"
    if item.list == "Fnc":
        name = TYPE_NAMES['FncTypes'].get(t, "type %d" % t)
        if t == 3:
            return (f"{name}: {d.name_of('Kbd', item.w(2))} -> {d.name_of('Rnk', item.w(4))}"
                    f" offset {item.s(6):+d}" + (f" notes {item.w(8) or 1}..{item.w(10) or NOTES}"
                                                if item.w(8) or item.w(10) else ""))
        if t in (1, 10):
            return (f"{name}: {d.name_of('Kbd', item.w(2))} plays {d.name_of('Kbd', item.w(4))}"
                    f" offset {item.s(6):+d}")
        if t == 5:
            return f"{name}: {d.name_of('Unt', item.w(2))}"
        if t == 4:
            return f"{name}: {d.name_of('Kbd', item.w(2))} -> {d.name_of('Unt', item.w(4))}"
        if t in (6, 7, 8, 18):
            return f"{name}: {d.name_of('Kbd', item.w(2))}"
        if t in (13, 14):
            return f"{name} of {d.name_of('Fnc', item.w(2))}"
        return name
    if item.list == "Unt":
        return f"{TYPE_NAMES['UntTypes'].get(t, 'type %d' % t)}, output {io_address(item.w(4))}"
    if item.list == "Chn":
        return TYPE_NAMES['ChnTypes'].get(t, "type %d" % t)
    if item.list in FIELDS and FIELDS[item.list].get(None):
        parts = [f"{lab} {val}" for lab, val in item_fields(d, item)[1:] if val not in ("-", "-----")]
        return "; ".join(parts)
    return ""

def print_list(d, listname):
    items = d.lists.get(listname)
    if not items:
        print(f"--- {listname}: no items"); return
    print(f"--- {listname} ({len(items)} items)")
    for it in items:
        print(f"{listname} {it.number:3d}  {it.name:<28} {summary_line(d, it)}")

def print_item(d, listname, number):
    it = d.get(listname, number)
    if it is None:
        print(f"no {listname} {number}"); return
    print(f"--- {listname} {number}")
    for label, value in item_fields(d, it):
        print(f"  {label + ':' if label else '':<26} {value}")
    if listname == "Stp":
        links = d.links_of_stop(number)
        print(f"  {'Link references:':<26} {', '.join(str(l.number) for l in links) or '-'}")
        for l in links:
            print(f"      Lnk {l.number}: {d.link_expression(l)} -> "
                  + ", ".join(d.name_of('Fnc', f) for f in d.link_functions(l)))
    if listname == "Lnk":
        for f in d.link_functions(it):
            fn = d.get("Fnc", f)
            if fn:
                print(f"      {d.name_of('Fnc', f)}: {summary_line(d, fn)}")

def print_summary(d):
    print(f"definition version ${d.version:04X}; lists: "
          + ", ".join(f"{n} {len(d.lists[n])}" for n in LIST_ORDER if n in d.lists)
          + (f"; unknown list ids {['$%04X' % u for u in d.unknown]}" if d.unknown else ""))
    for name in ("Kbd", "Chn"):
        if name in d.lists:
            print_list(d, name)
    stops = d.lists.get("Stp", [])
    named = [s for s in stops if s.name]
    print(f"--- Stp: {len(stops)} stops, {len(named)} named")
    for s in named[:400]:
        print(f"Stp {s.number:3d}  {s.name:<28} {summary_line(d, s)}")

def load(args):
    if args.file:
        return Definition(open(args.file, "rb").read()), args.file
    disk = Disk(args.side0, args.side1)
    e = disk.find(args.d)
    if e.letter != "D":
        raise SystemExit(f"{e.slot} is a {e.type} file, not a definition")
    return Definition(e.read()), f"{e.slot} {e.name!r}"

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("side0", nargs="?"); ap.add_argument("side1", nargs="?")
    ap.add_argument("-d", default="D1", help="definition slot (default D1)")
    ap.add_argument("--file", help="read an extracted definition file instead of a disk")
    ap.add_argument("--list", metavar="LIST", help="Kbd, Rnk, Stp, ... or all")
    ap.add_argument("--item", nargs=2, metavar=("LIST", "N"))
    a = ap.parse_args()
    if not a.file and not a.side0:
        ap.error("give a disk image or --file")
    try:
        d, what = load(a)
    except (ValueError, KeyError, IndexError, struct.error) as err:
        raise SystemExit(f"error: {err}")
    print(f"{what}: definition version ${d.version:04X}, {sum(len(v) for v in d.lists.values())} items")
    if a.item:
        print_item(d, a.item[0].capitalize(), int(a.item[1]))
    elif a.list:
        for name in (LIST_ORDER if a.list.lower() == "all" else [a.list.capitalize()]):
            if name in d.lists:
                print_list(d, name)
    else:
        print_summary(d)

if __name__ == "__main__":
    main()
