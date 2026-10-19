#!/usr/bin/env python3
"""Hauptwerk Paramount 332 as a playback target for Devtronix recordings
(dev2midi.py --paramount).

The organ.  Hauptwerk's MIDI recorder/player uses a fixed MIDI implementation
per virtual organ; for the Paramount 332 (Paramount Organ Works, organ ID
001113, version 2.11) it is in paramount332-spec.xml, Hauptwerk's "MIDI
recorder MIDI implementation (raw data)" export for the organ:

  keys     note on/off, one channel per keyboard: Pedal 1, Accompaniment 2,
           Accompaniment 2nd touch 13, Great 3, Solo 4
  stops    NRPN on channel 2 (CC 99/98 number, CC 6 value), 127 = on, 0 = off;
           couplers, tremulants, re-iterate and effects the same way
  swells   CC 11: Main on channel 4, Solo on 3, Percussions on 2

Only switches the file gives an NRPN for can be played.  The piano stops, the
celeste on/off switches and some couplers are sys-ex only and are not used.

The mapping.  dev2midi.Organ runs the relay logic of the Devtronix definition,
which decides which ranks sound at which pitch on which division.  Each of
those becomes a Paramount stop tab on the manual the keys come from:

  keyboards  KEYBOARDS: Devtronix keyboard -> Paramount keyboard.  AUTO
             keyboards (Bombarde, Echo) go to the Great or the Solo, whichever
             has a stop tab for more of what the track registers on them; the
             Great wins a tie.
  couplers   are played with the Paramount's own couplers where it has the
             same one (NATIVE_COUPLERS: Accomp to Pedal, Solo to Great, a
             manual's octave and sub octave while its unison is on, ...);
             those reach pitches and top-octave pipes the receiving manual
             has no stop tab for.  They also carry whatever else has been put
             on the coupled Paramount manual.  Every other coupler is folded
             into the registration: "Echo To Great" puts the Echo division's
             ranks on the Paramount Great, unison off takes the division's own
             ranks away, a coupler at another pitch adds every rank at that
             pitch.
  ranks      RANKS: Devtronix rank name -> Paramount voice.  A trailing "?"
             marks a stand-in for a rank the Paramount does not have; "@32"
             fixes the footage (resultants, mixtures).  Otherwise the pitch is
             the rank function's offset plus the coupler's.
  near       when that manual has no tab for the voice at that pitch, NEAR
             voices are tried (the other tibia, another diapason, a celeste's
             unison rank).
  traps      TRAPS (struck from a division's keys) and EFFECTS (switched
             directly); tremulants TREMULANTS; swells by chamber name.

What cannot be matched is counted and reported, never guessed at silently.
"""
import re

KEYBOARD_CHANNELS = {"Ped": 0, "Acc": 1, "Gt": 2, "Solo": 3, "Acc2T": 12}    # 0-based
KEYBOARD_NAMES = {"Ped": "Pedal", "Acc": "Accompaniment", "Acc2T": "Accompaniment 2nd touch",
                  "Gt": "Great", "Solo": "Solo"}
NRPN_CHANNEL = 1
SWELLS = {"main": (3, 11), "solo": (2, 11), "percussion": (1, 11)}           # chamber -> (channel, CC)

FEET = {"32": -24, "16": -12, "10 2/3": -5, "8": 0, "5 1/3": 7, "4": 12, "3 1/5": 16,
        "2 2/3": 19, "2": 24, "1 3/5": 28, "1 1/3": 31, "1": 36}
PITCH_FEET = {v: k for k, v in FEET.items()}

def feet(pitch):
    """Footage of a pitch offset from 8', e.g. -12 -> "16'"."""
    return PITCH_FEET[pitch] + "'" if pitch in PITCH_FEET else f"{pitch:+d}"

