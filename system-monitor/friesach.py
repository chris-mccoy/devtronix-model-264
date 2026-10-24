#!/usr/bin/env python3
"""Hauptwerk Friesach as a playback target for Devtronix recordings
(dev2midi.py --friesach).

The organ.  Piotr Grabowski's free sample set (organ ID 002213, version 1.06)
of the Eisenbarth organ (2000) in St. Bartholomäus, Friesach, Austria: a
classical organ of 44 stops on Hauptwerk (I), Schwellwerk (II, the only
enclosed division), Solowerk (III) and Pedal.  Manuals C-c4 (MIDI 36-96;
the organ's own C-a3, 36-93, is exactly the 58 Note Player's compass),
Pedal C-g1 (36-67), Trompete en chamade from c (48).  Hauptwerk's "MIDI
recorder MIDI implementation (raw data)" export for it is friesach-spec.xml:

  keys     note on/off, one channel per keyboard: Pedal 1, Hauptwerk 2,
           Schwellwerk 3, Solowerk 4
  stops    NRPN on channel 2 (CC 99/98 number, CC 6 value), 127 = on, 0 = off;
           the six unison couplers and the two tremulants the same way
  swell    CC 11 on channel 3 (the Schwellwerk enclosure)

The pistons and setter buttons are sys-ex only and are not used.

The mapping.  The same as for the Paramount 332 (see paramount332.py and
hauptwerk.py): the Devtronix relay logic decides which ranks sound at which
pitch on which division, and each of those becomes a stop on the manual the
keys come from.  Theatre and MIDI ranks have different names from a classical
organ's stops, so RANKS gives each rank a voice family (Principal, Flute,
Gedackt, String, ...) and the stop is the one of that family at that pitch on
that manual; NEAR names the families tried next.  Nearly every rank is a
stand-in ("?").  The tables:

  keyboards  Great -> Hauptwerk, Swell and Accompaniment -> Schwellwerk,
             Choir and Solo -> Solowerk; Bombarde and Echo go to the Hauptwerk
             or the Solowerk, whichever has stops for more of what the track
             registers on them.  Any other keyboard plays the Hauptwerk.
  player     the 58 Note Player plays the Hauptwerk, and its lowest held key
             also plays the Pedal on Subbaß 16' and Octavbaß 8' (BASS) while
             it is in the bottom two octaves, C-b.  The player definitions send
             their bottom octave to a pedal division of their own (Midi 16",
             Midi Pedal, Voice 1); those ranks sound on the Pedal only, so the
             player's own Pedal rank leaves the Hauptwerk alone.  II/I and
             III/I are drawn for every roll, so stops drawn by hand on the
             Schwellwerk and Solowerk play along (KEYBOARD_SWITCHES); only
             keyboards a track plays draw registration (PLAYED_ONLY), so the
             extra keyboards of the 58-note-16-2/-17/-18 definitions leave
             those two manuals empty.
  couplers   I/P, II/P, III/P, II/I, III/I and III/II are played with the
             Friesach's own; octave couplers, unison off and the rest are
             folded into the registration.
  traps      the Friesach has no percussion: traps, tuned percussion and
             pianos are silent.
  tremulants Solo and Choir tremulants -> Tremulant 3Man, Great ones -> none
             (the Hauptwerk has no tremulant), every other -> Tremulant 2Man.
  swell      Swell (else Main, else Echo) shades drive the Schwellwerk.
"""
import re

from hauptwerk import AUTO

ORGAN, SHORT = "Friesach", "Friesach"
KEYBOARD_CHANNELS = {"P": 0, "HW": 1, "SW": 2, "SL": 3}           # 0-based
KEYBOARD_NAMES = {"P": "Pedal", "HW": "Hauptwerk", "SW": "Schwellwerk", "SL": "Solowerk"}
NRPN_CHANNEL = 1
SWELLS = {(2, 11): ["swell", "main", "echo"]}                       # (channel, CC) -> chambers

