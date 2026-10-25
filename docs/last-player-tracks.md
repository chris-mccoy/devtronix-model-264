# `last-player`: the McCoy Organ disk's tracks

`last-player` (volume label "McCoy Organ") is a working disk for the McCoy
organ: System Monitor 2.6 (180), four combination files, sixteen definitions
(the McCoy organ in several versions, the Ahlborn MIDI set-ups, two 58-note
player definitions, a copy of PCC ORGAN, a single MIDI Great) and eleven
tracks. None of the tracks has a name. This file records what each track is,
how far identification got (October 2026), and what was ruled out, so the
next attempt can start from here.

Pitches use scientific names (C4 = middle C) as rendered in
`renders/last-player/` (keyboard mode, one MIDI channel per keyboard). Times
are those of the 120 BPM render. The renders use `D7` for T1–T4, `D5` "Octave Player" for T5–T8 and T11, and `D11` "PCC
ORGAN" for T9 and T10, the two tracks played on a keyboard 5 that no McCoy
definition has. Those are the best-covering definitions on the disk, not
necessarily the ones loaded when the tracks were recorded.

## Summary

| Track | Length | Keyboards | Key | What it is | Identification |
|---|---|---|---|---|---|
| T1 | 0:42 | Great, Pedal | C minor | Slow chords over a pedal line climbing by semitones | Probably improvised |
| T2 | 2:34 | Great | G minor | Three-voice fugue, manuals only | Not identified |
| T3 | 2:31 | Pedal | | 76 pedal notes with long gaps | Practice or a test |
| T4 | 0:51 | Swell, Pedal | G minor | Slow Swell line | Probably improvised |
| T5 | 1:15 | Great, Swell, Pedal | A minor | Fast dance in Hungarian/gypsy style | Not identified; same piece as T6 |
| T6 | 1:33 | all four | A minor | T5 played again, longer, with the Choir added | Not identified |
| T7 | 0:48 | Great (two pedal notes) | C major | Two-voice sketch | Probably improvised |
| T8 | 0:12 | Great | C major | Sixteen three-note chords | A fragment |
| T9 | 2:45 | keyboard 5 | F minor? | Novelty-piano style, very dense | Not identified |
| T10 | 2:43 | keyboard 5 | E♭ major | Rag or novelty style, very dense | Not identified |
| T11 | 4:54 | Great, Pedal | C major | Waltz-like tune in tremolo octaves | Not identified; fits a 58-note roll |

## The pieces

### T2: fugue in G minor

All on the Great, up to six notes at once, no pedal. The first voice is alone
until 0:15:

D5 (long) | E♭5 D5 E♭5 C5 | D5 (long) | G4 A4 A4 D5 C5 B♭4 G4 | D5 D5 B♭4 G4 | E♭5 (long) D5 (long) C5 …

The second voice answers at 0:15 on G4 (long), then B♭4 A4 B♭4 G4 A4: the
subject's turn with its first interval widened, a tonal answer. A third voice
enters in the tenor near 0:28. At 0:51 a descending sequence runs
C5 C5 C5 D5–C5 B♭4 | B♭4 B♭4 B♭4 C5–B♭4 A4 | A4 A4 A4 B♭4–A4 G4 | G4 G4 G4 A4–G4 F4.

Not Bach's "Little" Fugue in G minor (BWV 578) and not the G-minor fugue of
*The Well-Tempered Clavier* book I (BWV 861). Book II's G-minor fugue
(BWV 885) has not been checked.

### T5 and T6: A-minor dance

The same piece twice; T6 is the longer take and adds the Choir. It opens with
A minor, E major and A minor chords and a fast falling scale
(G5 F5 E5 D5 C5 B4), then the main theme rises over a bass falling by steps:

E4 E4 F♯4 G♯4 A4 | A4 B4 C5 | C5 D5 E5 (played twice)

After that come E–F–E turns (E4 F4 E5, E5 F5 E5, over A minor and E), and
F5–G5 alternations over a chain of chords round the circle of fifths (D minor,
G, C, F, …). In T6: at 0:24, arpeggios held over a low E (D5 with G♯5, B5, F5,
an E7♭9); at 0:35, a passage with B♭ (E5 F5 B♭4 G5 B♭4 E5 B♭4 E5); at 0:41,
A4 A4 E5 F5 F5 F5 E5 D5 E5 (twice); then running eighths (E5 D5 C5 D5 B4 E5 D5
C5 B4 A4 B4 C5 D5 E5 …); it ends on falling scale runs.

It sounds Hungarian or gypsy, a csárdás or something like it. It is not the
tarantella on the Disklavier floppy (below).

### T9 and T10: novelty piano

Both were played on keyboard 5 with very short notes (median 0.04 s and
0.07 s) and up to 14 at once, more like a piano or a roll than hands on organ
keys. Their compass is a piano's, wider than a 58-note roll's: MIDI 36–96 for
T9, 27–94 for T10.

- **T9** opens with a falling run, C7 E♭6 C♯6 C7 B♭6 G6 C7 B♭6 G6 F6 E6 C♯6
  C6 E♭6 C♯6 C6 B♭5 A♭5 G5 F5 E5 C5. From about 0:09 the theme is built on
  quick crushed notes against C: C6 E♭6 C♯6 E♭5 C♯5 C6 B5 | C6 E♭6 C♯6 E♭5 C♯5
  C6 C7 | ….