# Stop tabs: (switch, NRPN, voice, footage).  The voice is the Paramount rank
# behind the tab ("Tibia Clausa" where the tab does not say which); tuned
# percussion is 8', "Sub" 16'.  Traps are "trap:<name>" with no footage.
STOPS = [
    ("Stop: Acc: Brass Trumpet 8",                 2102, "Brass Trumpet",         "8"),
    ("Stop: Acc: Chrysoglott",                     2135, "Chrysoglott",           "8"),
    ("Stop: Acc: Clarinet 8",                      2109, "Clarinet",              "8"),
    ("Stop: Acc: Flute 8",                         2118, "Concert Flute",         "8"),
    ("Stop: Acc: Flute Nazard 2 2/3",              2131, "Concert Flute",         "2 2/3"),
    ("Stop: Acc: Flute Piccolo 4",                 2127, "Concert Flute",         "4"),
    ("Stop: Acc: Diaph Diap 8",                    2104, "Diaphonic Diapason",    "8"),
    ("Stop: Acc: Octave 4",                        2121, "Diaphonic Diapason",    "4"),
    ("Stop: Acc: English Horn 8",                  2101, "English Horn",          "8"),
    ("Stop: Acc: Flute Celeste 4",                 2153, "Flute Celeste",         "4"),
    ("Stop: Acc: Flute Celeste 8",                 2150, "Flute Celeste",         "8"),
    ("Stop: Acc: Gamba 8",                         2112, "Gamba",                 "8"),
    ("Stop: Acc: Gambette 4",                      2124, "Gamba",                 "4"),
    ("Stop: Acc: Gamba Celeste 8",                 2148, "Gamba Celeste",         "8"),
    ("Stop: Acc: Gambette Cel 4",                  2151, "Gamba Celeste",         "4"),
    ("Stop: Acc: Harp",                            2134, "Harp",                  "8"),
    ("Stop: Acc: Harp Sub",                        2133, "Harp",                  "16"),
    ("Stop: Acc: Horn Diapason 8",                 2106, "Horn Diapason",         "8"),
    ("Stop: Acc: Octave Horn 4",                   2122, "Horn Diapason",         "4"),
    ("Stop: Acc: Krumet 8",                        2115, "Krumet",                "8"),
    ("Stop: Acc: Oboe Horn 8",                     2116, "Oboe Horn",             "8"),
    ("Stop: Acc: Open Diapason 8",                 2105, "Open Diapason",         "8"),
    ("Stop: Acc: Orch Oboe 8",                     2110, "Orchestral Oboe",       "8"),
    ("Stop: Acc: Quintadena 8",                    2117, "Quintadena",            "8"),
    ("Stop: Acc: Saxophone 8",                     2111, "Saxophone",             "8"),
    ("Stop: Acc: Strings 4",                       2125, "Strings",               "4"),
    ("Stop: Acc: Strings 8",                       2113, "Strings",               "8"),
    ("Stop: Acc: Tibia 12th 2 2/3",                2130, "Tibia Clausa",          "2 2/3"),
    ("Stop: Acc: Tibia Piccolo 2",                 2132, "Tibia Clausa",          "2"),
    ("Stop: Acc: Tibia Clausa I 8",                2107, "Tibia Clausa (M)",      "8"),
    ("Stop: Acc: Tib Piccolo II 4",                2123, "Tibia Clausa (S)",      "4"),
    ("Stop: Acc: Tibia Clausa II 8",               2108, "Tibia Clausa (S)",      "8"),
    ("Stop: Acc: Tuba Horn 8",                     2103, "Tuba Horn",             "8"),
    ("Stop: Acc: Viol 4",                          2126, "VDO",                   "4"),
    ("Stop: Acc: Viol 8",                          2114, "VDO",                   "8"),
    ("Stop: Acc: Vibraphone",                      2136, "Vibraphone",            "8"),
    ("Stop: Acc: Viol Celeste 4",                  2152, "Viol Celeste",          "4"),
    ("Stop: Acc: Viol Celeste 8",                  2149, "Viol Celeste",          "8"),
    ("Stop: Acc: Vox Humana I 4",                  2128, "Vox Humana (M)",        "4"),
    ("Stop: Acc: Vox Humana I 8",                  2119, "Vox Humana (M)",        "8"),
    ("Stop: Acc: Vox Humana II 8",                 2120, "Vox Humana (S)",        "8"),
    ("Stop: Acc: Vox II 4",                        2129, "Vox Humana (S)",        "4"),
    ("Stop: Acc: Castanets",                       2140, "trap:Castanets",        None),
    ("Stop: Acc: Chinese Block",                   2142, "trap:Chinese Block",    None),
    ("Stop: Acc: Hi Hat Closed",                   2145, "trap:Hi Hat Closed",    None),
    ("Stop: Acc: Hi Hat Open",                     2144, "trap:Hi Hat Open",      None),
    ("Stop: Acc: Ride Cymbal",                     2147, "trap:Ride Cymbal",      None),
    ("Stop: Acc: Side Stick",                      2137, "trap:Side Stick",       None),
    ("Stop: Acc: Snare Drum Roll",                 2138, "trap:Snare Drum Roll",  None),
    ("Stop: Acc: Tambourine",                      2143, "trap:Tambourine",       None),
    ("Stop: Acc: Tambourine Roll",                 2139, "trap:Tambourine Roll",  None),
    ("Stop: Acc: Tap Cymbal",                      2146, "trap:Tap Cymbal",       None),
    ("Stop: Acc: Tom Tom",                         2141, "trap:Tom Tom",          None),
    ("Stop: Acc2T: Brass Trumpet 8",               2502, "Brass Trumpet",         "8"),
    ("Stop: Acc2T: Clarinet 8",                    2508, "Clarinet",              "8"),
    ("Stop: Acc2T: Diaph Diapason 8",              2504, "Diaphonic Diapason",    "8"),
    ("Stop: Acc2T: English Horn 8",                2501, "English Horn",          "8"),
    ("Stop: Acc2T: Glockenspiel",                  2512, "Glockenspiel",          "8"),
    ("Stop: Acc2T: Open Diapason 8",               2505, "Open Diapason",         "8"),
    ("Stop: Acc2T: Tibia Clausa I 8",              2506, "Tibia Clausa (M)",      "8"),
    ("Stop: Acc2T: Tibia Pic I 4",                 2509, "Tibia Clausa (M)",      "4"),
    ("Stop: Acc2T: Tibia Clausa II 8",             2507, "Tibia Clausa (S)",      "8"),
    ("Stop: Acc2T: Tibia Piccolo II 4",            2510, "Tibia Clausa (S)",      "4"),
    ("Stop: Acc2T: Tuba Horn 8",                   2503, "Tuba Horn",             "8"),
    ("Stop: Acc2T: Xylophone",                     2511, "Xylophone",             "8"),
    ("Stop: Acc2T: Triangle",                      2513, "trap:Triangle",         None),
    ("Stop: Gt: Brass Trumpet 16",                 2202, "Brass Trumpet",         "16"),
    ("Stop: Gt: Brass Trumpet 8",                  2222, "Brass Trumpet",         "8"),
    ("Stop: Gt: Chrysoglott",                      2269, "Chrysoglott",           "8"),
    ("Stop: Gt: Clarinet 16",                      2209, "Clarinet",              "16"),
    ("Stop: Gt: Clarinet 8",                       2229, "Clarinet",              "8"),
    ("Stop: Gt: Bourdon 16",                       2218, "Concert Flute",         "16"),
    ("Stop: Gt: Fife 1",                           2263, "Concert Flute",         "1"),
    ("Stop: Gt: Flute 4",                          2252, "Concert Flute",         "4"),
    ("Stop: Gt: Flute 8",                          2239, "Concert Flute",         "8"),
    ("Stop: Gt: Flute Nazard 2 2/3",               2256, "Concert Flute",         "2 2/3"),
    ("Stop: Gt: Flute Piccolo 2",                  2260, "Concert Flute",         "2"),
    ("Stop: Gt: Diaph Diapason 8",                 2224, "Diaphonic Diapason",    "8"),
    ("Stop: Gt: Diaphone 16",                      2204, "Diaphonic Diapason",    "16"),
    ("Stop: Gt: Fifteenth 2",                      2259, "Diaphonic Diapason",    "2"),
    ("Stop: Gt: Octave 4",                         2244, "Diaphonic Diapason",    "4"),
    ("Stop: Gt: English Horn 16",                  2201, "English Horn",          "16"),
    ("Stop: Gt: English Horn 8",                   2221, "English Horn",          "8"),
    ("Stop: Gt: Flute Celeste 16",                 2283, "Flute Celeste",         "16"),
    ("Stop: Gt: Flute Celeste 2",                  2280, "Flute Celeste",         "2"),
    ("Stop: Gt: Flute Celeste 4",                  2279, "Flute Celeste",         "4"),
    ("Stop: Gt: Flute Celeste 8",                  2275, "Flute Celeste",         "8"),
    ("Stop: Gt: Gamba 16",                         2212, "Gamba",                 "16"),
    ("Stop: Gt: Gamba 8",                          2233, "Gamba",                 "8"),
    ("Stop: Gt: Gambette 4",                       2249, "Gamba",                 "4"),
    ("Stop: Gt: Gamba Celeste 16",                 2271, "Gamba Celeste",         "16"),
    ("Stop: Gt: Gamba Celeste 8",                  2273, "Gamba Celeste",         "8"),
    ("Stop: Gt: Gambette Celeste 4",               2277, "Gamba Celeste",         "4"),
    ("Stop: Gt: Glockenspiel",                     2268, "Glockenspiel",          "8"),
    ("Stop: Gt: Harp",                             2265, "Harp",                  "8"),
    ("Stop: Gt: Harp Sub",                         2264, "Harp",                  "16"),
    ("Stop: Gt: Horn Diapason 16",                 2206, "Horn Diapason",         "16"),
    ("Stop: Gt: Horn Diapason 8",                  2226, "Horn Diapason",         "8"),
    ("Stop: Gt: Octave Horn 4",                    2246, "Horn Diapason",         "4"),
    ("Stop: Gt: Kinura 8",                         2230, "Kinura",                "8"),
    ("Stop: Gt: Krumet 16",                        2215, "Krumet",                "16"),
    ("Stop: Gt: Krumet 8",                         2236, "Krumet",                "8"),
    ("Stop: Gt: Oboe Horn 16",                     2216, "Oboe Horn",             "16"),
    ("Stop: Gt: Oboe Horn 8",                      2237, "Oboe Horn",             "8"),
    ("Stop: Gt: Bass 16",                          2205, "Open Diapason",         "16"),
    ("Stop: Gt: Octave Open 4",                    2245, "Open Diapason",         "4"),
    ("Stop: Gt: Open Diapason 8",                  2225, "Open Diapason",         "8"),
    ("Stop: Gt: Orch Oboe 16",                     2210, "Orchestral Oboe",       "16"),
    ("Stop: Gt: Orch Oboe 8",                      2231, "Orchestral Oboe",       "8"),
    ("Stop: Gt: Quintadena 16",                    2217, "Quintadena",            "16"),
    ("Stop: Gt: Quintadena 8",                     2238, "Quintadena",            "8"),
    ("Stop: Gt: Saxophone (TC) 16",                2211, "Saxophone",             "16"),
    ("Stop: Gt: Saxophone 8",                      2232, "Saxophone",             "8"),
    ("Stop: Gt: Strings 16",                       2213, "Strings",               "16"),
    ("Stop: Gt: Strings 4",                        2250, "Strings",               "4"),
    ("Stop: Gt: Strings 8",                        2234, "Strings",               "8"),
    ("Stop: Gt: Tibia Tenth 3 1/5",                2253, "Tibia Clausa",          "3 1/5"),
    ("Stop: Gt: Tibia Tierce 1 3/5",               2261, "Tibia Clausa",          "1 3/5"),
    ("Stop: Gt: Tibia 12th I 2 2/3",               2254, "Tibia Clausa (M)",      "2 2/3"),
    ("Stop: Gt: Tibia Clausa I 16",                2207, "Tibia Clausa (M)",      "16"),
    ("Stop: Gt: Tibia Clausa I 8",                 2227, "Tibia Clausa (M)",      "8"),
    ("Stop: Gt: Tibia Piccolo I 2",                2257, "Tibia Clausa (M)",      "2"),
    ("Stop: Gt: Tibia Piccolo I 4",                2247, "Tibia Clausa (M)",      "4"),
    ("Stop: Gt: Tibia Quint I 5 1/3",              2242, "Tibia Clausa (M)",      "5 1/3"),
    ("Stop: Gt: Tibia 12th II 2 2/3",              2255, "Tibia Clausa (S)",      "2 2/3"),
    ("Stop: Gt: Tibia Clausa II 16",               2208, "Tibia Clausa (S)",      "16"),
    ("Stop: Gt: Tibia Clausa II 8",                2228, "Tibia Clausa (S)",      "8"),
    ("Stop: Gt: Tibia Fife II 1",                  2262, "Tibia Clausa (S)",      "1"),
    ("Stop: Gt: Tibia Piccolo II 2",               2258, "Tibia Clausa (S)",      "2"),
    ("Stop: Gt: Tibia Piccolo II 4",               2248, "Tibia Clausa (S)",      "4"),
    ("Stop: Gt: Tibia Quint II 5 1/3",             2243, "Tibia Clausa (S)",      "5 1/3"),
    ("Stop: Gt: Ophicleide 16",                    2203, "Tuba Horn",             "16"),
    ("Stop: Gt: Tuba Horn 8",                      2223, "Tuba Horn",             "8"),
    ("Stop: Gt: Contra Viol 16",                   2214, "VDO",                   "16"),
    ("Stop: Gt: Viol 4",                           2251, "VDO",                   "4"),
    ("Stop: Gt: Viol 8",                           2235, "VDO",                   "8"),
    ("Stop: Gt: Vibraphone",                       2270, "Vibraphone",            "8"),
    ("Stop: Gt: Contra Viol Celeste 16",           2272, "Viol Celeste",          "16"),
    ("Stop: Gt: Viol Celeste 4",                   2278, "Viol Celeste",          "4"),
    ("Stop: Gt: Viol Celeste 8",                   2274, "Viol Celeste",          "8"),
    ("Stop: Gt: Vox Humana I 16",                  2219, "Vox Humana (M)",        "16"),
    ("Stop: Gt: Vox Humana I 8",                   2240, "Vox Humana (M)",        "8"),
    ("Stop: Gt: Vox Humana II 16",                 2220, "Vox Humana (S)",        "16"),
    ("Stop: Gt: Vox Humana II 8",                  2241, "Vox Humana (S)",        "8"),
    ("Stop: Gt: Xylophone",                        2267, "Xylophone",             "8"),
    ("Stop: Gt: Xylophone Sub",                    2266, "Xylophone",             "16"),
    ("Stop: Ped: Brass Trumpet 8",                 2014, "Brass Trumpet",         "8"),
    ("Stop: Ped: Clarinet 16",                     2009, "Clarinet",              "16"),
    ("Stop: Ped: Clarinet 8",                      2021, "Clarinet",              "8"),
    ("Stop: Ped: Bourdon 16",                      2012, "Concert Flute",         "16"),
    ("Stop: Ped: Flute 8",                         2026, "Concert Flute",         "8"),
    ("Stop: Ped: Contra Diaphone 32",              2001, "Diaphonic Diapason",    "32"),
    ("Stop: Ped: Diaph Diap 8",                    2016, "Diaphonic Diapason",    "8"),
    ("Stop: Ped: Diaphone 16",                     2006, "Diaphonic Diapason",    "16"),
    ("Stop: Ped: English Horn 16",                 2004, "English Horn",          "16"),
    ("Stop: Ped: English Horn 8",                  2013, "English Horn",          "8"),
    ("Stop: Ped: Flute Celeste 16",                2037, "Flute Celeste",         "16"),
    ("Stop: Ped: Flute Celeste 8",                 2040, "Flute Celeste",         "8"),
    ("Stop: Ped: Gamba 16",                        2010, "Gamba",                 "16"),
    ("Stop: Ped: Gamba 8",                         2022, "Gamba",                 "8"),
    ("Stop: Ped: Gamba Celeste 16",                2035, "Gamba Celeste",         "16"),
    ("Stop: Ped: Gamba Celeste 8",                 2038, "Gamba Celeste",         "8"),
    ("Stop: Ped: Horn Diapason 16",                2041, "Horn Diapason",         "16"),
    ("Stop: Ped: Horn Diapason 8",                 2018, "Horn Diapason",         "8"),
    ("Stop: Ped: Oboe Horn 8",                     2025, "Oboe Horn",             "8"),
    ("Stop: Ped: Bass 16",                         2007, "Open Diapason",         "16"),
    ("Stop: Ped: Open Diapason 8",                 2017, "Open Diapason",         "8"),
    ("Stop: Ped: String Ensemble 8",               2023, "Strings",               "8"),
    ("Stop: Ped: Contra Tibia 32",                 2002, "Tibia Clausa",          "32"),
    ("Stop: Ped: Tibia Clausa I 16",               2008, "Tibia Clausa (M)",      "16"),
    ("Stop: Ped: Tibia Clausa I 8",                2019, "Tibia Clausa (M)",      "8"),
    ("Stop: Ped: Tibia Clausa II 8",               2020, "Tibia Clausa (S)",      "8"),
    ("Stop: Ped: Ophicleide 16",                   2005, "Tuba Horn",             "16"),
    ("Stop: Ped: Tuba Horn 8",                     2015, "Tuba Horn",             "8"),
    ("Stop: Ped: Contra Violone 32",               2003, "VDO",                   "32"),
    ("Stop: Ped: Viol 8",                          2024, "VDO",                   "8"),
    ("Stop: Ped: Violone 16",                      2011, "VDO",                   "16"),
    ("Stop: Ped: Viol Celeste 16",                 2036, "Viol Celeste",          "16"),
    ("Stop: Ped: Viol Celeste 8",                  2039, "Viol Celeste",          "8"),
    ("Stop: Ped:Bass Drum ff",                     2027, "trap:Bass Drum ff",     None),
    ("Stop: Ped: Crash Cymbal",                    2030, "trap:Crash Cymbal",     None),
    ("Stop: Ped: Cymbal Roll",                     2042, "trap:Cymbal Roll",      None),
    ("Stop: Ped: Hi Hat Open",                     2031, "trap:Hi Hat Open",      None),
    ("Stop: Ped: Kettle Drum",                     2028, "trap:Kettle Drum",      None),
    ("Stop: Ped: Ride Cymbal",                     2033, "trap:Ride Cymbal",      None),
    ("Stop: Ped: Snare Drum",                      2029, "trap:Snare Drum",       None),
    ("Stop: Ped: Tap Cymbal",                      2032, "trap:Tap Cymbal",       None),
    ("Stop: Ped: Triangle",                        2034, "trap:Triangle",         None),
    ("Stop: Solo: Brass Trumpet 16",               2302, "Brass Trumpet",         "16"),
    ("Stop: Solo: Brass Trumpet 8",                2313, "Brass Trumpet",         "8"),
    ("Stop: Solo: Cathedral Chimes",               2349, "Cathedral Chimes",      "8"),
    ("Stop: Solo: Chrysoglott",                    2351, "Chrysoglott",           "8"),
    ("Stop: Solo: Chrysoglott Sub",                2350, "Chrysoglott",           "16"),
    ("Stop: Solo: Clarinet 16",                    2307, "Clarinet",              "16"),
    ("Stop: Solo: Clarinet 8",                     2320, "Clarinet",              "8"),
    ("Stop: Solo: Flute 8",                        2330, "Concert Flute",         "8"),
    ("Stop: Solo: Diaphone 16",                    2304, "Diaphonic Diapason",    "16"),
    ("Stop: Solo: Diaphonic Diapason 8",           2315, "Diaphonic Diapason",    "8"),
    ("Stop: Solo: Octave 4",                       2333, "Diaphonic Diapason",    "4"),
    ("Stop: Solo: English Horn 16",                2301, "English Horn",          "16"),
    ("Stop: Solo: English Horn 8",                 2312, "English Horn",          "8"),
    ("Stop: Solo: Flute Cel 8",                    2358, "Flute Celeste",         "8"),
    ("Stop: Solo: Gamba 8",                        2324, "Gamba",                 "8"),
    ("Stop: Solo: Gambette 4",                     2336, "Gamba",                 "4"),
    ("Stop: Solo: Gamba Celeste 8",                2356, "Gamba Celeste",         "8"),
    ("Stop: Solo: Gambette Celeste 4",             2359, "Gamba Celeste",         "4"),
    ("Stop: Solo: Glockenspiel",                   2353, "Glockenspiel",          "8"),
    ("Stop: Solo: Harp",                           2348, "Harp",                  "8"),
    ("Stop: Solo: Harp Sub",                       2347, "Harp",                  "16"),
    ("Stop: Solo: Horn Diapason 8",                2317, "Horn Diapason",         "8"),
    ("Stop: Solo: Kinura 8",                       2321, "Kinura",                "8"),
    ("Stop: Solo: Krumet (TC) 16",                 2309, "Krumet",                "16"),
    ("Stop: Solo: Krumet 8",                       2327, "Krumet",                "8"),
    ("Stop: Solo: Oboe Horn 8",                    2328, "Oboe Horn",             "8"),
    ("Stop: Solo: Open Diapason 8",                2316, "Open Diapason",         "8"),
    ("Stop: Solo: Orch Oboe 8",                    2322, "Orchestral Oboe",       "8"),
    ("Stop: Solo: Quintadena 8",                   2329, "Quintadena",            "8"),
    ("Stop: Solo: Saxophone (TC) 16",              2308, "Saxophone",             "16"),
    ("Stop: Solo: Saxophone 8",                    2323, "Saxophone",             "8"),
    ("Stop: Solo: Sleigh Bells",                   2355, "Sleigh Bells",          "8"),
    ("Stop: Solo: Strings 4",                      2337, "Strings",               "4"),
    ("Stop: Solo: Strings 8",                      2325, "Strings",               "8"),
    ("Stop: Solo: Tibia Fife 1",                   2346, "Tibia Clausa",          "1"),
    ("Stop: Solo: Tibia Larigot 1 1/3",            2345, "Tibia Clausa",          "1 1/3"),
    ("Stop: Solo: Tibia 12th I 2 2/3",             2339, "Tibia Clausa (M)",      "2 2/3"),
    ("Stop: Solo: Tibia Clausa I 16",              2305, "Tibia Clausa (M)",      "16"),
    ("Stop: Solo: Tibia Clausa I 8",               2318, "Tibia Clausa (M)",      "8"),
    ("Stop: Solo: Tibia Picc I 2",                 2341, "Tibia Clausa (M)",      "2"),
    ("Stop: Solo: Tibia Piccolo I 4",              2334, "Tibia Clausa (M)",      "4"),
    ("Stop: Solo: Tibia Trc I 1 3/5",              2343, "Tibia Clausa (M)",      "1 3/5"),
    ("Stop: Solo: Tib Piccolo II 2",               2342, "Tibia Clausa (S)",      "2"),
    ("Stop: Solo: Tibia 12th II 2 2/3",            2340, "Tibia Clausa (S)",      "2 2/3"),
    ("Stop: Solo: Tibia Clausa II 16",             2306, "Tibia Clausa (S)",      "16"),
    ("Stop: Solo: Tibia Clausa II 8",              2319, "Tibia Clausa (S)",      "8"),
    ("Stop: Solo: Tibia Piccolo II 4",             2335, "Tibia Clausa (S)",      "4"),
    ("Stop: Solo: Tibia Trc II 1 3/5",             2344, "Tibia Clausa (S)",      "1 3/5"),
    ("Stop: Solo: Ophicleide 16",                  2303, "Tuba Horn",             "16"),
    ("Stop: Solo: Tuba Horn 8",                    2314, "Tuba Horn",             "8"),
    ("Stop: Solo: Viol 4",                         2338, "VDO",                   "4"),
    ("Stop: Solo: Viol 8",                         2326, "VDO",                   "8"),
    ("Stop: Solo: Vibraphone",                     2354, "Vibraphone",            "8"),
    ("Stop: Solo: Viol Celeste 4",                 2360, "Viol Celeste",          "4"),
    ("Stop: Solo: Viol Celeste 8",                 2357, "Viol Celeste",          "8"),
    ("Stop: Solo: Vox Humana I 8",                 2331, "Vox Humana (M)",        "8"),
    ("Stop: Solo: Vox I 16",                       2310, "Vox Humana (M)",        "16"),
    ("Stop: Solo: Vox Humana II 8",                2332, "Vox Humana (S)",        "8"),
    ("Stop: Solo: Vox II 16",                      2311, "Vox Humana (S)",        "16"),
    ("Stop: Solo: Xylophone",                      2352, "Xylophone",             "8"),
]

