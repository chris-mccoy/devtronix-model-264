# Devtronix Model 264 — what has been found

The Devtronix Model 264 is a pipe-organ relay and combination action with a
record/playback facility, built around a Motorola 68000. This project reverse
engineers it from a 2011 Bus Pirate dump of its boot ROM and 2020 flux-level
dumps of its floppies, so that the performances recorded on those floppies can
be recovered. This file is the index and the one-page summary; the detailed
write-ups are linked from each section. Work done 16 October 2026.

| Folder | Contents |
|---|---|
| [`../boot-rom/`](../boot-rom/README.md) | Boot ROM ("Loader Revision C.04"): annotated disassembly, memory and I/O maps, disk reader |
| [`../system-monitor/`](../system-monitor/README.md) | The operating software (System Monitor 2.6): disassembly, file system, file formats, all tools |
| [`../system-monitor/COMMANDS.md`](../system-monitor/COMMANDS.md) | Every command the monitor's terminal accepts |
| [`../renders/INDEX.md`](../renders/INDEX.md) | Catalogue of every recording, rendered to MIDI |
| [`../decoded-images/`](../decoded-images/README.md) | Sector images decoded from the flux dumps, plus every HFE image |

Python tools run with `../.venv/bin/python` (capstone and pypdf are installed there).
Nothing under `disk-images/` or `devtronix-hardware/` is ever modified.

## The machine

- **CPU** Motorola 68000; a "Dimension-030" 68030 accelerator option exists
  (the monitor enables its cache with `movec CACR`).
- **Memory** 512 KB RAM at `$000000`; 8 KB boot ROM at `$800000`.
- **I/O** MC68681 DUART at `$FFFFFE21` (channel A = terminal, 9600 baud;
  channel B = modem, 1200 baud), MC6840 timer at `$FFFFFE11` (1 ms tick, tempo
  clock), WD179x floppy controller with glue at `$FFFFFFE0`, console scanner
  (input boards, magnet output boards, swell-shoe A/D) at `$FFFFFF80`, and a
  two-digit status display at `$FFFFFE00` that shows boot codes and then the
  sector being read.
- **Terminal** TeleVideo/ADM-3A escape sequences (`ESC =` cursor address,
  `ESC Y`, `ESC T`).

### Byte order: read this before touching any dump

Strings are stored in byte-address order but **16-bit words are stored low
byte first**. Longs are two little-endian words, high word first. This is
visible in both the ROM dump and the flux-level floppy images, and the
firmware itself relies on it. Rules: swap the two bytes of every word before
disassembling; read strings as-is; read 16-bit fields little-endian. The
hardware mechanism (probably a byte-lane swap on byte-sized bus cycles) has not
been confirmed on the board.

## Boot ROM (Loader Revision C.04)

Relocates itself to RAM at `$07E000`, auto-detects a terminal by ringing BEL on
each port and baud rate and waiting for ESC, then offers "Hit return to boot
from disk" / "Hit $ to download across modem". Boot reads logical sector 0,
checks the `$F2` signature, finds the system-monitor file through a header
sector and an extent list, zeroes RAM below the load address, loads the file
and jumps to it. The modem path receives checksummed 1 KB blocks. The 2011 dump
covers only the first 2 KB of what is probably an 8 KB ROM pair; the loader
fits in it, but the rest of the ROM is unread.

## System Monitor 2.6 (183), dated 05/11/93

74 KB of hand-written 68000 assembly: a small multitasking kernel (ten tasks,
62 system calls through `trap #0`, a 28-function disk service through
`trap #1`, a 1 ms timer wheel through `trap #3`), a text-window system, a
command line, the organ definition editor, the console scanner and relay
logic, and the recorder/player. Version 189 (06/01/94) is also on the disks and
is 93 % identical; nothing that matters for the music changed.

## File system

- 1024-byte sectors, 5 per track, 80 cylinders, 2 sides: 800 sectors, 800 KB.
  Logical sector *n* → track n/5, sector n%5+1; cylinder = track/2, side = track&1.
- Boot block (sector 0): `$F2` signature, volume label at `$1C`, boot pointer
  at `$36/$38`, **directory at `$6C`** (4-byte entries: slot number, slot letter,
  header sector), **allocation bitmap at `$200`**.