# Stop tabs: (switch, NRPN, voice family, footage).  Mixtures play at any pitch.
STOPS = [
    ("01. P  Untersatz 32'",               2001, "Gedackt",       "32"),
    ("02. P  Contrabaß 16'",               2002, "Principal",     "16"),
    ("03. P  Subbaß 16'",                  2003, "Gedackt",       "16"),
    ("04. P  Octavbaß 8'",                 2004, "Principal",     "8"),
    ("05. P  Gedackt 8'",                  2005, "Gedackt",       "8"),
    ("06. P  Choralbaß 4'",                2006, "Principal",     "4"),
    ("07. P  Posaune 32'",                 2007, "Trumpet",       "32"),
    ("08. P  Posaune 16'",                 2008, "Trumpet",       "16"),
    ("09. P  Trompete 8'",                 2009, "Trumpet",       "8"),
    ("10. HW  Praestant 16'",              2101, "Principal",     "16"),
    ("11. HW  Principal 8'",               2102, "Principal",     "8"),
    ("12. HW  Holzflöte 8'",               2103, "Flute",         "8"),
    ("13. HW  Röhrflöte 8'",               2104, "Gedackt",       "8"),
    ("14. HW  Gambe 8'",                   2105, "String",        "8"),
    ("15. HW  Octave 4'",                  2106, "Principal",     "4"),
    ("16. HW  Spitzflöte 4'",              2107, "Flute",         "4"),
    ("17. HW  Quinte 2 2/3'",              2108, "Principal",     "2 2/3"),
    ("18. HW  Octave 2'",                  2109, "Principal",     "2"),
    ("19. HW  Mixtur major 4-5f. 2 2/3'",  2110, "Mixture",       None),
    ("20. HW  Mixtur minor 4f. 1 1/3'",    2111, "Sharp Mixture", None),
    ("21. HW  Trompete 16'",               2112, "Trumpet",       "16"),
    ("22. HW  Trompete 8'",                2113, "Trumpet",       "8"),
    ("23. SW  Bourdon 16'",                2201, "Gedackt",       "16"),
    ("24. SW  Principal 8'",               2202, "Principal",     "8"),
    ("25. SW  Nachthorn Gedackt 8'",       2203, "Gedackt",       "8"),
    ("26. SW  Corno dolce 8'",             2204, "Dolce",         "8"),
    ("27. SW  Viola 8'",                   2205, "String",        "8"),
    ("28. SW  Vox celeste 8'",             2206, "Celeste",       "8"),
    ("29. SW  Geigenprincipal 4'",         2207, "Principal",     "4"),
    ("30. SW  Querflöte 4'",               2208, "Flute",         "4"),
    ("31. SW  Nazard 2 2/3'",              2209, "Flute",         "2 2/3"),
    ("32. SW  Flageolett 2'",              2210, "Flute",         "2"),
    ("33. SW  Tierce 1 3/5'",              2211, "Flute",         "1 3/5"),
    ("34. SW  Larigot 1 1/3'",             2212, "Flute",         "1 1/3"),
    ("35. SW  Plein Jeu 4-5f. 2'",         2213, "Mixture",       None),
    ("36. SW  Scharff 4f. 1'",             2214, "Sharp Mixture", None),
    ("37. SW  Trompete harmonique 8'",     2215, "Trumpet",       "8"),
    ("38. SW  Hautbois 8'",                2216, "Oboe",          "8"),
    ("39. SW  Clairon 4'",                 2217, "Trumpet",       "4"),
    ("40. SL  Jubalflöte 8'",              2301, "Flute",         "8"),
    ("41. SL  Trichterflöte 4'",           2302, "Flute",         "4"),
    ("42. SL  Cornet a pavilon 1-8f. 8'",  2303, "Cornet",        "8"),
    ("43. SL  Trompete en chamade 8'",     2304, "Trumpet",       "8"),
    ("44. SL  Englischhorn 8'",            2305, "English Horn",  "8"),
]

def stop_division(switch):
    m = re.match(r"\d+\. (P|HW|SW|SL) ", switch)
    return m.group(1) if m else None