# Every switch that has an NRPN: the stop tabs above plus couplers (not used),
# re-iterate, effects and tremulants.
SWITCHES = {name: nrpn for name, nrpn, _, _ in STOPS}
SWITCHES.update({
    "Coupler: Acc2T: Gt Octave To Acc":        1512,
    "Coupler: Acc2T: Solo to Acc":             1516,
    "Coupler: Acc: Oct to Acc":                1107,
    "Coupler: Acc: Solo to Acc":               1116,
    "Coupler: Gt: Octave":                     1212,
    "Coupler: Gt: Solo to Great":              1216,
    "Coupler: Gt: Solo to Great Sub":          1215,
    "Coupler: Gt: Sub Octave":                 1210,
    "Coupler: Gt: Unison Off":                 1211,
    "Coupler: Ped: Acc To Ped":                1006,
    "Coupler: Ped: Gt Octave To Ped":          1012,
    "Coupler: Ped: Solo To Ped":               1016,
    "Coupler: Solo: Gt to Solo":               1311,
    "Coupler: Solo: Gt2SoloOctave":            1312,
    "Coupler: Solo: GtToSoloSubOct":           1310,
    "Coupler: Solo: Octave":                   1317,
    "Coupler: Solo: Sub Oct":                  1315,
    "Coupler: Solo: Unison Off":               1316,
    "Re-It: Glockenspiel":                     2662,
    "Re-It: Harp":                             2660,
    "Re-It: Xylophone":                        2661,
    "Stop: Ahooga Horn":                       2610,
    "Stop: Bass Drum Roll":                    2625,
    "Stop: Bell Tree":                         2604,
    "Stop: Chinese Gong":                      2603,
    "Stop: Choke Cymbal":                      2606,
    "Stop: Crash":                             2601,
    "Stop: Crash Cymbal":                      2624,
    "Stop: Cymbal Roll I":                     2602,
    "Stop: Cymbal Roll II":                    2626,
    "Stop: Door Bell":                         2609,
    "Stop: Fire Bell":                         2608,
    "Stop: Grand Crash 1st touch":             2611,
    "Stop: Grand Crash 2nd touch":             2612,
    "Stop: Scrape Cymbal":                     2607,
    "Stop: Toe Stud - Ahooga Horn":            2622,
    "Stop: Toe Stud - Bass Drum Roll":         2620,
    "Stop: Toe Stud - Birds":                  2618,
    "Stop: Toe Stud - Cymbal":                 2615,
    "Stop: Toe Stud - Door Bell":              2616,
    "Stop: Toe Stud - Fire Bell":              2617,
    "Stop: Toe Stud - Siren":                  2621,
    "Stop: Toe Stud - Train Whistle":          2619,
    "Stop: Toe Stud - Triangle":               2614,
    "Stop: Train Whistle":                     2627,
    "Stop: Triangle":                          2605,
    "Tremulant: Clarinet":                     2652,
    "Tremulant: Main":                         2650,
    "Tremulant: Main Strings":                 2656,
    "Tremulant: Saxophone":                    2658,
    "Tremulant: Solo":                         2651,
    "Tremulant: Solo Strings":                 2657,
    "Tremulant: Tibia":                        2654,
    "Tremulant: Trumpet":                      2659,
    "Tremulant: Tuba/Dia":                     2653,
    "Tremulant: Vox":                          2655,
})

