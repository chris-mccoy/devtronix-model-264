# Paramount 332 mapping: draft for review

`dev2midi.py --paramount` turns a Devtronix track into a MIDI file for Hauptwerk's MIDI
player with the Paramount 332 loaded. The tables that decide which Paramount stop plays
each of the old organ's ranks are in [`system-monitor/paramount332.py`](../system-monitor/paramount332.py).
This page shows how those tables come out over every track on the three theatre-organ
disks (Jerry's Disc, the 1995 Tour Disc, New Console), so they can be checked before any
renders are made for listening.

"Key presses" weights each rank by how often a key was pressed while it was registered,
summed over all tracks, so it shows what is actually heard. Disks: J = Jerry's Disc,
T = Tour Disc, N = New Console.

| Disk | Exact | Stand-in | Near | Not sounded |
|---|---:|---:|---:|---:|
| Jerry's Disc | 65% | 31% | 1% | 3% |
| Tour Disc | 53% | 43% | 0% | 3% |
| New Console | 52% | 41% | 2% | 5% |

- **Exact**: the Paramount has that rank at that pitch on that manual.
- **Stand-in**: the Paramount lacks the rank, so the closest voice is used (marked `?` in `RANKS`).
- **Near**: the rank exists, but not at that pitch on that manual, so a close relative is used
  (the other tibia, another diapason).
- **Not sounded**: no tab at that pitch, or the piano (see question 3).

## Questions

1. **Stand-ins.** Rows marked *stand-in* in [Ranks](#ranks) are my picks. The most-played are:
   Dulciana / Unda Maris / Violin → Strings (8 rks); Salicional, Voix Celeste, Viola Dolce,
   Solo String, Main String → Gamba / Gamba Celeste; Lieblich Flute and Main Tibia Minor →
   Tibia I; Tibia Minor (Tour, New Console) and Solo Tibia 10" → Tibia II; Voce Umana,
   Diapason Celeste, Echo Principal → Horn Diapason; French Horn → Oboe Horn;
   Musette → Krumet; Echo ranks → Main-chamber equivalents; Great mixtures → Great Fifteenth 2';
   32' resultants and bourdons → Contra Tibia 32'; pedal Bombarde I–VII → Contra Diaphone 32'.
2. **Great VDO 2'** is the most-played pitch with no Paramount tab (about 20,000 key presses
   on all three disks). The Great also lacks Tuba 4' and the diapason mutations (2 2/3', 1 1/3', 1'),
   and the Accompaniment has no 4' Harp. Leave them silent, or play them on another 2'/4' tab?
3. **Pianos.** The Paramount's piano stops can only be switched by sys-ex, and the XML does not
   give the sys-ex format. The Tour Disc's Bösendorfer (Piano Roll Blues, Tiger Rag, the Demos)
   is silent for now, about 8,900 key presses. If you can find the sys-ex layout in the Hauptwerk
   user guide ("MIDI recorder/player fixed, predefined MIDI implementation"), I can add them.
   Otherwise the piano stops have to be set by hand.
4. **Echo manual.** Jerry's Disc has an Echo keyboard that is actually played (T1, T2, T11).
   I applied your Bombarde rule to it, so it goes to the Great on all three tracks.
5. **Paramount tabs read from their names.** I took "Bass 16" (Pedal, Great) as the Open Diapason;
   "Octave 4" as the Diaphonic Diapason (the Great also has "Octave Open 4"); "Violone 16" and
   "Contra Violone 32" as the VDO; and "Acc: Oct to Acc" as the Accompaniment octave coupler.
   Tibia tabs with no I/II (Acc 12th and Piccolo 2', Great Tenth and Tierce, Solo Larigot and Fife,
   Contra Tibia 32') serve either tibia. Hovering over them in Hauptwerk would confirm.
6. **Tremulants.** Dad's tremulants are matched by name (Tibia, Vox, Saxophone, Trumpet, Clarinet,
   Strings, Tuba/Diapason), and his plain Main and Solo tremulants go to the Paramount's Main and Solo.
   Paramount tremulants with no counterpart follow Main (Clarinet, Tuba/Dia, Main Strings, Tibia, Vox)
   or Solo (Saxophone, Trumpet, Solo Strings). In practice they are all on or off together.
7. **Swells.** Main shades drive the Paramount MAIN pedal and Solo shades drive SOLO. The Tour Disc's
   percussion shades drive PERCUSSIONS; on the other two disks PERCUSSIONS follows Solo. Echo and
   String Organ shades are not used.