SWITCHES = {name: nrpn for name, nrpn, _, _ in STOPS}
SWITCHES.update({
    "45. I/P":              1101,
    "46. II/P":             1201,
    "47. III/P":            1301,
    "48. II/I":             1111,
    "49. III/I":            1116,
    "50. III/II":           1216,
    "51. Tremulant 2Man":   1720,
    "52. Tremulant 3Man":   1730,
})

# ----------------------------------------------------------------------------- the mapping
AUTO_CHOICES = ("HW", "SL")             # tie goes to the first

# Devtronix keyboard -> Friesach keyboard.  None: the keys are dropped (and
# counted) along with anything registered on them; names not listed play the
# Hauptwerk.
KEYBOARDS = {
    "Pedal": "P", "Pedal Keys": "P",
    "Great": "HW", "Great Keys": "HW", "Great 1st Touch": "HW", "Midi Great": "HW",
    "Swell": "SW", "Swell Keys": "SW",
    "Accomp": "SW", "Accomp.": "SW", "Accomp Keys": "SW", "Accomp 1st T": "SW",
    "Accompaniment 1st Touch": "SW",
    "Choir": "SL", "Choir Keys": "SL",
    "Solo": "SL", "Solo Keys": "SL",
    "Bombarde": AUTO, "Echo": AUTO,
    "58 Note Player": "HW",
    "Accomp 2T": None, "Accomp. 2T": None, "Accomp 2nd T": None, "Accomp 2nd Tnd T": None,
    "Accompaniment 2nd Touch": None, "Great 2T": None, "Great 2nd Touch": None,
    "Great 2T (Peterson)": None, "Great 2T (4 Manual)": None, "Bombarde 2T": None,
    "String (Floating)": None, "Pedal on CHIORDON": None, "TEST KEYBOARD": None,
}
DEFAULT_KEYBOARD = "HW"

# The roll player's lowest held key also plays the Pedal while it is in the
# bottom two octaves.  The player definitions send only the bottom octave to
# the Pedal, (36, 47); (36, 67) would use the whole Pedal, C-g1.
BASS = {"58 Note Player": "P"}
BASS_RANGE = (36, 59)                   # MIDI notes, C-b
# Drawn for every roll: the Pedal stops its lowest key plays, and II/I and
# III/I so that stops drawn on the Schwellwerk and Solowerk sound with it.
KEYBOARD_SWITCHES = {"58 Note Player": ["03. P  Subbaß 16'", "04. P  Octavbaß 8'", "48. II/I", "49. III/I"]}
PLAYED_ONLY = True

NATIVE_COUPLERS = {
    ("P", "HW", 0): "45. I/P", ("P", "SW", 0): "46. II/P", ("P", "SL", 0): "47. III/P",
    ("HW", "SW", 0): "48. II/I", ("HW", "SL", 0): "49. III/I", ("SW", "SL", 0): "50. III/II",
}

def pedal(spec):
    """A rank that sounds on the Pedal only (silent where a manual plays it)."""
    return {"P": spec}