def stop_division(switch):
    m = re.match(r"Stop: ?(Ped|Acc2T|Acc|Gt|Solo):", switch)
    return m.group(1) if m else None

STOP_INDEX = {(stop_division(name), voice, FEET[ft] if ft else None): name
              for name, _, voice, ft in STOPS}

# ----------------------------------------------------------------------------- the mapping
AUTO = "auto"
AUTO_CHOICES = ("Gt", "Solo")           # tie goes to the first

# Devtronix keyboard -> Paramount keyboard.  None: no Paramount keyboard, the
# keys are dropped (and counted) along with anything registered on them.
KEYBOARDS = {
    "Pedal": "Ped",
    "Accomp": "Acc", "Accomp.": "Acc", "Accompaniment 1st Touch": "Acc",
    "Accomp 2T": "Acc2T", "Accomp. 2T": "Acc2T", "Accompaniment 2nd Touch": "Acc2T",
    "Great": "Gt", "Great 1st Touch": "Gt",
    "Solo": "Solo",
    "Bombarde": AUTO,
    "Echo": AUTO,                       # played as a manual on Jerry's Disc
    "Great 2T": None, "Great 2nd Touch": None, "Great 2T (Peterson)": None,
    "Great 2T (4 Manual)": None, "Bombarde 2T": None,
    "String (Floating)": None, "TEST KEYBOARD": None,
}

