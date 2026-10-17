# Writing a Model 264 emulator

What an emulator of the Devtronix Model 264 has to provide, drawn from the boot ROM
and System Monitor disassemblies in this project. The machine is small: a 68000,
half a megabyte of RAM, four peripheral chips and two custom ports. The one unusual
requirement is the byte order of its memory. This document lists every component,
what the firmware expects of it, how to go about it in stages, and which emulation
framework fits.

## 1. The machine in one table

| Component | Address | What the firmware expects | Where it is documented |
|---|---|---|---|
| MC68000, 8 MHz | | Plain 68000 instruction set; the monitor also runs on a 68030 (Dimension-030) but needs nothing from it | [`../boot-rom/README.md`](../boot-rom/README.md) |
| RAM, 512 KB | `$000000`–`$07FFFF` | Sized at start-up by the monitor; vectors at `$0`, monitor loads at `$1032`, loader relocates to `$7E000`, reset SSP `$7F000` | boot ROM "Memory map" |
| Boot ROM, 8 KB | `$800000`–`$801FFF` | Two 2732A EPROMs; `loader-c04.bin` is the first 2 KB, the rest is `$FF` | boot ROM README |
| **Byte order** | all memory | 16-bit words are stored low byte first; bytes are in address order; see section 2 | boot ROM "Byte order" |
| MC68681 DUART, 3.6864 MHz crystal, IP2 = 8 MHz CPU clock | `$FFFFFE21`–`$FFFFFE3F`, odd bytes | Channel A = terminal 9600 (CSR `$BB`) or PC link 38400 (`$CC`); channel B = modem 300–38400 or MIDI at 31250 via the counter/timer (ACR `$40`, CTUR:CTLR = 8, CSR `$DD`); interrupt vector `$3C`, IMR `$33` | monitor "Serial ports and the MIDI baud rate" |
| MC6840 PTM | `$FFFFFE11`–`$FFFFFE1F`, odd bytes, 800 kHz clock | T1 = 1 ms system tick, level-6 interrupt (vector `$78`); T2 = tempo pulse (latch = 500000 / BPM, 96 per beat); T3 = one-shot used with `movep` to time key events | monitor "Hardware the monitor touches", "Timer" |
| WD2791 floppy controller | `$FFFFFFE0`–`$FFFFFFE3` | Command/status at `$E0`, sector at `$E2`, data (seek target) at `$E3`; commands `$08` restore, `$18` seek, `$84` read sector, `$A4` write sector, format | boot ROM "Floppy"; monitor "The floppy driver" |
| Floppy sector buffer | `$FFFFFFE4` (port), `$FFFFFFE5` (counter reset), `$FFFFFFE6` (drive/side latch, INTRQ in bit 1), `$FFFFFFE7` (`$80` run, `$84` write direction, `$8C` format, `$00` reset) | 2 KB SRAM between controller and CPU; the CPU streams a sector through the port, see section 3 | boot ROM "The sector buffer" |
| Status display | `$FFFFFE00` (write) | Two hex digits on the board; boot codes `A1 B1 B2 B3 C1 EE` and sector numbers | boot ROM "Status display codes" |
| Unknown port | `$FFFFFE03` (read once at reset), `$FFFFFE06` | Value discarded; return anything | boot ROM |
| Console scanner | `$FFFFFF80` data, `$FFFFFF82` control, `$FFFFFF84`/`$86` strobes | Writes an address, reads the input state in bit 15; outputs and the analog A/D by control word; see section 4 | monitor "The relay", "Console scanner hardware" |
| Terminal | on DUART channel A | Wyse WY-50 (default on most disks) or TeleVideo 950 escape sequences | monitor "Terminals" |

Nothing else is addressed by either program. The Dimension-030 is reached only
through `movec CACR`, which a plain 68000 core can treat as a no-op or an illegal
instruction the monitor never executes unless `Turbo` is typed.