# Devtronix rank -> Friesach voice family.  "?" = stand-in, "@16" = fixed
# footage, "A|B" = A, else B where the manual has no A at that pitch,
# None = silent.  Names are matched without regard to case or spacing.
RANKS = {
    # principals and diapasons
    "Open Diapason": "Principal", "Main Open Diapason": "Principal", "Principal": "Principal",
    "Echo Principal": "Principal", "DIAPASON": "Principal",
    "Diaphonic Diapason": "Principal?", "Horn Diapason": "Principal?", "Solo Horn Diapason": "Principal?",
    "Diapason Celeste": "Principal?", "Voce Umana": "Principal?",     # diapason celestes
    "Twelfth": "Principal", "2 2/3 Twelfth": "Principal",
    # flutes: the tibias are the big round flutes (Jubalflöte, Holzflöte)
    "Tibia Clausa": "Flute?", "Main Tibia Clausa": "Flute?", "Main Tibia": "Flute?",
    "Main Tibia Minor": "Flute?", "Lieblich Flute": "Flute?", "Tibia Minor": "Flute?",
    "Solo Tibia": "Flute?", 'Solo Tibia (15")': "Flute?", 'Solo Tibia Clausa (10")': "Flute?",
    "Tibia Clausa (Solo)": "Flute?", "Tibia (Unenclosed)": "Flute?",
    "Echo Tibia": "Flute?", "Echo Tibia Clausa": "Flute?", "Echo Lieblich Tibia": "Flute?",
    "Concert Flute": "Flute?", "Main Concert Flute": "Flute?", "FLUTE": "Flute",
    "Flute Celeste": "Flute?", "Echo Spitzflute Chest II": "Flute",
    "Gedeckt": "Gedackt", "Lieblich Gedeckt (String Organ)": "Gedackt?",
    "Quintadena": "Gedackt?", "Main Quintadena": "Gedackt?", "Quintadena Celeste": "Gedackt?",
    # strings
    "Viol d' Orch": "String?", "Viol D' Orchestra": "String?", "Viol d'Orchestre": "String?",
    "Main V.D.O.": "String?",
    "Viol Celeste": "Celeste?", "VDO Celeste": "Celeste?", "Main Viol Celeste": "Celeste?",
    "Gamba (String Organ)": "String", "Solo Gamba": "String",
    "Gamba Celeste (String Organ)": "Celeste?", "Solo Gamba Celeste": "Celeste?",
    "Main Voix Celeste": "Celeste", "Voix Celeste (Solo)": "Celeste", "Solo Voix Celeste": "Celeste",
    "Celeste": "Celeste",
    "Salicional": "String?", "Main Salicional": "String?", "Salicional (Solo)": "String?",
    "Solo Salicional (MPM)": "String?", "Salicional (String Organ)": "String?",
    "Salicional (16' String Organ)": "String?",
    "Salicional Celeste": "Celeste?", "Salicional Celeste (String Organ)": "Celeste?",
    "Main String": "String?", "Solo String": "String?", "Echo String": "String?",
    "Echo String Main Chest": "String?",
    "Solo String Celeste": "Celeste?", "Echo String Celeste": "Celeste?",
    "Violin": "String?", "Violin (String Organ)": "String?", "Viola Pomposa (String Organ)": "String?",
    "Muted Viol (String Organ)": "String?", "Viola Dolce (mpm)": "String?",
    "Violin Celeste": "Celeste?", "Violin Celeste (String Organ)": "Celeste?",
    "Viola Pomposa Celeste (String Organ)": "Celeste?", "Muted Viol Celeste (String Organ)": "Celeste?",
    "Viola Celeste (String Organ)": "Celeste?", "Viola Dolce Celeste": "Celeste?",
    # soft flues: dulcianas and gemshorns -> Corno dolce
    "Dulciana": "Dolce?", "Dulcet (String Organ)": "Dolce?", "Gemshorn (String Organ)": "Dolce?",
    "Dulciana Celeste": "Celeste?", "Dulcet Celeste (String Organ)": "Celeste?",
    "Gemshorn Celeste (String Organ)": "Celeste?", "Unda Maris": "Celeste?",
    # reeds
    "Trompette": "Trumpet", "Brass Trumpet": "Trumpet", "Chorus Trumpet": "Trumpet",
    "Solo Trumpet": "Trumpet", "Trumpet (en-chamade)": "Trumpet",
    "Tuba Horn": "Trumpet?", "Main Tuba Horn": "Trumpet?",
    "Tuba Mirabilis": "Trumpet?", "Solo Tuba Mirabilis": "Trumpet?",
    "English Horn": "English Horn", "Solo English Horn": "English Horn",
    "Brass Saxophone": "English Horn?|Oboe?", "Solo Saxophone": "English Horn?|Oboe?",
    "French Horn": "English Horn?|Oboe?",
    "Orchestral Oboe": "Oboe?|English Horn?", "Solo Orch. Oboe": "Oboe?|English Horn?",
    "Oboe Horn": "Oboe?|English Horn?", "Main Oboe Horn": "Oboe?|English Horn?",
    "Clarinet": "Oboe?|English Horn?", "Main Clarinet": "Oboe?|English Horn?",
    "Kinura": "Oboe?|English Horn?", "Solo Kinura": "Oboe?|English Horn?",
    "Musette": "Oboe?|English Horn?", "Corno d' Amore (String Organ)": "Oboe?|English Horn?",
    # the Friesach has no Vox Humana; Hautbois (and the tremulant) instead
    "Vox Humana": "Oboe?|English Horn?", "Main Vox Humana": "Oboe?|English Horn?",
    "Solo Vox Humana": "Oboe?|English Horn?", "Vox Humana (Solo)": "Oboe?|English Horn?",
    "Vox Humana mf (String Organ)": "Oboe?|English Horn?",
    "Vox Humana p (String Organ)": "Oboe?|English Horn?",
    "Echo Vox (16')": "Oboe?|English Horn?", "Echo Vox (8')": "Oboe?|English Horn?",
    "Echo Vox (4')": "Oboe?|English Horn?", "Echo Vox Celeste (8')": "Oboe?|English Horn?",
    "Echo 16' Vox Humana": "Oboe?|English Horn?", "Echo 8' Vox Humana": "Oboe?|English Horn?",
    "Echo 4' Vox Humana": "Oboe?|English Horn?", "Echo 8' Vox Humana Celeste": "Oboe?|English Horn?",
    # mixtures: each rank of one is the manual's mixture
    "I Mixture": "Mixture", "II Mixture": "Mixture", "III Mixture": "Mixture", "IV Mixture": "Mixture",
    "Mixture IV": "Mixture", "MIXTURE I": "Mixture", "MIXTURE II": "Mixture", "MIXTURE III": "Mixture",
    "Great Mixture I": "Mixture", "Great Mixture II": "Mixture",
    "Great Mixture III": "Mixture", "Great Mixture IV": "Mixture",
    "Wired Mixture I": "Mixture", "Wired Mixture II": "Mixture", "Wired Mixture III": "Mixture",
    # pedal resultants and bombardes: Untersatz 32'
    "32' Resultant": "Gedackt? @32", "32' Resultant (Lieb)": "Gedackt? @32",
    "32' Resultant(Bourdon)": "Gedackt? @32",
    "32' Pedal Bourdon I": "Gedackt? @32", "32' Pedal Bourdon II": "Gedackt? @32",
    "32' Pedal Bourdon III": "Gedackt? @32", "32' Pedal Bourdon IV": "Gedackt? @32",
    "32' Soft Bourdon I": "Gedackt? @32", "32' Soft Bourdon II": "Gedackt? @32",
    "Bombarde I": "Gedackt? @32", "Bombarde II": "Gedackt? @32", "Bombarde III": "Gedackt? @32",
    "Bombarde IV": "Gedackt? @32", "Bombarde V": "Gedackt? @32", "Bombarde VI": "Gedackt? @32",
    "Bombarde VII": "Gedackt? @32",
    # MIDI divisions (the 58 Note Player, the McCoy and Ahlborn definitions)
    "Midi 8'": "Principal?", "Midi 4'": "Principal?", "Midi Great": "Principal?",
    "Great Midi Out": "Principal?", "Great Midi Driver": "Principal?", "GREAT MIDI": "Principal?",
    "GREAT MIDIN": "Principal?", "GREAT DIVISION": "Principal?", "DIVISION A": "Principal?",
    "Accomp Midi Out": "Gedackt?", "Midi Swell": "Flute?", "SWELL MIDI": "Flute?",
    "SWELL DIVISION": "Flute?", "DIVISION B": "Flute?", "CHOIR DIVISION": "Flute?",
    "Solo Midi Out": "Flute?", "STOPS": "Principal?",
    'Midi 16"': pedal("Gedackt? @16"), "Midi Pedal": pedal("Gedackt? @16"),
    "Voice 1": pedal("Principal? @16"), "PEDAL": pedal("Gedackt? @16"),
    "PEDAL DIVISION": pedal("Gedackt? @16"), "Pedal Midi Out": pedal("Gedackt? @16"),
    "PEDAL MIDIDON": pedal("Gedackt? @16"),
    "Voice 2": None, "Voice 3": None, "Voice 4": None, "Voice 5": None,
    # the MIDI orchestra of the New Console and Tour Disc
    "Midi 1 - Str. Bass": "String?|Principal?", "Midi 7 - String Bass": "String?|Principal?",
    "Midi 16 - Pedal Double Bases": "String?|Principal?", "Midi Double Basses": "String?|Principal?",
    "Midi 2 - Bowed Strings": "String?", "Midi 8 - Arco Strings": "String?",
    "Midi 13 - Str. Tremolo": "String?", "Midi 14 - Pizz. Strings": "String?",
    "Midi 5 - Mute Trumpets": "Oboe?|Trumpet?", "Midi 6 - English Horn": "English Horn",
    "Midi 12 - Solo Flute": "Flute?", "Midi 15 - Trombone/vib.": "Trumpet?",
    "Midi 3 - Harp": None, "Midi 3 - Orchestral Harp": None, "Midi 4 - Tympani": None,
    # no tuned percussion and no piano on the Friesach
    "Chrysoglott": None, "Main Chrysoglott": None, "Glockenspiel": None, 'Glockenspiel (15")': None,
    "Glockenspiel (regular)": None, "Glockenspiel (Perc.)": None, "Glockenspiel (solo)": None,
    "Glockenspiel Celeste": None, "Glockenspiel (Celeste A-435)": None, "Solo Glock": None,
    "Xylophone": None, "Xylophone (SS)": None, "Master Xylophone": None, "Solo Xylophone": None,
    "Xylophone (Reit)": None, "Xylophone Reiterate": None,
    "Harp": None, "Marimba / Harp": None, "Marimba/Harp": None, "Solo Harp/Marimba": None,
    "Vibraharp": None, "Cathedral Chimes": None, "Chimes": None, "Solo Chimes": None,
    "Sleigh Bells": None, "Solo Sleighballs": None, "Tuned Birds": None, "Tuned Bird Whistles": None,
    "Piano": None, "Piano-Corder": None, "Midi 1 & 2 Piano (Bosendorfer)": None,
    "Midi 9 - Chamber Piano": None,
    # test ranks named after output boards
    "AA": None, "BB": None, "CC": None, "DD": None, "EE": None, "FF": None, "BLANK": None, "": None,
}