# Couplers played with the Paramount's own: (manual of the keys, manual of
# the coupled division, pitch offset) -> switch.  Same manual = its octave
# couplers, used only while that manual's unison is on.
NATIVE_COUPLERS = {
    ("Gt", "Gt", 12): "Coupler: Gt: Octave", ("Gt", "Gt", -12): "Coupler: Gt: Sub Octave",
    ("Solo", "Solo", 12): "Coupler: Solo: Octave", ("Solo", "Solo", -12): "Coupler: Solo: Sub Oct",
    ("Acc", "Acc", 12): "Coupler: Acc: Oct to Acc",
    ("Ped", "Acc", 0): "Coupler: Ped: Acc To Ped", ("Ped", "Solo", 0): "Coupler: Ped: Solo To Ped",
    ("Ped", "Gt", 12): "Coupler: Ped: Gt Octave To Ped",
    ("Gt", "Solo", 0): "Coupler: Gt: Solo to Great", ("Gt", "Solo", -12): "Coupler: Gt: Solo to Great Sub",
    ("Solo", "Gt", 0): "Coupler: Solo: Gt to Solo", ("Solo", "Gt", 12): "Coupler: Solo: Gt2SoloOctave",
    ("Solo", "Gt", -12): "Coupler: Solo: GtToSoloSubOct",
    ("Acc", "Solo", 0): "Coupler: Acc: Solo to Acc",
    ("Acc2T", "Solo", 0): "Coupler: Acc2T: Solo to Acc", ("Acc2T", "Gt", 12): "Coupler: Acc2T: Gt Octave To Acc",
}