## How it works

- **Keys** play the Paramount manual of the keyboard they were played on: Pedal, Accompaniment
  (2nd touch on its own channel), Great, Solo. The **Bombarde** goes to whichever of Great or Solo
  has exact tabs for more of what the track registers on it, with ties going to the Great.
  That came out as the Great on every track.
- **Registration** comes from the old relay's own logic (stops → links → functions), so pistons,
  general tabs and "String Celeste Off" behave as they did on the organ. Every rank that would sound
  becomes a Paramount stop tab on the manual the keys come from.
- **Couplers** use the Paramount's own coupler where it has the same one (Accomp to Pedal,
  Solo to Great, Great/Solo octave and sub octave, ...). That keeps the top octave, and it covers
  pitches the receiving manual has no tab for. Other couplers are folded into the registration;
  for example, "Echo To Great" puts the Echo ranks on Great tabs.
- **Second touch** on the Great and Bombarde has no Paramount keyboard. Nothing was registered on
  them in any track, so dropping their keys loses no sound.
- The file starts by switching every Paramount stop, coupler and tremulant off, so whatever was
  drawn in Hauptwerk beforehand does not leak in.
- **Not tested in Hauptwerk yet**: the stop messages follow the XML (NRPN on channel 2, CC 99/98
  number, CC 6 value 127/0), but the first real check is loading a file in Hauptwerk.

## Per track

| Disk | Track | Exact | Stand-in | Near | Not sounded | Bombarde / Echo |
|---|---|---:|---:|---:|---:|---|
| Jerry's Disc | T1 Stairway | 49% | 51% | 0% | 0% | Bombarde → Great, Echo → Great |
| Jerry's Disc | T2 Walking My Baby | 59% | 32% | 3% | 6% | Bombarde → Great, Echo → Great |
| Jerry's Disc | T3 Rigadon | 73% | 21% | 1% | 5% | Bombarde → Great |
| Jerry's Disc | T4 There's No Business | 67% | 30% | 0% | 3% | Bombarde → Great |
| Jerry's Disc | T5 It's Beginnin To Look Alo | 63% | 35% | 0% | 2% | Bombarde → Great |
| Jerry's Disc | T6 Sleigh Ride | 72% | 24% | 1% | 3% |  |
| Jerry's Disc | T7 Joy To The World | 75% | 19% | 1% | 6% |  |
| Jerry's Disc | T8 Danny Boy | 56% | 44% | 0% | 0% |  |
| Jerry's Disc | T9 Stars And Stripes Forever | 70% | 26% | 0% | 3% |  |
| Jerry's Disc | T10 Get Me To The Church | 60% | 35% | 1% | 3% | Bombarde → Great |
| Jerry's Disc | T11 T.H. Clowns | 65% | 33% | 2% | 0% | Bombarde → Great, Echo → Great |
| Jerry's Disc | T13 Easter Parade | 60% | 38% | 1% | 1% | Bombarde → Great |
| Tour Disc | T1 Stairway To The Stars | 57% | 41% | 0% | 2% | Bombarde → Great |
| Tour Disc | T2 Old Piano Roll Blues | 52% | 43% | 0% | 4% | Bombarde → Great |
| Tour Disc | T3 Memory | 58% | 40% | 0% | 2% | Bombarde → Great |
| Tour Disc | T4 Aba Daba Honeymoon DRAPES | 50% | 48% | 0% | 3% | Bombarde → Great |
| Tour Disc | T5 Exit-Walking My Baby Back | 50% | 47% | 0% | 2% | Bombarde → Great |
| Tour Disc | T6 Demo | 55% | 20% | 0% | 25% | Bombarde → Great |
| Tour Disc | T7 Piano Roll Blues | 54% | 42% | 0% | 4% | Bombarde → Great |
| Tour Disc | T8 Memory | 50% | 48% | 0% | 2% | Bombarde → Great |
| Tour Disc | T9 Tiger Rag | 54% | 41% | 0% | 5% | Bombarde → Great |
| Tour Disc | T10 Washington Post March | 53% | 45% | 0% | 2% | Bombarde → Great |
| Tour Disc | T11 Demo | 60% | 16% | 0% | 24% | Bombarde → Great |
| Tour Disc | T13 Memeory | 52% | 46% | 0% | 2% | Bombarde → Great |
| Tour Disc | T14 Tiger Rag | 54% | 42% | 0% | 4% | Bombarde → Great |
| Tour Disc | T15 Washington Post March | 57% | 41% | 0% | 2% | Bombarde → Great |
| New Console | T1 STAIRWAY P(1,2) | 57% | 41% | 2% | 0% | Bombarde → Great |
| New Console | T2 PLAY WITH T1 P(1,2) | 58% | 42% | 0% | 0% | Bombarde → Great |
| New Console | T3 OLD PIANO ROLL BLUES | 59% | 36% | 0% | 4% | Bombarde → Great |
| New Console | T4 WALKING MY BABY | 56% | 41% | 2% | 1% | Bombarde → Great |
| New Console | T5 MY SIN | 55% | 43% | 1% | 1% |  |
| New Console | T6 ROMANZA | 45% | 54% | 1% | 0% | Bombarde → Great |
| New Console | T7 You Are Love - demo | 50% | 46% | 3% | 1% | Bombarde → Great |
| New Console | T8 Russian Lullaby | 55% | 44% | 2% | 0% | Bombarde → Great |
| New Console | T9 Toccata & Fugue | 50% | 33% | 2% | 15% | Bombarde → Great |
| New Console | T10 Dance Of The Blue Danube | 51% | 47% | 1% | 1% | Bombarde → Great |
| New Console | T12 Nevertheless | 47% | 51% | 1% | 1% | Bombarde → Great |