- Files live in *slots*: a letter and a number, `A4`, `T12`. The letter is the
  type: `A` system monitor, `D` organ definition, `C` combination (piston)
  settings, `T` track/song recording. `D1` and `C1` autoload; `C99` is the
  autosave slot. The console's two-digit "File #" display shows the slot number.
- Each file has a header sector: bytes used in the last sector at `+2`, name at
  `+4`, extent list of (first sector, count) word pairs at `+$40`.

`system-monitor/devfs.py` lists, checks and extracts; `fluxdecode.py` turns
KryoFlux streams or HFE files into sector images.

## File formats

- **Track / Song (`T`)**: a byte stream of time deltas (1/96 beat, 192 per
  second at the default tempo of 120, which is not stored in the file) and
  events: key on/off per keyboard, stop on/off, analog channel (swell shoe)
  values, MIDI passthrough, sync blocks carrying the full stop state, end of
  block, end of track. `devfs.py --events` decodes one.
- **Definition (`D`)**: a container of typed lists (keyboards, ranks, units,
  stops, links, functions, pistons, channels, ...). Keys and pipes share one
  121-note scale with note 25 = 8' C. A stop sounds a rank pipe at key + pitch
  offset through a link expression and a rank-output function. `devdef.py`
  dumps one like the editor's list commands.
- **Combination (`C`)**: 6-byte header, then per piston an OFF bitmap and an
  ON bitmap over the stops; their union is the piston's range. Decoded from the
  Set/Range/piston code. `devcomb.py` decodes one.
- `dev2midi.py` renders a track with its definition to a standard MIDI file,
  one channel per keyboard, or through stops and ranks with `--ranks`.

## The collection

- 56 image sets, 54 of them Devtronix system disks (many are duplicate dumps of
  the same floppy). Two are MS-DOS disks, not Devtronix.
- **844 track files**, all rendered: 1664 MIDI files in `renders/`, 41 tracks
  flagged for decode problems, 12 directory entries that are corrupt. Jerry's
  tour disc holds twelve named tunes (Danny Boy, Joy To The World, Stars And
  Stripes Forever, ...); the eighteen "58 Note Player" disks hold unnamed
  recordings for a one-keyboard roll player. "Danny Boy" and "Joy To The
  World" were checked note by note and are right; nothing has been listened to
  yet.
- **94 definition entries, 50 distinct by content**, about eight real organs:
  Jerry's "OLD ORGAN DEFINITION" (11 keyboards, 710 stops, 60 ranks), the
  1995 tour disc (467 stops, 109 ranks), New Console 12-08-93 / 2-13-95 (417
  stops, 81 ranks), the PCC organ family (250 stops, 35 ranks, nine copies),
  McCoy's SCHANTZ 66 and OLD SWELL (142 stops, 70 ranks), and small test,
  player and MIDI-control definitions.
- **28 combination files** on the real-organ disks, none on the player disks.
  Several were saved under an older definition than the disk's `D1`.
- All 42 HFE images are gathered in `decoded-images/`. Two disks, `os-backup`
  and `startupa`, exist only as HFE and have not been decoded. Four HFEs have
  84 tracks because KryoFlux reads past cylinder 79; the format uses 80 and
  the extra tracks hold nothing.
- The side files (`*_s0`, `*_s1`) are per-side images, cylinder by cylinder;
  the `.img` files are side 0 then side 1. A standard track-interleaved image
  for an emulator needs the two sides interleaved in 5120-byte chunks, with the
  geometry declared; the HFE files avoid that.

## Open questions

1. Confirm the byte-lane arrangement and the ROM size on the CPU board; re-dump
   ROM addresses `$400`–`$FFF`.
2. Listen to the renders; confirm the 120 BPM tempo assumption.
3. Decode `os-backup` and `startupa` from their HFEs.
4. Still unknown in the definition: a few `Stp` body fields, the `Piz`/`Rit`
   timing tables. `dev2midi.py --ranks` does not model traps, tremulants or
   expression.
5. The relay logic itself (`task_scn`, key and stop events) is traced but not
   annotated in depth.