# Devtronix rank -> Paramount voice.  "?" = stand-in, "@32" = fixed footage,
# "A|B" = A, else B where the manual has no A at that pitch, None = silent.
# Names are matched without regard to case or spacing.
RANKS = {
    # diapasons
    "Diaphonic Diapason": "Diaphonic Diapason",
    "Open Diapason": "Open Diapason",
    "Horn Diapason": "Horn Diapason",
    "Diapason Celeste": "Horn Diapason?",      # Horn Diapason Celeste has no MIDI stop
    "Voce Umana": "Horn Diapason?",            # a diapason celeste, 4' C up
    "Echo Principal": "Horn Diapason?",
    # tibias and flutes
    "Main Tibia Clausa": "Tibia Clausa (M)",
    "Tibia Clausa": "Tibia Clausa (M)",
    "Main Tibia Minor": "Tibia Clausa (M)?",
    "Lieblich Flute": "Tibia Clausa (M)?",     # the Main Tibia Minor of Jerry's Disc
    "Echo Tibia Clausa": "Tibia Clausa (M)?",
    "Echo Tibia": "Tibia Clausa (M)?",
    "Echo Lieblich Tibia": "Tibia Clausa (M)?",
    'Solo Tibia (15")': "Tibia Clausa (S)",
    "Tibia Clausa (Solo)": "Tibia Clausa (S)",
    'Solo Tibia Clausa (10")': "Tibia Clausa (S)?",
    "Tibia Minor": "Tibia Clausa (S)?",        # solo chamber on the Tour and New Console
    "Tibia (Unenclosed)": "Tibia Clausa (S)?",
    "Concert Flute": "Concert Flute",
    "Flute Celeste": "Flute Celeste",
    "Echo Spitzflute Chest II": "Concert Flute?",
    "Lieblich Gedeckt (String Organ)": "Concert Flute?",
    "Quintadena": "Quintadena",
    "Quintadena Celeste": "Quintadena?",
    # strings
    "Viol d' Orch": "VDO", "Viol D' Orchestra": "VDO", "Viol d'Orchestre": "VDO",
    "Viol Celeste": "Viol Celeste", "VDO Celeste": "Viol Celeste",
    "Echo String": "VDO?", "Echo String Main Chest": "VDO?",
    "Echo String Celeste": "Viol Celeste?",
    "Main String": "Gamba?",
    "Solo String": "Gamba?", "Solo String Celeste": "Gamba Celeste?",
    "Solo Salicional (MPM)": "Gamba?", "Solo Voix Celeste": "Gamba Celeste?",
    "Salicional": "Gamba?", "Salicional Celeste": "Gamba Celeste?",
    "Salicional (Solo)": "Gamba?", "Voix Celeste (Solo)": "Gamba Celeste?",
    "Viola Dolce (mpm)": "Gamba?", "Viola Dolce Celeste": "Gamba Celeste?",
    "Dulciana": "Strings?", "Dulciana Celeste": "Strings?", "Unda Maris": "Strings?",
    "Violin": "Strings?", "Violin Celeste": "Strings?",
    # the floating String Organ of the Tour Disc
    "Gamba (String Organ)": "Gamba", "Gamba Celeste (String Organ)": "Gamba Celeste",
    "Viola Pomposa (String Organ)": "Strings?", "Viola Pomposa Celeste (String Organ)": "Strings?",
    "Violin (String Organ)": "Strings?", "Violin Celeste (String Organ)": "Strings?",
    "Dulcet (String Organ)": "Strings?", "Dulcet Celeste (String Organ)": "Strings?",
    "Salicional (String Organ)": "Strings?", "Salicional Celeste (String Organ)": "Strings?",
    "Salicional (16' String Organ)": "Strings?",
    "Gemshorn (String Organ)": "Strings?", "Gemshorn Celeste (String Organ)": "Strings?",
    "Muted Viol (String Organ)": "Strings?", "Muted Viol Celeste (String Organ)": "Strings?",
    "Corno d' Amore (String Organ)": "Oboe Horn?",
    "Vox Humana mf (String Organ)": "Vox Humana (M)?", "Vox Humana p (String Organ)": "Vox Humana (M)?",
    # reeds
    "Tuba Horn": "Tuba Horn",
    "Tuba Mirabilis": "Tuba Horn?",
    "Brass Trumpet": "Brass Trumpet",
    "Chorus Trumpet": "Brass Trumpet?",
    "English Horn": "English Horn",
    "Clarinet": "Clarinet",
    "Brass Saxophone": "Saxophone",
    "Orchestral Oboe": "Orchestral Oboe",
    "Oboe Horn": "Oboe Horn",
    "Kinura": "Kinura",
    "Musette": "Krumet?",
    "French Horn": "Oboe Horn?",
    "Main Vox Humana": "Vox Humana (M)", "Vox Humana": "Vox Humana (M)",
    "Solo Vox Humana": "Vox Humana (S)", "Vox Humana (Solo)": "Vox Humana (S)",
    "Echo Vox (16')": "Vox Humana (M)?", "Echo Vox (8')": "Vox Humana (M)?",
    "Echo Vox (4')": "Vox Humana (M)?", "Echo Vox Celeste (8')": "Vox Humana (M)?",
    "Echo 16' Vox Humana": "Vox Humana (M)?", "Echo 8' Vox Humana": "Vox Humana (M)?",
    "Echo 4' Vox Humana": "Vox Humana (M)?", "Echo 8' Vox Humana Celeste": "Vox Humana (M)?",
    # mixtures: the Paramount has none; its Great Fifteenth instead
    "I Mixture": "Diaphonic Diapason? @2", "II Mixture": "Diaphonic Diapason? @2",
    "III Mixture": "Diaphonic Diapason? @2", "IV Mixture": "Diaphonic Diapason? @2",
    "Mixture IV": "Diaphonic Diapason? @2",
    "Great Mixture I": "Diaphonic Diapason? @2", "Great Mixture II": "Diaphonic Diapason? @2",
    "Great Mixture III": "Diaphonic Diapason? @2", "Great Mixture IV": "Diaphonic Diapason? @2",
    # pedal resultants
    "32' Resultant": "Tibia Clausa? @32", "32' Resultant (Lieb)": "Tibia Clausa? @32",
    "32' Resultant(Bourdon)": "Tibia Clausa? @32",
    "32' Pedal Bourdon I": "Tibia Clausa? @32", "32' Pedal Bourdon II": "Tibia Clausa? @32",
    "32' Pedal Bourdon III": "Tibia Clausa? @32", "32' Pedal Bourdon IV": "Tibia Clausa? @32",
    "32' Soft Bourdon I": "Tibia Clausa? @32", "32' Soft Bourdon II": "Tibia Clausa? @32",
    "Bombarde I": "Diaphonic Diapason? @32", "Bombarde II": "Diaphonic Diapason? @32",
    "Bombarde III": "Diaphonic Diapason? @32", "Bombarde IV": "Diaphonic Diapason? @32",
    "Bombarde V": "Diaphonic Diapason? @32", "Bombarde VI": "Diaphonic Diapason? @32",
    "Bombarde VII": "Diaphonic Diapason? @32",
    # tuned percussion
    "Chrysoglott": "Chrysoglott",
    "Glockenspiel": "Glockenspiel", 'Glockenspiel (15")': "Glockenspiel",
    "Glockenspiel (regular)": "Glockenspiel", "Glockenspiel (Perc.)": "Glockenspiel",
    "Glockenspiel (solo)": "Glockenspiel",
    "Glockenspiel Celeste": "Glockenspiel?", "Glockenspiel (Celeste A-435)": "Glockenspiel?",
    "Xylophone": "Xylophone", "Xylophone (SS)": "Xylophone", "Master Xylophone": "Xylophone",
    "Xylophone (Reit)": "Xylophone", "Xylophone Reiterate": "Xylophone",
    "Harp": "Harp", "Marimba / Harp": "Harp", "Marimba/Harp": "Harp",
    "Vibraharp": "Vibraphone",
    "Cathedral Chimes": "Cathedral Chimes", "Chimes": "Cathedral Chimes",
    "Sleigh Bells": "Sleigh Bells",
    "Tuned Birds": None, "Tuned Bird Whistles": None,      # the Paramount's birds are an untuned effect
    # pianos: the Paramount's piano stops are sys-ex only
    "Piano": None, "Midi 1 & 2 Piano (Bosendorfer)": None, "Midi 9 - Chamber Piano": None,
    # MIDI sound-module voices
    "Midi 1 - Str. Bass": "Strings?|VDO?", "Midi 7 - String Bass": "Strings?|VDO?",
    "Midi 16 - Pedal Double Bases": "Strings?|VDO?", "Midi Double Basses": "Strings?|VDO?",
    "Midi 2 - Bowed Strings": "Strings?", "Midi 8 - Arco Strings": "Strings?",
    "Midi 13 - Str. Tremolo": "Strings?", "Midi 14 - Pizz. Strings": "Strings?",
    "Midi 3 - Harp": "Harp?", "Midi 3 - Orchestral Harp": "Harp?",
    "Midi 4 - Tympani": "trap:Kettle Drum?",
    "Midi 5 - Mute Trumpets": "Brass Trumpet?",
    "Midi 6 - English Horn": "English Horn?",
    "Midi 12 - Solo Flute": "Concert Flute?",
    "Midi 15 - Trombone/vib.": "Tuba Horn?",
}

# Ranks that also turn on a Paramount re-iterate switch while they sound.  A
# Devtronix reiterate modifier on a rank does the same.
REITERATE = {"Harp": "Re-It: Harp", "Xylophone": "Re-It: Xylophone", "Glockenspiel": "Re-It: Glockenspiel"}
REITERATING_RANKS = {"Xylophone (Reit)", "Xylophone Reiterate"}

# When a manual has no tab for a voice at the pitch asked for.
NEAR = {
    "Tibia Clausa (M)": ["Tibia Clausa (S)"], "Tibia Clausa (S)": ["Tibia Clausa (M)"],
    "Vox Humana (M)": ["Vox Humana (S)"], "Vox Humana (S)": ["Vox Humana (M)"],
    "Diaphonic Diapason": ["Open Diapason", "Horn Diapason"],
    "Open Diapason": ["Diaphonic Diapason", "Horn Diapason"],
    "Horn Diapason": ["Open Diapason", "Diaphonic Diapason"],
    "Concert Flute": ["Tibia Clausa"],
    "Flute Celeste": ["Concert Flute"], "Viol Celeste": ["VDO"], "Gamba Celeste": ["Gamba"],
    "VDO": ["Strings", "Gamba"], "Gamba": ["Strings", "VDO"], "Strings": ["Gamba", "VDO"],
    "Kinura": ["Krumet"], "Krumet": ["Kinura"],
}