## 2. The byte order

The 264 stores 16-bit words low byte first while bytes keep their natural addresses
(the Alpha Micro design the board follows). Our images, ROM and disks alike, are in
byte-address order, which is what the hardware sees. In an emulator this is a
three-line rule in the memory access layer, with no change to the CPU core:

```
read8 (a)  = mem[a]
read16(a)  = mem[a] | mem[a+1] << 8          (and the mirror for writes)
read32(a)  = read16(a) << 16 | read16(a+2)
```

A big-endian 68000 core asking for the word at an even address must receive the
value assembled this way, and instruction fetches are word reads, so the code in
`monitor-183.raw` and `loader-c04.raw` (byte-address order) runs as is. If a
framework insists on big-endian RAM, the equivalent trick is to load the
byte-swapped images (`*.bin`) and XOR the address with 1 on every byte-sized access.
Peripherals are 8-bit on the low byte lane and unaffected.

## 3. The floppy, without MFM

No flux or MFM emulation is needed. The firmware drives the controller like this,
and an emulator only has to honour the sequence:

1. Drive/side latch written to `$FFE6` (`$A1` side 0, `$B1` side 1, `$00` off).
2. Seek: cylinder written to `$FFE3`, command `$18` to `$FFE0`; the firmware then
   waits for INTRQ (`$FFE6` bit 1 set) and BUSY (`$FFE0` bit 0) clear.
3. Read: `$FFE5` cleared, `$FFE7 = $80`, sector number to `$FFE2`, command `$84`;
   wait for INTRQ and not BUSY. The emulator copies the 1024-byte sector into the
   buffer and resets the buffer pointer. The firmware then reads `$FFE4` 1024 times
   and expects successive bytes.
4. Write: `$FFE5` cleared, 1024 bytes written to `$FFE4`, `$FFE7 = $84`, command
   `$A4`; the emulator stores the buffer to the sector image and raises INTRQ.
5. Status bits the firmware checks: 7 NOT READY (it waits for it to clear), 6 WRITE
   PROTECT, 4 RNF, 3 CRC, 2 LOST DATA, 0 BUSY. Errors make the firmware pulse
   `$FFE7` low (reset), RESTORE and retry.

Sector images: the `*_s0` / `*_s1` files are one side each, cylinder c at offset
c×5120, sector r at (r−1)×1024, 80 cylinders. The monitor also knows a 512-byte,
9-sectors-per-track format, but no disk in the collection uses it.

## 4. The console scanner

An emulator that returns "nothing pressed" boots and runs the monitor fine. The
protocol, for a fuller model (see `../system-monitor/README.md`, "The relay"):

- Scan: control word `$1160` (or `$21E6`) to `$FF82`, then for each input write
  `address−1 | state<<15` to `$FF80` and read `$FF80`; bit 15 of the reply is the
  contact state (1 = open). A virtual console changes the reply for the addresses of
  the keys, stops and pistons it wants to press.
- Outputs: control `$3C00` (console boards) or `$3300` (chamber boards), data word
  `~(address−1)` with bit 15 clear for on, set for off. A model that logs these sees
  exactly which magnets the relay fires, which is the way to check `dev2midi.py`
  against the real logic.
- Analog inputs: control `$31xx`; the firmware does an 8-step successive
  approximation, reading bit 15 as the comparator result for DAC value `xx`.
- `$FF84` / `$FF86` are cleared by the tick handler while `pulse_hold` counts
  down; ignoring writes is fine.