# When a manual has no stop of a family at the pitch asked for, the first of
# these it has at that pitch.  Every chain ends in the flues, so a 16' string
# or reed on the Schwellwerk falls back to the Bourdon rather than going silent.
NEAR = {
    "Principal": ["Flute", "Gedackt", "String", "Dolce"],
    "Flute": ["Gedackt", "Principal", "Dolce", "String"],
    "Gedackt": ["Flute", "Principal", "Dolce"],
    "String": ["Celeste", "Dolce", "Principal", "Gedackt", "Flute"],
    "Celeste": ["String", "Dolce", "Principal", "Gedackt", "Flute"],
    "Dolce": ["String", "Principal", "Gedackt", "Flute"],
    "Trumpet": ["English Horn", "Oboe", "Principal"],
    "Oboe": ["English Horn", "String", "Trumpet", "Gedackt"],
    "English Horn": ["Oboe", "String", "Trumpet", "Gedackt"],
    "Cornet": ["Flute"],
    "Mixture": ["Sharp Mixture"], "Sharp Mixture": ["Mixture"],
}

TRAP_DEFAULT = None                     # no percussion: every trap is silent

# Tremulant units (name contains "trem"): the first pattern that matches.
TREMULANTS = [
    (r"solo|choir", ["52. Tremulant 3Man"]),
    (r"great", []),
    (r".", ["51. Tremulant 2Man"]),
]