# Trap units struck from a division's keys -> Paramount trap tabs, first one
# the manual has.
TRAPS = {
    "Snare Drum": ["Snare Drum", "Snare Drum Roll"],
    "Tap Cymbal": ["Tap Cymbal"], "Exposed Tap Cymbal": ["Tap Cymbal"], "Unenclosed Tap Cymbal": ["Tap Cymbal"],
    "Crash Cymbal": ["Crash Cymbal"], "Exposed Crash Cymbal": ["Crash Cymbal"],
    "Unenclosed Crash Cymbal": ["Crash Cymbal"],
    "Brush Cymbal": ["Ride Cymbal"], "Exposed Brush Cymbal": ["Ride Cymbal"],
    "Roll Cymbal 1": ["Cymbal Roll"],
    "Bass Drum": ["Bass Drum ff"],
    "Kettle Drum": ["Kettle Drum"], "Tympani": ["Kettle Drum"],
    "Wood Block": ["Chinese Block"], "Chinese Block": ["Chinese Block"],
    "Castanets": ["Castanets"], "Tambourine": ["Tambourine"], "Tamborine": ["Tambourine"],
    "Tom Tom": ["Tom Tom"], "Tom-Tom": ["Tom Tom"], "Triangle": ["Triangle"],
    "Snare Control On": None, "": None,             # relay controls, not sounds
}

# Units switched on directly (toe studs, effects) -> Paramount effect switches.
EFFECTS = {
    "Ahooga Horn": "Stop: Ahooga Horn", "Siren": "Stop: Toe Stud - Siren",
    "Door Bell": "Stop: Door Bell", "Fire Gong": "Stop: Fire Bell",
    "Train Bell": "Stop: Fire Bell", "Train Bell 1": "Stop: Fire Bell", "Train Bell 2": "Stop: Fire Bell",
    "Crossing Bell": "Stop: Fire Bell", "Exposed Train Crossing Bell": "Stop: Fire Bell",
    "Train Whistle 1": "Stop: Train Whistle", "Train Whistle 2": "Stop: Train Whistle",
    "Train Whistle 3": "Stop: Train Whistle", "Steam Whistle 1": "Stop: Train Whistle",
    "Steam Whistle 2": "Stop: Train Whistle", "Steam Whistle 3": "Stop: Train Whistle",
    "Boat Whistle": "Stop: Train Whistle", "Bird Whistle": "Stop: Toe Stud - Birds",
    "Gong": "Stop: Chinese Gong", "Chinese Gong": "Stop: Chinese Gong",
    "Crash Cymbal": "Stop: Crash Cymbal", "Exposed Crash Cymbal": "Stop: Crash Cymbal",
    "Unenclosed Crash Cymbal": "Stop: Crash Cymbal", "Roll Cymbal 1": "Stop: Cymbal Roll I",
    "Triangle": "Stop: Triangle", "Wind Chimes": "Stop: Bell Tree",
}

# Tremulant units (name contains "trem"): the first pattern that matches the
# name picks the Paramount tremulants.  "string" goes by the unit's chamber.
TREMULANTS = [
    (r"tibia|lieblich", ["Tremulant: Tibia"]),
    (r"vox", ["Tremulant: Vox"]),
    (r"sax", ["Tremulant: Saxophone"]),
    (r"trumpet", ["Tremulant: Trumpet"]),
    (r"clarinet", ["Tremulant: Clarinet"]),
    (r"string", "strings"),
    (r"tuba|diapason|principal", ["Tremulant: Tuba/Dia"]),
    (r"^main|french horn", ["Tremulant: Main"]),
    (r"^solo", ["Tremulant: Solo"]),
    (r"^echo", ["Tremulant: Main"]),
]
STRING_TREMULANTS = {"main": ["Tremulant: Main Strings"], "echo": ["Tremulant: Main Strings"],
                     "solo": ["Tremulant: Solo Strings"]}
# A Paramount tremulant that no tremulant of the definition maps to follows this one.
TREMULANT_FOLLOWS = {
    "Tremulant: Clarinet": "Tremulant: Main", "Tremulant: Tuba/Dia": "Tremulant: Main",
    "Tremulant: Main Strings": "Tremulant: Main",
    "Tremulant: Saxophone": "Tremulant: Solo", "Tremulant: Trumpet": "Tremulant: Solo",
    "Tremulant: Solo Strings": "Tremulant: Solo",
    "Tremulant: Tibia": "Tremulant: Main", "Tremulant: Vox": "Tremulant: Main",
}

def norm(name):
    return " ".join(name.lower().replace("’", "'").split())

def parse_voice(spec):
    """'Tibia Clausa? @32' -> [(voice, fixed pitch or None, stand-in?)]"""
    out = []
    for part in spec.split("|"):
        part = part.strip()
        fixed = None
        if "@" in part:
            part, ft = part.split("@")
            fixed = FEET[ft.strip()]
        part = part.strip()
        guess = part.endswith("?")
        out.append((part.rstrip("?"), fixed, guess))
    return out

RANK_SPECS = {norm(k): (parse_voice(v) if v else None) for k, v in RANKS.items()}
KEYBOARD_SPECS = {norm(k): v for k, v in KEYBOARDS.items()}
TRAP_SPECS = {norm(k): v for k, v in TRAPS.items()}
EFFECT_SPECS = {norm(k): v for k, v in EFFECTS.items()}

