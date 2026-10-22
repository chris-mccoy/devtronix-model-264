# How the lists of a definition link together

A definition (`D` file) is a set of lists, and the lists refer to each other by
item number (1-based, in list order). This is how they connect when the relay
runs. Field offsets (`+2`, `+4`, ...) are body offsets, as `devdef.py --item`
prints them; the full field tables are in
[`../system-monitor/README.md`](../system-monitor/README.md#definition-files-d).

## 1. What switches a function on

```mermaid
flowchart LR
  TRK[("<b>T</b> Track file")]
  PST["<b>Pst</b> piston"]
  CF[("<b>C</b> file<br/>OFF and ON stop bitmaps<br/>per piston")]
  SPF["<b>Spf</b> Set and Range pistons"]
  CTL["<b>Ctl</b> control button"]
  STP["<b>Stp</b> stop<br/>contacts in;<br/>indicator and magnets out"]
  LNK["<b>Lnk</b> link<br/>RPN expression over<br/>stops and control buttons"]
  CIN["<b>Cin</b> channel input<br/>a contact worth a value,<br/>or analog"]
  CHN["<b>Chn</b> channel<br/>expression, crescendo, tempo"]
  COT["<b>Cot</b> channel output"]
  USE{{"<b>Fnc</b> function<br/>use count: active while above 0"}}
  KEYS["types 1, 3–9, 13, 14<br/>act on keys: diagram 2"]
  F12["12 function multiplier"]
  F17["17 stop reverser"]
  F15["15 channel coupler<br/>16 channel output"]
  F19["19–22 MIDI program change,<br/>controllers, velocity"]
  MIDI(["MIDI out"])

  TRK -.->|"stop events"| STP
  PST -->|"row n"| CF
  SPF -.->|"held: program the piston"| CF
  CF -->|"stops off, then on"| STP
  CTL -->|"$4000 + n"| LNK
  STP -->|"stop n"| LNK
  LNK -->|"its function list,<br/>+1 when true, −1 when false"| USE
  CIN -->|"channel +2, value +4"| CHN
  CHN --> COT
  COT -->|"function +2, at value +4"| USE
  USE --> KEYS
  USE --> F12
  USE --> F17
  USE --> F15
  USE --> F19
  F12 -.->|"switches up to 8 more"| USE
  F17 -.->|"toggles up to 4 stops"| STP
  CHN <-.-|"sets a value"| F15
  F19 --> MIDI
```

## 2. What an active function does with keys

```mermaid
flowchart LR
  KBD["<b>Kbd</b> keyboard<br/>an input address per key, 1–121"]
  TRK[("<b>T</b> Track file")]
  F9["9 transposer"]
  F6["6 unison off<br/>7 sustain, 8 legato, 18 sostenuto"]
  NS(["note set<br/>one per keyboard, built at Run"])
  F1["1 divisional coupler<br/>melody or bass at +14"]
  PIZ["<b>Piz</b><br/>release time per note"]
  RIT["<b>Rit</b><br/>cycle and duty per note"]
  F13["13 pizzicato modifier<br/>14 reiterate modifier"]
  F3["3 rank output<br/>pitch offset, note limits"]
  F4["4 trap output"]
  F5["5 direct unit output"]
  SPF["<b>Spf</b> metronome and<br/>downbeat units"]
  RNK["<b>Rnk</b> rank<br/>an output address per pipe, 1–121"]
  UNT["<b>Unt</b> unit<br/>plain, one-shot, reiterating,<br/>shade, MIDI note"]
  BRD(["output boards<br/>use count per address"])
  MIDI(["MIDI out"])

  KBD -->|"key on / off"| NS
  TRK -.->|"key events"| NS
  F9 -.->|"shifts every key"| NS
  F6 -.->|"silences or holds keys<br/>of keyboard +2"| NS
  NS -->|"keyboard +2"| F1
  F1 -->|"key + offset into<br/>division +4"| NS
  NS -->|"division +2"| F3
  NS -->|"division +2"| F4
  PIZ -->|"+4"| F13
  RIT -->|"+4"| F13
  F13 -->|"+2: wraps a function"| F3
  F3 -->|"rank +4:<br/>pipe = key + offset"| RNK
  F4 -->|"unit +4"| UNT
  F5 -->|"unit +2"| UNT
  SPF --> UNT
  RNK --> BRD
  UNT --> BRD
  RNK -.->|"addresses from $6001"| MIDI
  UNT -.-> MIDI
```

How to read it:

- **Boxes headed with a list name** (`Kbd`, `Stp`, `Lnk`, ...) are lists in the
  `D` file, and the numbered boxes are the types of `Fnc` item. `T` and `C` are
  the Track and Combination files, which refer to the definition's keys, stops
  and pistons by number. Rounded boxes are what the relay builds or drives at
  run time.
- **A key reaches a pipe in three steps.** A key goes into its keyboard's note
  set. Every active function hooked on that note set sees it. A rank output
  function (type 3) then turns key + pitch offset into one of its rank's pipe
  addresses.
- **Stops do nothing by themselves.** Drawing a stop re-evaluates every link
  whose expression mentions it. When a link turns true, each function in its
  list gets a use count of +1 and is active while the count is above zero, so
  two links can share one function. Channel outputs switch functions the same
  way, by channel value, which is how the crescendo pedal draws stops.
- **Couplers chain.** A divisional coupler takes the keys of the keyboard at
  `+2` and feeds them, offset, into the note set of the division at `+4`, where
  they count like played keys. With "couple the couplers" (`+12`) the coupled
  keys are coupled on again.
- **Modifiers wrap another function.** Pizzicato and reiterate take the
  function at `+2`, usually a rank output, and time its notes from a `Piz` or
  `Rit` table.
- **MIDI is just another address.** Any input or output address from `$6001`
  up is MIDI (a note, or a program change for inputs from `$6801`), so a rank or
  unit given such addresses plays a MIDI instrument instead of magnets.

Not shown: `Ind` (system lamps such as disk busy and recording, driven by the
monitor itself), `Div` (an old division list the loader turns into keyboard
references) and the timing fields of `Spf`.