Addresses follow the definition's encoding (`board1<<11 | board2<<7 | pin<<3 |
digit`, 1-based); MIDI pseudo addresses `$6001+` never reach the scanner.

### 4a. The DUART in detail

An emulated 68681 needs the baud-rate generator (set 1, since ACR bit 7 is 0 in the
monitor; the boot ROM uses set 2, where the codes `$BB`, `$66` and `$88` give the
same rates) and the **counter/timer in timer mode**: the monitor clocks it from
IP2, which the board ties to the 8 MHz CPU clock, with a preload of 8, and selects
it with CSR `$DD` to get 31250 baud for MIDI. An emulator can simply treat CSR
`$DD` on channel B as "MIDI rate" and route the bytes to a MIDI port. Interrupts:
RxRDY and TxRDY of both channels (IMR `$33`) on vector `$3C`; the handler reads
SRA/SRB and calls the installed hooks. OPCR is written once (`$0A`); the output
port is otherwise unused and the input port serves only as the timer clock.

## 5. What the terminal must understand

The loader prints TeleVideo sequences (`ESC =` row col, `ESC Y`, `ESC T`, `ESC . 0`).
The monitor uses the table selected by its `Term` type, which is baked into each
monitor image at offset 6: type 6, the Wyse WY-50, on nearly every disk. A terminal
window therefore needs the WY-50 set: `ESC =` cursor address, `ESC ;` clear, `` ESC ` n ``
cursor style, `ESC H ^B` / `ESC H ^C` line graphics with the digit-and-punctuation
box characters, or the TeleVideo equivalents if `Term 0` is used. The easiest route is
a translation layer to ANSI/VT100 in the emulator's console, or an existing Wyse
terminal emulation.

## 6. Stages, with what "working" looks like

1. **CPU + memory + display + DUART A.** Load `boot-rom/loader-c04.raw` at `$800000`,
   start at the reset vector. Working: the display shows `A1`, the banner "Devtronix
   Organ Control System Loader Revision C.04" appears, and pressing ESC during the
   BEL probe lands on "Hit return to boot from disk".
2. **Floppy with the sector buffer.** Working: "Loading system monitor" with one dot
   per sector, then the monitor's Idle screen; `Dir` lists the disk the same way
   `devfs.py` does; `Term`, `Ver`, `Mem` answer.
3. **6840 timer.** Working: the clock on the status line runs, tasks switch, `Run`
   enters Run mode and the scan-rate figure appears. Nothing happens on the console
   without a scanner model, which is expected.
4. **Scanner model and MIDI.** Working: `Play` of a track drives the output log; a
   virtual keyboard presses keys and the relay fires pipes; MIDI in through channel B
   reaches `midi_dispatch`.
5. **Extras.** Modem mode against a YMODEM peer; the PC link; the Dimension-030
   `movec` as a no-op so `Turbo` prints its message.

Each stage can be checked against this project's tools: the loader's expected output
is in `../boot-rom/loader-c04.asm`, the directory listings in `devfs.py`, the
terminal tables and command list in `../system-monitor/README.md` and `COMMANDS.md`.

## 7. Which framework

| Option | What you get for free | What you write | Verdict |
|---|---|---|---|
| **Standalone** (Musashi or another 68000 core in C, or any language with a 68k core) | the CPU | memory with the byte rule, DUART A as a terminal, 6840, floppy from sector images, display, scanner stub: a few hundred lines | fastest to the monitor's screen; best for settling details |
| **MAME** | 68000, `mc68681`, `ptm6840`, `wd2791` with floppy images and HFE support, a `wy50` terminal device, address maps with per-size handlers | a machine driver: address map, byte-swap handler, scanner device, buffer latch | best if other Devtronix owners should be able to run it; MAME has emulated general computers since it absorbed MESS |
| **QEMU** | the 68000 only | 68681, 6840, WD2791, scanner, and main RAM as an MMIO region to get per-size byte swapping | most work for the least return |

Recommended path: build the standalone emulator through stage 2 or 3 to prove the
component behaviour, then port it into a MAME driver reusing MAME's chip models.

## 8. Still unknown

- `$FFFFFE03` and `$FFFFFE06`, read once at start-up and discarded.
- The Dimension-030's bus interface, irrelevant unless its driver is emulated.