## Ranks

"Not sounded" counts key presses on pitches the manual has no tab for (see the next table), and the silent pianos.

| Dad's rank | Paramount voice | Match | Key presses | Not sounded | Disks |
|---|---|---|---:|---:|---|
| Dulciana | Strings | stand-in | 66,976 | 0 | JNT |
| Solo String | Gamba | stand-in | 41,036 | 802 | NT |
| Unda Maris | Strings | stand-in | 35,082 | 0 | J |
| Dulciana Celeste | Strings | stand-in | 34,624 | 0 | NT |
| Violin | Strings | stand-in | 31,663 | 4,640 | NT |
| Salicional | Gamba | stand-in | 30,674 | 856 | N |
| Viola Dolce Celeste | Gamba Celeste | stand-in | 30,650 | 0 | T |
| Viola Dolce (mpm) | Gamba | stand-in | 26,614 | 0 | T |
| Voix Celeste (Solo) | Gamba Celeste | stand-in | 25,994 | 0 | T |
| Violin Celeste | Strings | stand-in | 23,220 | 0 | NT |
| Solo String Celeste | Gamba Celeste | stand-in | 22,101 | 0 | T |
| Salicional Celeste | Gamba Celeste | stand-in | 19,977 | 0 | N |
| Salicional (Solo) | Gamba | stand-in | 19,971 | 0 | T |
| Lieblich Flute | Tibia Clausa (M) | stand-in | 17,720 | 301 | NT |
| Main String | Gamba | stand-in | 16,551 | 0 | J |
| Tibia Minor | Tibia Clausa (S) | stand-in | 16,303 | 0 | NT |
| Main Tibia Minor | Tibia Clausa (M) | stand-in | 13,520 | 0 | J |
| Solo Salicional (MPM) | Gamba | stand-in | 12,846 | 0 | J |
| Chorus Trumpet | Brass Trumpet | stand-in | 12,291 | 0 | T |
| Solo Voix Celeste | Gamba Celeste | stand-in | 10,340 | 0 | J |
| Midi 2 - Bowed Strings | Strings | stand-in | 8,107 | 0 | N |
| Solo Tibia Clausa (10") | Tibia Clausa (S) | stand-in | 7,876 | 0 | J |
| Echo Tibia | Tibia Clausa (M) | stand-in | 7,451 | 0 | T |
| Voce Umana | Horn Diapason | stand-in | 7,268 | 0 | T |
| French Horn | Oboe Horn | stand-in | 6,814 | 0 | J |
| Echo Principal | Horn Diapason | stand-in | 6,362 | 0 | T |
| Echo String Main Chest | VDO | stand-in | 5,384 | 0 | N |
| Musette | Krumet | stand-in | 4,898 | 0 | JNT |
| Echo Spitzflute Chest II | Concert Flute | stand-in | 4,752 | 0 | T |
| Great Mixture I | Diaphonic Diapason at 2' | stand-in | 2,768 | 301 | N |
| Great Mixture II | Diaphonic Diapason at 2' | stand-in | 2,768 | 301 | N |
| Great Mixture III | Diaphonic Diapason at 2' | stand-in | 2,768 | 301 | N |
| Great Mixture IV | Diaphonic Diapason at 2' | stand-in | 2,768 | 301 | N |
| I Mixture | Diaphonic Diapason at 2' | stand-in | 1,765 | 0 | J |
| II Mixture | Diaphonic Diapason at 2' | stand-in | 1,765 | 0 | J |
| III Mixture | Diaphonic Diapason at 2' | stand-in | 1,765 | 0 | J |
| IV Mixture | Diaphonic Diapason at 2' | stand-in | 1,765 | 0 | J |
| Echo Tibia Clausa | Tibia Clausa (M) | stand-in | 1,228 | 0 | J |
| Glockenspiel (Celeste A-435) | Glockenspiel | stand-in | 1,090 | 0 | J |
| Midi 8 - Arco Strings | Strings | stand-in | 1,008 | 0 | T |
| Tuba Mirabilis | Tuba Horn | stand-in | 927 | 0 | NT |
| Echo Vox (16') | Vox Humana (M) | stand-in | 548 | 0 | J |
| Echo Vox (8') | Vox Humana (M) | stand-in | 548 | 0 | J |
| 32' Resultant | Tibia Clausa at 32' | stand-in | 514 | 0 | J |
| Midi 14 - Pizz. Strings | Strings | stand-in | 457 | 0 | NT |
| Midi Double Basses | Strings or VDO | stand-in | 427 | 0 | N |
| Midi 7 - String Bass | Strings or VDO | stand-in | 398 | 0 | T |
| Mixture IV | Diaphonic Diapason at 2' | stand-in | 372 | 0 | T |
| Midi 3 - Harp | Harp | stand-in | 311 | 0 | N |
| 32' Resultant (Lieb) | Tibia Clausa at 32' | stand-in | 257 | 0 | J |
| 32' Resultant(Bourdon) | Tibia Clausa at 32' | stand-in | 257 | 0 | J |
| Echo Lieblich Tibia | Tibia Clausa (M) | stand-in | 254 | 0 | N |
| 32' Pedal Bourdon I | Tibia Clausa at 32' | stand-in | 224 | 0 | NT |
| 32' Pedal Bourdon II | Tibia Clausa at 32' | stand-in | 224 | 0 | NT |
| 32' Pedal Bourdon III | Tibia Clausa at 32' | stand-in | 224 | 0 | NT |
| 32' Pedal Bourdon IV | Tibia Clausa at 32' | stand-in | 224 | 0 | NT |
| Midi 3 - Orchestral Harp | Harp | stand-in | 139 | 0 | T |
| Midi 12 - Solo Flute | Concert Flute | stand-in | 101 | 0 | NT |
| Midi 13 - Str. Tremolo | Strings | stand-in | 93 | 0 | N |
| Salicional (16' String Organ) | Strings | stand-in | 85 | 0 | T |
| Tibia (Unenclosed) | Tibia Clausa (S) | stand-in | 63 | 0 | T |
| Bombarde I | Diaphonic Diapason at 32' | stand-in | 56 | 0 | N |
| Bombarde II | Diaphonic Diapason at 32' | stand-in | 56 | 0 | N |
| Bombarde III | Diaphonic Diapason at 32' | stand-in | 56 | 0 | N |
| Bombarde IV | Diaphonic Diapason at 32' | stand-in | 56 | 0 | N |
| Bombarde V | Diaphonic Diapason at 32' | stand-in | 56 | 0 | N |
| Bombarde VI | Diaphonic Diapason at 32' | stand-in | 56 | 0 | N |
| Echo 8' Vox Humana | Vox Humana (M) | stand-in | 30 | 0 | T |
| Echo 8' Vox Humana Celeste | Vox Humana (M) | stand-in | 30 | 0 | T |
| Midi 6 - English Horn | English Horn | stand-in | 26 | 0 | NT |
| 32' Soft Bourdon I | Tibia Clausa at 32' | stand-in | 23 | 0 | N |
| 32' Soft Bourdon II | Tibia Clausa at 32' | stand-in | 23 | 0 | N |
| Midi 16 - Pedal Double Bases | Strings or VDO | stand-in | 7 | 0 | T |
| Midi 1 - Str. Bass | Strings or VDO | stand-in | 5 | 0 | N |
| Midi 4 - Tympani | trap:Kettle Drum | stand-in | 4 | 0 | T |
| Midi 1 & 2 Piano (Bosendorfer) | — | silent | 8,380 | 8,380 | T |
| Piano | — | silent | 2,094 | 2,094 | JN |
| Concert Flute | Concert Flute | exact | 125,788 | 1,245 | JNT |
| Diaphonic Diapason | Diaphonic Diapason | exact | 57,269 | 2,869 | JNT |
| Open Diapason | Open Diapason | exact | 51,184 | 5,961 | JNT |
| Viol Celeste | Viol Celeste | exact | 46,855 | 0 | JN |
| Tuba Horn | Tuba Horn | exact | 45,455 | 1,928 | JNT |
| Viol d' Orch | VDO | exact | 44,526 | 10,743 | J |
| Clarinet | Clarinet | exact | 42,050 | 501 | JNT |
| Flute Celeste | Flute Celeste | exact | 41,402 | 0 | JNT |
| Tibia Clausa (Solo) | Tibia Clausa (S) | exact | 40,104 | 0 | NT |
| Solo Tibia (15") | Tibia Clausa (S) | exact | 35,395 | 0 | J |
| Brass Trumpet | Brass Trumpet | exact | 33,999 | 590 | JNT |
| Tibia Clausa | Tibia Clausa (M) | exact | 33,802 | 0 | NT |
| Quintadena | Quintadena | exact | 30,645 | 802 | JNT |
| Horn Diapason | Horn Diapason | exact | 30,238 | 0 | NT |
| Viol D' Orchestra | VDO | exact | 29,290 | 6,528 | N |
| Oboe Horn | Oboe Horn | exact | 27,713 | 503 | JNT |
| Orchestral Oboe | Orchestral Oboe | exact | 26,050 | 0 | JNT |
| Viol d'Orchestre | VDO | exact | 24,437 | 5,191 | T |
| Brass Saxophone | Saxophone | exact | 22,329 | 0 | JNT |
| Vox Humana | Vox Humana (M) | exact | 20,148 | 0 | NT |
| Vox Humana (Solo) | Vox Humana (S) | exact | 20,026 | 346 | NT |
| VDO Celeste | Viol Celeste | exact | 19,246 | 0 | T |
| English Horn | English Horn | exact | 9,827 | 20 | JNT |
| Marimba/Harp | Harp | exact | 8,176 | 1,239 | T |
| Solo Vox Humana | Vox Humana (S) | exact | 6,841 | 0 | J |
| Harp | Harp | exact | 4,781 | 0 | N |
| Marimba / Harp | Harp | exact | 3,536 | 0 | J |
| Master Xylophone | Xylophone | exact | 2,701 | 266 | JNT |
| Kinura | Kinura | exact | 2,461 | 0 | JNT |
| Chrysoglott | Chrysoglott | exact | 2,205 | 0 | JNT |
| Main Vox Humana | Vox Humana (M) | exact | 2,085 | 0 | J |
| Vibraharp | Vibraphone | exact | 1,406 | 81 | JNT |
| Glockenspiel (Perc.) | Glockenspiel | exact | 815 | 0 | T |
| Xylophone | Xylophone | exact | 551 | 20 | T |
| Glockenspiel (regular) | Glockenspiel | exact | 545 | 0 | J |
| Glockenspiel (15") | Glockenspiel | exact | 253 | 0 | J |
| Cathedral Chimes | Cathedral Chimes | exact | 73 | 0 | J |
| Glockenspiel | Glockenspiel | exact | 42 | 0 | N |
| Chimes | Cathedral Chimes | exact | 19 | 0 | T |

## Pitches with no Paramount tab

| Manual | Dad's rank | Pitch | Key presses | Disks |
|---|---|---|---:|---|
| Great | Viol d' Orch | 2' | 10,743 | J |
| Great | Viol d'Orchestre | 2' | 4,765 | T |
| Great 1st Touch | Viol D' Orchestra | 2' | 4,171 | N |
| Great | Violin | 2' | 3,358 | T |
| Great 1st Touch | Open Diapason | 1 1/3' | 2,088 | N |
| Pedal | Diaphonic Diapason | 4' | 2,067 | JNT |
| Great | Open Diapason | 2 2/3' | 1,767 | J |
| Great | Tuba Horn | 4' | 1,426 | J |
| Accomp. | Marimba/Harp | 4' | 1,239 | T |
| Bombarde | Viol D' Orchestra | 2' | 1,200 | N |
| Bombarde | Violin | 2' | 927 | NT |
| Bombarde | Open Diapason | 1 1/3' | 501 | N |
| Bombarde | Open Diapason | +43 | 501 | N |
| Bombarde | Open Diapason | 1' | 501 | N |
| Bombarde | Diaphonic Diapason | 1' | 501 | N |
| Bombarde | Concert Flute | +48 | 501 | N |
| Bombarde | Viol D' Orchestra | 1' | 501 | N |
| Bombarde | Salicional | 2' | 501 | N |
| Bombarde | Solo String | 2' | 501 | N |
| Bombarde | Quintadena | 4' | 501 | N |
| Bombarde | Oboe Horn | 4' | 501 | N |
| Bombarde | Clarinet | 4' | 501 | N |
| Bombarde | Tuba Horn | 4' | 501 | N |
| Bombarde | Brass Trumpet | 4' | 501 | N |
| Bombarde | Viol d'Orchestre | 2' | 426 | T |
| Pedal | Concert Flute | 2' | 355 | N |
| Pedal | Viol D' Orchestra | 2' | 355 | N |
| Pedal | Salicional | 4' | 355 | N |
| Pedal | Violin | 4' | 355 | N |
| Pedal | Open Diapason | 1 1/3' | 301 | N |
| Pedal | Open Diapason | 2' | 301 | N |
| Pedal | Diaphonic Diapason | 2' | 301 | N |
| Pedal | Great Mixture IV | 8' | 301 | N |
| Pedal | Great Mixture III | 8' | 301 | N |
| Pedal | Great Mixture II | 8' | 301 | N |
| Pedal | Great Mixture I | 8' | 301 | N |
| Pedal | Concert Flute | 1' | 301 | N |
| Pedal | Lieblich Flute | 4' | 301 | N |
| Pedal | Viol D' Orchestra | 4' | 301 | N |
| Pedal | Solo String | 4' | 301 | N |
| Pedal | Quintadena | 8' | 301 | N |
| Solo | Master Xylophone | 16' | 266 | T |
| Great 1st Touch | Vox Humana (Solo) | 4' | 198 | N |
| Great | Vox Humana (Solo) | 4' | 148 | T |
| Pedal | Concert Flute | 10 2/3' | 88 | T |

54 combinations in all; the 45 most played are listed.

## Played on a near voice

| Manual | Dad's rank | Pitch | Played on | Key presses |
|---|---|---|---|---:|
| Accompaniment 1st Touch | Lieblich Flute | 4' | Stop: Acc: Tib Piccolo II 4 | 3,359 |
| Great 1st Touch | Open Diapason | 2' | Stop: Gt: Fifteenth 2 | 2,088 |
| Great | Open Diapason | 2' | Stop: Gt: Fifteenth 2 | 1,767 |
| Accomp | Concert Flute | 2' | Stop: Acc: Tibia Piccolo 2 | 1,182 |
| Pedal | Solo Tibia (15") | 16' | Stop: Ped: Tibia Clausa I 16 | 1,024 |
| Bombarde | Open Diapason | 2' | Stop: Gt: Fifteenth 2 | 501 |
| Accompaniment 1st Touch | Concert Flute | 2' | Stop: Acc: Tibia Piccolo 2 | 438 |
| Pedal | Tibia Clausa (Solo) | 16' | Stop: Ped: Tibia Clausa I 16 | 421 |
| Accomp | Open Diapason | 4' | Stop: Acc: Octave 4 | 408 |
| Pedal | Violin | 16' | Stop: Ped: Gamba 16 | 88 |
| Pedal | Salicional (16' String Organ) | 16' | Stop: Ped: Gamba 16 | 85 |

## Traps and effects

| Dad's trap / effect | Paramount | Key presses | Disks |
|---|---|---:|---|
| Snare Drum | Acc: Snare Drum Roll, Ped: Snare Drum | 210 | JT |
| Tap Cymbal | Ped: Tap Cymbal, Acc: Tap Cymbal | 198 | JT |
| Snare Control On | — (silent) | 186 | T |
| Unenclosed Tap Cymbal | Acc: Tap Cymbal | 165 | N |
| Exposed Tap Cymbal | Acc: Tap Cymbal | 164 | J |
| Brush Cymbal | Ped: Ride Cymbal | 64 | NT |
| Wood Block | Acc: Chinese Block | 54 | J |
| Crash Cymbal | Ped: Crash Cymbal | 34 | JNT |
| Exposed Brush Cymbal | Ped: Ride Cymbal | 13 | J |
| Bass Drum | Ped:Bass Drum ff | 12 | J |
| Kettle Drum | Ped: Kettle Drum | 4 | JT |
| (unnamed) | — (silent) | 4 | T |
| Chinese Block | Acc: Chinese Block | 2 | N |
| Unenclosed Crash Cymbal | Ped: Crash Cymbal | 1 | N |