# ----------------------------------------------------------------------------- console
class Console:
    """The Paramount switches and swells wanted for the state of a
    dev2midi.Organ, with a tally of how each registered rank was matched.

    assign: Devtronix keyboard number -> Paramount keyboard (AUTO resolved
    by choose()), or None."""

    def __init__(self, organ, assign=None):
        self.o = organ
        d = organ.d
        self.d = d
        self.kbd_names = {k.number: k.name for k in d.lists.get("Kbd", [])}
        self.assign = dict(assign) if assign is not None else keyboard_assignment(d)
        self.rank_names = {r.number: r.name for r in d.lists.get("Rnk", [])}
        self.units = organ.units
        self.trem_units = {}
        for u in self.units.values():
            if re.search(r"trem|temolo", u.name, re.I):
                self.trem_units[u.number] = self._trem_targets(u)
        mapped = {s for ts in self.trem_units.values() for s in ts}
        self.trem_follow = {p: f for p, f in TREMULANT_FOLLOWS.items() if p not in mapped}
        chambers = set(organ.shade_units)
        self.swell_source = {ch: ch for ch in SWELLS if ch in chambers}
        if "percussion" not in chambers and "solo" in chambers:
            self.swell_source["percussion"] = "solo"
        self.cache = {}
        self.tally = {}                     # (status, kbd, rank, feet, switch) -> key-ons
        self.dirty = True
        self._requests = {}

    def _trem_targets(self, u):
        name = u.name.lower()
        for rx, targets in TREMULANTS:
            if re.search(rx, name):
                if targets == "strings":
                    ch = self.o.chamber_of(u.name)
                    return STRING_TREMULANTS.get(ch, STRING_TREMULANTS["main"] + STRING_TREMULANTS["solo"])
                return targets
        return []

    # -- relay state
    def couplers(self):
        out, unison_off = [], set()
        for n in self.o.active:
            f = self.o.fncs.get(n)
            if f is None:
                continue
            if f.type == 1:
                out.append(f)
            elif f.type == 6:
                unison_off.add(f.w(2))
        return out, unison_off

    def reach(self, kbd):
        """({(division, pitch offset)} that the keys of keyboard kbd sound on,
        [Paramount couplers that play the rest])."""
        couplers, unison_off = self.couplers()
        here = self.assign.get(kbd)
        native = {}
        for c in couplers:
            if c.w(2) != kbd or c.b(12):
                continue
            div = c.w(4)
            if div == kbd:
                s = None if kbd in unison_off else NATIVE_COUPLERS.get((here, here, c.s(6)))
            else:
                there = self.assign.get(div)
                s = NATIVE_COUPLERS.get((here, there, c.s(6))) if there != here else None
            if s:
                native[id(c)] = s
        out = set() if kbd in unison_off else {(kbd, 0)}
        out |= {(c.w(4), c.s(6)) for c in couplers
                if c.w(2) == kbd and not c.b(12) and id(c) not in native}
        todo = list(out)
        while todo:                           # couplers that couple the couplers
            div, off = todo.pop()
            for c in couplers:
                if c.b(12) and c.w(2) == div:
                    nxt = (c.w(4), off + c.s(6))
                    if nxt not in out and abs(nxt[1]) <= 36:
                        out.add(nxt); todo.append(nxt)
        return out, sorted(set(native.values()))

    def requests(self, kbd):
        """What keyboard kbd registers: [("rank", rank number, pitch, reiterate?) or
        ("trap", unit number, None, False)], cached until the registration changes."""
        if self.dirty:
            self._requests = {}
            self.dirty = False
        if kbd in self._requests:
            return self._requests[kbd]
        by_div = self._by_div()
        out = []
        reach, native = self.reach(kbd)
        for div, off in sorted(reach):
            for f, mod in by_div.get(div, ()):
                if f.type == 3:
                    out.append(("rank", f.w(4), f.s(6) + off, mod is not None and mod.type == 14))
                elif f.type == 4:
                    out.append(("trap", f.w(4), None, False))
        out += [("coupler", s, None, False) for s in native]
        self._requests[kbd] = out
        return out

    def _by_div(self):
        if "_by_div" not in self._requests:
            by = {}
            for f, mod in self.o.rank_functions():
                by.setdefault(f.w(2), []).append((f, mod))
            for n in self.o.active:
                f = self.o.fncs.get(n)
                if f is not None and f.type == 4 and f.w(4):
                    by.setdefault(f.w(2), []).append((f, None))
            self._requests["_by_div"] = by
        return self._requests["_by_div"]

    def changed(self):
        self.dirty = True

    # -- matching
    def resolve(self, div, req):
        """(switch or None, status); status is exact, stand-in, near, missing,
        silent (the table says so) or unknown (not in the table)."""
        key = (div, req[0], req[1], req[2])
        if key in self.cache:
            return self.cache[key]
        kind, what, pitch, _ = req
        if kind == "coupler":
            res = (what, "exact")
        elif kind == "trap":
            u = self.units.get(what)
            voices = TRAP_SPECS.get(norm(u.name), "unknown") if u else "unknown"
            if voices == "unknown":
                res = (None, "unknown")
            elif voices is None:
                res = (None, "silent")
            else:
                res = (None, "missing")
                for v in voices:
                    s = STOP_INDEX.get((div, "trap:" + v, None))
                    if s:
                        res = (s, "exact"); break
        else:
            spec = RANK_SPECS.get(norm(self.rank_names.get(what, "")), "unknown")
            if spec == "unknown":
                res = (None, "unknown")
            elif spec is None:
                res = (None, "silent")
            else:
                res = (None, "missing")
                for voice, fixed, guess in spec:
                    p = None if voice.startswith("trap:") else (fixed if fixed is not None else pitch)
                    s = self._tab(div, voice, p)
                    if s:
                        res = (s, "stand-in" if guess else "exact"); break
                else:
                    voice, fixed, _ = spec[0]
                    p = fixed if fixed is not None else pitch
                    for alt in NEAR.get(voice, ()):
                        s = self._tab(div, alt, p)
                        if s:
                            res = (s, "near"); break
        self.cache[key] = res
        return res

    @staticmethod
    def _tab(div, voice, pitch):
        s = STOP_INDEX.get((div, voice, pitch))
        if s is None and voice.startswith("Tibia Clausa ("):
            s = STOP_INDEX.get((div, "Tibia Clausa", pitch))
        return s

    def choose(self, seen):
        """Paramount manual for an AUTO keyboard, from the requests it made."""
        best, score = AUTO_CHOICES[0], -1
        for div in AUTO_CHOICES:
            n = sum(1 for r in seen if self.resolve(div, r)[1] in ("exact", "stand-in"))
            if n > score:
                best, score = div, n
        return best

    # -- output
    def switches(self):
        """Paramount switches that should be on now."""
        on = set()
        for kbd, div in self.assign.items():
            if div is None:
                continue
            for req in self.requests(kbd):
                s, _ = self.resolve(div, req)
                if s:
                    on.add(s)
                    if req[0] == "rank":
                        voice = STOP_VOICE.get(s)
                        if voice in REITERATE and (req[3] or self.rank_names.get(req[1]) in REITERATING_RANKS):
                            on.add(REITERATE[voice])
        direct = self.direct_units()
        for u in direct:
            on.update(self.trem_units.get(u, ()))
            unit = self.units.get(u)
            e = unit and EFFECT_SPECS.get(norm(unit.name))
            if e:
                on.add(e)
        for target, source in self.trem_follow.items():
            if source in on:
                on.add(target)
        return on

    def direct_units(self):
        return {self.o.fncs[n].w(2) for n in self.o.active
                if n in self.o.fncs and self.o.fncs[n].type == 5 and self.o.fncs[n].w(2)}

    def swells(self):
        """{(channel, controller): value} for the Paramount swell pedals."""
        levels = self.o.shade_levels(self.direct_units())
        out = {}
        for ch, (chan, ctl) in SWELLS.items():
            src = self.swell_source.get(ch)
            out[(chan, ctl)] = int(round(127 * levels.get(src, 0))) if src else 127
        return out

    def count_key(self, kbd):
        """Tally what a key-on on keyboard kbd sounds through."""
        div = self.assign.get(kbd)
        for req in self.requests(kbd):
            s, status = self.resolve(div, req) if div else (None, "no keyboard")
            if req[0] == "rank":
                name, ft = self.rank_names.get(req[1], f"rank {req[1]}"), feet(req[2])
            elif req[0] == "trap":
                u = self.units.get(req[1]); name, ft = (u.name if u else f"unit {req[1]}"), ""
            else:
                name, ft = req[1], ""
            k = (status, self.kbd_names.get(kbd, str(kbd)), name.strip(), ft, s)
            self.tally[k] = self.tally.get(k, 0) + 1

STOP_VOICE = {name: voice for name, _, voice, _ in STOPS}

def fits(d):
    """True for a definition whose keyboards all appear in KEYBOARDS (the
    theatre-organ definitions of Jerry's Disc, the Tour Disc and New Console)."""
    kbds = d.lists.get("Kbd", [])
    return bool(kbds) and all(norm(k.name) in KEYBOARD_SPECS for k in kbds)

def keyboard_assignment(d):
    """Devtronix keyboard number -> Paramount keyboard, AUTO or None."""
    return {k.number: KEYBOARD_SPECS.get(norm(k.name)) for k in d.lists.get("Kbd", [])}