- **T10** opens with a falling run over two octaves, F6 G6 F6 E♭6 C6 B♭5 A♭5
  G5 F♯5 F5 G5 F5 E♭5 C5 B♭4. The theme follows: B♭4 C5 D5 E♭5 F5 E♭5 C5 D5
  E♭5 E5 F5 F♯5 G5 E♭5 C5 B♭4 C5 B♭4 C5 B♭4. It is answered by F6 E♭6 F6
  E♭6 F6 in a short–long syncopation. From 0:24 there is a slower strain in steady
  quarter notes on G5 and A♭5 (G G A♭ A♭ G G G G A♭ A♭ …).

### T11: waltz-like tune in tremolo octaves

The track opens with an introduction on held chords, 0:02–0:13: G7 with a
small figure on G and A over it, then a diminished chord (G B♭ C♯ E) with the
same figure, then G7 again. From 0:13 the tune is played in fast broken
octaves, so repeated notes in the tune do not show:

G F♯ G | A — G — | C/E — — A | C B — — |
G F♯ G | B — A — | B over F — — | E — — — |
G F♯ G | A — G — F — E — | D — C — B — A …

A second strain starts near 0:33. The compass is MIDI 36–91, which fits the
58-note rolls (36–93) exactly, and the disk carries the 58-note player
definitions (`D9` "58 NOTE PLAYER PRINCIPAL", `D10`). So T11 may be a roll
played through the McCoy organ. It is not any of the 470 rolls on the
58-note player disks.

It is not the chorus of "Let Me Call You Sweetheart", which opens
E G C D E G F♯ G A, and not *In the Shade of the Old Apple Tree*, *The Band
Played On*, *Missouri Waltz*, *Peg o' My Heart*, *Shine On, Harvest Moon*,
*Daisy Bell*, *Moonlight and Roses* or *Have You Ever Been Lonely?*; all were
checked against their lead sheets.

## The fragments

- **T1**: Great chords in C minor over a pedal line that climbs by semitones
  from E♭2 (E♭2 E2 F2 F♯2 G2 … A♭2 B♭2), returns to E♭2 and ends on C3.
- **T3**: Pedal only, F2–B♭3, starting at 0:43, with silences of 18, 23 and
  9 seconds.
- **T4**: A slow Swell line in G minor (D5 D5 E♭5 D5 … F♯5 G5 F♯5 G5 A5 F♯5 G5
  F5 E♭5 D5 …). Its "held pedal" is seven key presses whose releases were
  never recorded; the render holds them to the end.
- **T7**: Two voices in C major. C5 B4 C5 (long), C5 B4 C5 E5 C5 B4 C5 G4 C5
  E4 G4 C4, then G5 E5 G5 A5 G5 F5 G5 (long) and E5 C5 E5 F5 E5 D5 E5. It turns
  to C minor at 0:26 (E♭5 C5 G5 E♭5 C6) and ends on a scale falling two octaves
  to G4.
- **T8**: Sixteen three-note chords moving by step in C major; top line
  G4 C5 E5 D5 C5 B4 A4 G4 A4 B4 C5 D5 C5 B4 A4 G4.

## What was ruled out

- **Other tracks in the collection.** Every track's top line was compared
  with every other's. Only T5 and T6 share material; the partial matches with
  58-note rolls (T10 with 58-note-16 T23, T11 with 58-note-14 T26 and
  58-note-07 T8) are shared chromatic runs, scales and broken octaves.
- **A theme index.** 14,012 themes from 2,358 pieces, mostly Mutopia editions
  (Bach, Beethoven, Chopin and others), from the
  [new-theme-finder-site](https://github.com/frankslin/new-theme-finder-site)
  index. [Themefinder](https://www.themefinder.org/) itself was unreachable.
- **Lead sheets.** The [OpenEWLD](https://github.com/00sapo/OpenEWLD) set of
  502 public-domain popular-song lead sheets (roughly 1890–1930). Its only
  matches were scales, broken chords and trills.
- **The two Disklavier floppies** (below): nothing on them matches any track
  in the collection.

## The Disklavier floppies

The two MS-DOS disks in `new-images/` are Yamaha Disklavier (DRC 1.60)
floppies; `system-monitor/dosdisk.py` copies their files out. Each song is a
`DRC_nn.MDA` file in Yamaha's E-SEQ format: plain MIDI channel messages
between E-SEQ delay and bar-line codes, from offset `$57`. `MUSIC.DIR` lists
the files but holds no titles. They were checked here only to see whether
any of the 264's recordings came from them; none did.

| Disk | File | Notes | What it is |
|---|---|---:|---|
| `fenelon-tarantelle` | `DRC_01` | 5532 | One long piece: E F G A in octaves, then D minor and A major; presumably the tarantella of the label |
| | `DRC_05` | 0 | 955 bytes with no note events; not decoded further |
| `midi-piano-selections` | `DRC_01`–`DRC_06` | 597–14 656 | Six piano pieces, unnamed |
| | `DRC_07` | 72 | E♭-major arpeggios up and down the keyboard, then a few chords |
| | `DRC_10`, `DRC_11` | 67 | A chromatic scale C2–C7, a test; the two differ only in the file name in their headers |
