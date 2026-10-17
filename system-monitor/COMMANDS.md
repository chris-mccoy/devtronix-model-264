# System Monitor 2.6 (183) — command reference

Everything the terminal command line of the Devtronix Model 264 accepts, as
recovered from the command table (`cmd_table`, `$38B8` in `monitor-183.asm`),
the built-in `Help` text and the handlers themselves. Where a handler was read in
full the behaviour is stated; where only its prompts and messages were read this
is said. Addresses are handler entry points in the listing, for cross-checking.
Differences in version 189 are at the end.

## How the command line works

- The monitor runs in one of four **modes**: Idle (also called Menu), Edit,
  Run and RunEdit. The status line shows the mode; `Idle`, `Menu`, `Edit`, `Run`
  and `RunEdit` switch between them, `Quit` shuts the system down ("System shut
  down").
- A command is a word followed by optional arguments; words are matched
  case-insensitively against the table, which also holds explicit one-letter
  aliases (`R`, `P`, `F`, `K`, `T`, `L`, `S`, `G`). Leading `/` characters are
  skipped (the editor uses `/CPY`, `/REP`). "Illegal Command" if nothing
  matches, "Command error" when a handler cannot parse its arguments.
- Each table entry carries a mask of modes the command may be used in. Most
  utility commands carry `$4F`: usable in Idle, Edit, Run and RunEdit. Run-mode
  commands carry `$04`. `Conset`/`Conbrd` carry `$03`: Idle or Edit only.
- **File specification** (`dsk_parsefile`, `$410A`): a slot letter `A`–`Z`
  followed by a number 1–99, optionally followed by a quoted name of up to 25
  characters, e.g. `T12 "Sleigh Ride"`. The letter is the file type (A system,
  D definition, C combination, T track/song) and commands check it ("File type
  mismatch"). Where a command implies the type the letter may be omitted and
  just the number given.
- **File lists** (`dsk_parselist`, `$4676`): slots separated by commas,
  `T1,T2,T5`.
- **Numbers** are decimal. Several commands prompt interactively instead of
  taking arguments; `ESC` cancels a prompt ("File operation cancelled").
- Disk commands mount the disk in the current drive, do their work and unmount,
  reporting through the error list: Invalid file name, Disk not ready, Disk read
  error, Disk file not found, Duplicate file name, Disk is full, Disk is write
  protected, End of disk directory, Illegal disk record number, Disk format
  error, Disk header record error, File type mismatch, File operation cancelled,
  Remote disk file not found.
- The `Boot`-time screen shows `Disk:` (label), `Status:` (Normal, Write
  protected, Read error, Write error, Format error, Disk full), `Free disk:` in
  KB, `Busy:`, `File:`, `Access:` and `Free ram:`.

## Mode commands (usable in every mode)

| Command | Handler | What it does |
|---|---|---|
| `Idle`, `Menu` | `$1358` | Return to Idle mode. Stops the organ scanner; the command loop then runs `menu_loop` |
| `Edit` | `$1358` | Enter the definition editor (`edit_mode`, `$EB64`). Requires a definition to be loaded or started with `Clear` |
| `Run` | `$1358` | Run the organ: "No definition file loaded" if none. Starts the scanner, loads `C1` ("Load C1" indicator), shows the run screen (Scan rate, Worst delay, Runtime, Song status, Tempo, Time, Record, Meter, Measure, Beat, Play, Status) |
| `Quit` | `$1358` | Leaves the mode loop: prints "System shut down" and calls the Dimension-030 driver's exit when relocated, otherwise halts |
| `Help [I\|E\|R]` | `$12880` | Prints the built-in help pages: `Help I` idle commands, `Help E` edit commands, `Help R` run commands. The text says "The help system is not yet fully implemented" |
| `Screen` | `$62B6` | Redraw the screen; shows "System version 2.6 (183) released on 05/11/93" |
| `Ver` | `$5F0A` | Prints the version and date line |
| `Beep` | `$60EE` | Toggle the terminal bell: "Terminal Beep Turned On/Off" |
| `Term [n]` | `$6276` | Without a number prints "Current terminal type is n"; with one selects the terminal escape-sequence table (`term_select`, tables at `$1B8A`): 0 TeleVideo 950, 1 Wyse 50 (alternate graphics), 2 TeleVideo cursor always on, 3 TeleVideo no graphics, 4 minimal ADM-3A class, 5 Devtronix PC terminal program, 6 Wyse WY-50. Most disks' monitors default to 6; see README.md "Terminals" |
| `Tbeep` | `$A4FE` | Test the bell: "So, like, BEEP!" after a timer callback |
| `X n` | `$60C2` | Test command: waits `n` ticks, opens a window, waits for a key |
| `Time n` | `$A538` | Timer-wheel test: schedules a callback `n` ticks ahead |
| `Mem [n]` | `$5F4E` | Heap display: walks the free list, prints "block at … (in-use)", "Total memory in-use is … bytes", "Calculated in-use is … bytes"; a number limits the listing |
| `Hex` | `$607A` | Debug: toggles indicators 1 and 2 and walks the heap to the end of RAM |
| `Tsk`, `Tskdsp` | `$A6C6` | "Stack Size Check": for each task prints name, "bytes used" of its stack and worst run time in ms; also "Key time was %t microseconds", "Stop time was %t microseconds" |
| `Tskclr` | `$A69E` | Clears the task timing statistics |
| `Speed` | `$DD18` | CPU speed test: times a loop of malloc/free against the tick counter |
| `Memtst` | `$DD44` | RAM test: "Testing memory address %5dk" from `$20000` up to the end of RAM |
| `Turbo` | `$61C0` | Dimension-030 accelerator: "Dimension-030 Turbo Mode Turned On/Off" or "Dimension-030 Board Not Installed" |
| `.` | `$EA96` | Inject console events for testing: `. K n` presses key `n` of the keyboard chosen with `. D k` (1–16), `. S n` turns stop `n` on, `. F n` fires function `n`, `. U n` unit `n`, `. P n` piston `n`. A leading `-` releases/turns off (`. -K 40`) |

## Disk and file commands (Idle, Edit, Run)

| Command | Handler | What it does |
|---|---|---|
| `Dir [list]` | `$62F4` | "--- Directory Listing ---": one line per file, `slot "name" (sectors - bytes at header-sector)`, 17 lines per page then waits for Return; "Header record contains trash" for a bad header. With a slot list only those files are shown |
| `Load spec` | `$54EC` | Idle: load a definition (`D`) or combination (`C`) file; "Loading definition file from disk" / "Definition file loaded", "Definition file not current format" if the version word is outside `$1A12`–`$1A15`. Defaults to `D1` when only a number is given |
| `Save spec` | `$5562` | Save the current definition (`D`) or combination (`C`) file: "Saving definition file onto disk" / "Definition file saved", "Saving combination file" / "Combination file saved". Prompts when the slot is occupied (see `Record`) |
| `Erase spec` | `$6590` | Delete a file: frees its sectors and directory entry, "File erased" |
| `Unerase` | `$65D8` | Scans every unused sector for a sector that looks like a file header ("…. Searching for file header ….", "--- Found possible erased file ---", shows Filename, Original file slot, File size, Header record number) and asks "Do you wish to reactivate this file? (Y/N)". A recovered file is put in the first free slot of its type: "This file has been reactivated in slot …, You should move it to a usable slot later"; "End of unerase processing" |
| `Move spec TO spec` | `$642A` | Change a file's slot: both specs must have the same letter (or `Z`), "File exists in that slot" if taken, "File moved" |
| `Name spec "name"` | `$6520` | Write a new name into the file's header sector: "File renamed" |
| `Copy list` | `$7198` | Copies files to another disk in one drive: "Files selected for copy:", reads as many as fit into RAM ("Copying files from source disk into computer memory:"), "Remove the source disk, insert the target disk and hit return:", writes them ("Copying files from computer memory onto target disk:"), repeats with "Another pass is necessary to copy more files" and "Remove the target disk, insert the source disk again and hit return:" until done: "Copy completed - enter ESC to exit:" |
| `Dump record [byte]` | `$6A1A` | Hex/ASCII dump of logical sector `record` starting at `byte` ("Disk record:", "Starting byte:"); keys page through the sector |
| `Disk` | `$69E0` | Mounts the disk and reports its status (error message or label) |
| `Dskname` | `$6B98` | "Enter new disk name:" — writes the volume label at boot block `$1C` |
| `Init` | `$6B4A` | Re-initialise the directory of the mounted disk: clears the directory and bitmap in the boot block and writes it back (the disk must not be write protected) |
| `Format` | `$6ECA` | "--- Disk Formatting Routine ---": asks "Enter number of sides (1 or 2):", formats 80 tracks ("Formatting track: n"), asks "Enter disk name:", writes a fresh boot block: "Formatting Complete" or "Error code n detected - formatting aborted" / "Format aborted" |
| `Boot` | `$6C24` | "--- Disk Boot Setup Routine ---": shows the current boot file, asks "Enter new file to boot from (ESC to cancel):". The file must start with `lea d(pc),a5` ("Not a valid operating system file"); writes boot block words `$36` (header sector) and `$38` (load address derived from the displacement): "This disk will now boot up using: …" |
| `System [n]` | `$84E0` | "Saving system monitor (%d bytes)": writes the running monitor image to slot `A<n>` (default: the slot it was booted from), name "System Monitor 2.6 (183)"; "System monitor saved" |
| `Fixfile spec` | `$6968` | Rewrites a file header in the previous header layout: "File fixed to old format" |
| `Dtoa spec` | `$6EBE` | Definition to ASCII; implemented in the Dimension-030 driver (function 11), does nothing without the board |
| `Atod spec` | `$6EB2` | ASCII to definition; Dimension-030 driver function 10 |
| `View` | `$127F0` | "-------- Ascii File Viewer/Editor --------": opens a window and waits for a key (a stub) |
| `Modem [baud]` | `$282C` | "-------- MODEM CONNECT MODE --------" on DUART channel B at 300, 1200, 2400 or 9600 baud (default 2400; "Not a valid baud rate"). Keys go to the modem; "Press ESCAPE 3 times within 1 second to exit", `Control-D` starts a file download ("--- File Download ---", prompts Filename, Fileslot, shows Filesize/Received/Errors, "Download successful" / "** Download failed **"), `Control-U` an upload ("Enter the Devtronix file ID to upload:", "Enter the filename to be used on the BBS:") |
| `Pcdisk` | `$4CEA` | Mount a PC over the serial link as the disk: "PC Disk mounted in DOS file mode" or "… in Devtronix disk image mode"; "PC Link not active" if no PC answers. After this the file commands go to the PC |
| `Topc spec` | `$4DDA` | Send a file to the PC ("--- File Upload ---" window) |
| `Frompc spec` | `$4DDC` | Receive a file from the PC: "--- File Transfer From PC ---", "File transfer complete - press ESC to exit:"; also "--- System Load From PC ---" which receives a monitor image and runs it ("Transfer complete - press ESC to execute:", "Executing system file", "Not a valid system file") |

## Recording and song commands

| Command | Mode | Handler | What it does |
|---|---|---|---|
| `Record [spec]`, `R` | Run | `$CD1C` | Start recording into Track file `T<n>` (prompted/overwrite dialogue when the slot exists: "There is already a file in slot T5 … R - write over the old file with the new file, N - write the file into a new slot, ESC - cancel"; `N` shows "The first ten slots available for this file are:"). Without a slot the console's File # display is used. Writes the sync block and waits for `Go` or the first key unless the "go switch" is on; "Already recording" if a recording is in progress |
| `Play [list]`, `P` | Run | `$D0FC` | Queue songs for playback: a comma-separated list of `T` slots, a range `T1-T5`, and `(...)` to repeat the group. Without a list the File # display's slot is used. "Playback list empty", "Already playing", "Track file not found" |
| `Go`, `G` | Run | `$8A94` | Start the queued playback/recording now (arms the pulse clock at the next beat) |
| `Pause` | Run | `$8AAA` | Pause/resume playback and recording |
| `Finish`, `F` | Run | `$8A76` | End the current recording (writes `$FF`, flushes the last block) and let playing songs run out |
| `Kill`, `K` | Run | `$8A6C` | Stop all playback songs immediately and release keys and stops |
| `Gosw` | Run | `$6136` | Toggle the "go switch": "Go Switch Turned On/Off". When on, Record/Play start as soon as the first key is pressed |
| `Tempo [n]`, `T` | Run | `$D9BE` | Set the tempo in beats per minute (10–999, default 120 when no number). The tempo also follows the console's tempo button (tap tempo) and tempo control |
| `Meter n/m` | Run | `$8AB0` | Set the meter shown as "Meter: n/m" (beats per measure 1–32 / beat unit); beep on a bad value |
| `Room n` | Run | `$8B46` | Set the room-size output delay in ms, "Delay must be less than 999" |
| `Graph [n]` | Run | `$8BD4` | "----- Channel output graph -----": live bar graph of the analog channel values (optionally only the first `n` channels, up to 99); any key closes it |
| `Ptrace` | Run | `$D898` | Toggle a trace window that shows each played event's slot |
| `Dirt` | Run | `$8B7A` | Check the output table: "Output table is clean" / "Output table is dirty" |
| `Timer` | Run | `$6176` | "Function Timer Turned On/Off": timing of key and stop processing for `Tsk` |
| `Keytst [n]` | Run | `$DB3A` | Key-processing test: turns on stops 55–59 and plays key 49 on keyboard 2 repeatedly |
| `Timtst [n]` | Run | `$DBE6` | Timing test of the key/stop pipeline (allocates test tables) |
| `Analyze spec` | any | `$E092` | Reads a Track file and prints "---- Console Event Counts ----": Zero/Normal/Extended/Humongous pulse counts, Key changes, Stop changes, Console changes, Channel changes, Midi note-on/off/other commands, Key balance count, Key balance bad record, Key count bad record, Illegal codes, First key position, Last key position, Song length (as measure:beat:pulse) |
| `Process spec` | any | `$E7CE` | "---- Processing Track File ----": reads a Track file and reports "Initial delay = n" pulses and "Possible song breaks = n" (gaps of 768 pulses = 4 s or more) |
| `Split spec [gap]` | any | `$7538` | Cuts a Track file into songs at gaps of `gap` seconds (default 10): "Scanning for track-sync code…", "Track Splitting in Progress", per-song "Input Track Progress" and "Song # Progress" windows (Time, Measure, Key/Stop/Channel changes, Keys/Stops active, errors). At each gap: "A gap of … seconds has been detected", then `W` writes the song to the target disk (swap disks when asked; the boot block is compared to check the right disk is in), `C` continues the same song, `I` ignores it. Songs are written as `T` files named `"<slot> (Song n meas m)"`; warnings "Note that there was no key activity" / "Note that there are still some keys active" |

In Run mode the console pistons do the same through the CTL task: Record,
Play, Finish, Kill, Load C, Save C, Go, Pause, File Up/Down, and `C99` is written
by Auto Save.

## Combination commands (Run mode)

| Command | Handler | What it does |
|---|---|---|
| `L [spec]` | `$5528` | Load a combination file `C<n>` (default `C1`): "Loading combination file" / "Combination file loaded" / "C1 combination file not found" |
| `S [spec]` | `$559C` | Save the combination settings to `C<n>`: "Saving combination file" / "Combination file saved" |

## Console and I/O diagnostics

| Command | Mode | Handler | What it does |
|---|---|---|---|
| `Console` | any | `$C2D2` | "Console input scan test": scans the input boards and prints each active input with its address (`AA-A1` form) and what it is defined as ("key n", "switch #n", "--- Unassigned ---", "--- Undefined Input ---"); also "Console Voltage Analysis Scan" with "Console input signal count" and "Console scan timing". Any key ends it |
| `Conset` | Idle, Edit | `$C16E` | "=== Setting up - please wait ===": scans the console and sets up the input board tables from the loaded definition; "No definition file loaded" otherwise |
| `Conbrd` | Idle, Edit | `$C0D4` | "Console Input Board Analysis": counts the input boards and prints the scan size ("Console scan size is %dw inputs") |
| `Inpwat n` | any | `$6266` | Set the input settle (wait) count used by the scanner |
| `Test` | any | `$DD8C` | "Reset Line Timing Test": pulses the scanner reset line until a key is pressed |
| `Tstadr` | any | `$DDF4` | "Address selectors test routine": cycles the board address lines |
| `Tstinp` | any | `$DE5C` | "Input board test routine": shows the raw input words board by board |
| `Tstotp` | any | `$DFAA` | "Output board test routine": walks a bit across the output boards |
| `Kpd [-]n`, `B [-]n` | any | `$C86C` | Simulate console button `n` (keypad digit or control button; `-` releases). Buttons 12, 13, 22 and 23 are handled specially; others light indicator 11 |
| `Dsp` | any | `$BDBA` | Toggle the indicator-status window (two rows of indicator letters: `BRWRPRPOEWTC` / `ZNTAARSWRPAF`) |
| `MI` | any | `$8DB0` | "---- MIDI Input Messages ----": shows incoming MIDI bytes until a key is pressed |
| `MO n` | any | `$8E4E` | Send a MIDI byte/value `n` to the output (test) |
| `MB n` | any | `$8E68` | MIDI test with value `n` |
| `MM` | any | `$8E82` | "----- Midi Input Message Map -----": table of which message types (Note Off/On, Key Pres, Ctrl Chng, Prgm Chng, Chnl Pres, Pitch Bend, Sys Msg) are accepted per channel `CHN-n` |

## Edit mode (definition editor)

`Edit` enters the editor; `RunEdit` enters it from Run mode with only `Piz` and
`Rit` available ("edit pizz & reit times"). The editor table is at `$F19E`;
each list command opens a window with the prompt `Edit: =>` and shows the items
of that list with their fields. "--- No items defined yet ---" for an empty
list; "Illegal Edit Command" otherwise.

| Command | List |
|---|---|
| `Kbd`, `K` | Keyboards: Keyboard name, Midi address |
| `Rnk`, `R` | Ranks: Rank name, Couple from/to rank, Bottom/Top note limit, Pitch offset(s) (32', 16', 8' … 1-1/7) |
| `Unt`, `U` | Units (outputs): Unit name, Signal type, Location, Output address, Minimum/Maximum "on" time, Trigger on key-up, Reiterate cycle time, Duty-cycle, Weighted outputs 1–8, Midi channel/note number, Velocity value |
| `Stp`, `S` | Stops: Stop name, Stop hardware type (Button or switch, Dual magnetic stop, Reversible button, Dual-contact drawknob …), Stop/Button contact address, ON/OFF magnet address, ON/OFF contact address, Indicator address, Combination status, Record/play status, Function list |
| `Lnk`, `L` | Links: Link name, Algorithm, Functions |
| `Fnc`, `F` | Functions: Function name, Function type (Divisional coupler, Normal rank output, Normal trap output, Direct unit output, Division unison off, Keyboard sustain/legato/sostenuto, Transposer, Melody couplers, Function multiplier, Pizzicato/Reiterate modifier, Channel coupler, Channel output, Stop reverser, Midi program change, Midi controller outputs …), Keyboard name, Aux keyboard name, Division name, Couple from/to division, Couple the couplers, Special function, Rank/Trap/Unit name, Transposer type, Change value, Controlled stops, Modified function, Channel fields, Midi fields |
| `Ctl`, `C` | Control buttons: Control button name, Control button type (Keypad digit #1–#0, General clear, Current file display, Overwrite files, Record/Play setup, start/stop, finish, Combination load/save, File number down/up, hex digits …), Input address |
| `Ind`, `I` | Indicators: Indicator type (Disk busy, Organ running, General wait, Record active, Playback active, Record ready, Record/play pause, File overwrite, Error, Disk write protected, Transposer active, Display current file), Output address |
| `Pst`, `P` | Pistons: Piston name, Piston input address, Set piston, Range piston |
| `Piz` | Pizzicato timing (also in RunEdit) |
| `Rit` | Reiterate timing (also in RunEdit) |
| `Chn` | Analog channels: Channel name, Channel type (Expression, Crescendo, Tempo control, Pipe chambers, Console), Record channel |
| `Cin` | Channel inputs: Input item name, Output channel name, Input contact address, Output value (0-255), Analog sensitivity |
| `Cot` | Channel outputs: Output item name, Output function, Channel value |
| `Spf` | Special functions: Tempo button, Tempo control, Metronome unit, Downbeat unit, Play/record switch, Magnet pulse time, Panel up/down speed, Console polarity, sensitivity, scan timing, Metronome on/off, Debounce time, Sequence name, Track number, Sync to sequence/measure, Start sync at, Begin/End play at |
| `Clear` | "Definition cleared": start a new, empty definition |
| `Add` | Add items to the current list: "Item(s) added" |
| `Cpy x TO y`, `/CPY x TO y(n)` | Copy item `x` to `y` (optionally `n` items): "Item copied"; "Format is /CPY x TO y or /CPY x TO y(n)" |
| `Rep(n)`, `/REP(n)+i`, `/REP(n)-i` | Repeat the last item `n` times, stepping addresses by `i`: "Item repeated"; "Format is /REP(n) or /REP(n)+i or /REP(n)-i" |
| `Load`, `Save` | As in Idle mode |

I/O addresses in the editor are written `AA-A1`: board letters `AA`…`PP` and
pin `A1`…`P8` (`sys_parseio`, `$36AE`). Yes/no fields print `yes`/`no`,
polarity `Ground`/`Hot`, status `Active`/`Inactive`. The internal layout of the
definition file is being worked out separately.

## Version 189 differences

Removed: `Topc`, `Frompc`, `Pcdisk`, `View`, `Turbo`. Added: `Optimiz` (Edit
mode only: "Optimizing unnecessary links…", "Removing inactive links…",
"Optimizing unnecessary functions…", "Removing inactive functions…",
"Definition optimization is complete"), `Ref` in the editor ("Function
references", fields Reference name, Function), new function types "Function
delay" (Function to delay, Function "on"/"off" delay), "Activate a piston" and
"Function command" (a console command string executed by the new FNC task:
"Illegal Function Command"), and a hidden `:` command that hands its line to
that task. Everything else is the same.
