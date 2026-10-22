#!/usr/bin/env python3
"""Devtronix Model 264 floppy file system (as implemented by System Monitor 2.6).

Builds on ../boot-rom/devdisk.py.  Everything here was derived from the
monitor disassembly (monitor-183.asm, FIL task at $3EEA) and checked against the
disk images; see README.md for the layout.

usage:
  devfs.py SIDE0 [SIDE1]                      list the directory
  devfs.py SIDE0 [SIDE1] --extract SLOT OUT   write a file's bytes (header excluded)
  devfs.py SIDE0 [SIDE1] --header SLOT        hex dump of a file's header sector
  devfs.py SIDE0 [SIDE1] --events SLOT [-n N] decode a Track/Song file's event stream
           ... --events SLOT -d D1            the same, stops and keys named from definition D1
  devfs.py SIDE0 [SIDE1] --check              compare the allocation bitmap with the files

SIDE0/SIDE1 are the per-side *_s0 / *_s1 images (409600 bytes each); a single
819200-byte *.img (side 0 then side 1) also works.
"""
import argparse, pathlib, struct, sys

SECTOR = 1024
SPT = 5

def w16(buf, off):
    """16-bit field as the 68000 in this machine sees it: low byte first."""
    return struct.unpack_from("<H", buf, off)[0]

# ----------------------------------------------------------------------------- disk
class Disk:
    def __init__(self, side0, side1=None):
        img = pathlib.Path(side0).read_bytes()
        if side1:
            self.sides = [img, pathlib.Path(side1).read_bytes()]
        elif len(img) == 2 * 80 * SPT * SECTOR:
            self.sides = [img[:len(img) // 2], img[len(img) // 2:]]
        else:
            self.sides = [img]
        self.boot = self.read_logical(0, double_sided=False)
        self.double_sided = bool(self.boot[0] & 1)
        self.is_system = self.boot[1] == 0xF2
        self.total_sectors = w16(self.boot, 2)
        self.label = self.boot[0x1C:0x36].split(b"\0")[0].decode("latin-1")
        self.boot_header = w16(self.boot, 0x36)
        self.load_address = w16(self.boot, 0x38)

    def read_logical(self, n, double_sided=None):
        ds = self.double_sided if double_sided is None else double_sided
        track, sec = divmod(n, SPT)
        side = 0
        if ds:
            track, side = track >> 1, track & 1
        if side >= len(self.sides):
            raise IOError(f"sector {n} is on side {side}, which was not given")
        off = track * SPT * SECTOR + sec * SECTOR
        data = self.sides[side][off:off + SECTOR]
        if len(data) != SECTOR:
            raise IOError(f"sector {n} beyond the end of the image")
        return data

    # -- directory: boot block +$6C, 4-byte entries {number, letter, header sector}
    def directory(self):
        out, off = [], 0x6C
        while off + 4 <= 0x200:
            number, letter = self.boot[off], self.boot[off + 1]
            if letter & 0x80:          # $FFFFFFFF terminator
                break
            out.append(DirEntry(self, chr(letter), number, w16(self.boot, off + 2)))
            off += 4
        return out

    def find(self, slot):
        slot = slot.upper()
        for e in self.directory():
            if e.slot == slot:
                return e
        raise KeyError(f"no file in slot {slot}")

    # -- allocation bitmap: boot block +$200, bit (n-1) set = sector n in use
    def used(self, n):
        if n == 0:
            return True
        b = self.boot[0x200 + (n - 1) // 8]
        return bool(b >> ((n - 1) % 8) & 1)

    def free_sectors(self):
        return sum(1 for n in range(1, self.total_sectors) if not self.used(n))

class DirEntry:
    TYPES = {"A": "system", "D": "definition", "C": "combination", "T": "track/song"}

    def __init__(self, disk, letter, number, header_sector):
        self.disk, self.letter, self.number, self.header_sector = disk, letter, number, header_sector
        self.slot = f"{letter}{number}"
        self.header = disk.read_logical(header_sector)
        self.last_bytes = w16(self.header, 2)          # bytes used in the last sector
        self.name = self.header[4:0x1E].split(b"\0")[0].decode("latin-1").rstrip()
        self.header_ok = self.header[0x1D] == 0        # monitor's "header record contains trash" test
        self.extents = []
        off = 0x40
        while off + 4 <= SECTOR:
            start, length = w16(self.header, off), w16(self.header, off + 2)
            if start == 0:
                break
            self.extents.append((start, length)); off += 4

    @property
    def type(self):
        return self.TYPES.get(self.letter, "?")

    @property
    def sectors(self):
        return [s for a, n in self.extents for s in range(a, a + n)]

    @property
    def size(self):
        n = len(self.sectors)
        return 0 if n == 0 else (n - 1) * SECTOR + self.last_bytes

    def read(self):
        data = b"".join(self.disk.read_logical(s) for s in self.sectors)
        return data[:self.size]

# ----------------------------------------------------------------------------- tracks
# Event classes, from the table at $D93A (read in raw byte order) and the
# recorder/player code.  Pulses are 1/96 beat; 192 per second at the default
# tempo of 120.
def iter_events(data):
    """Yield (offset, time_pulses, kind, info) for a Track/Song file.

    kind / info:
      "key"      (keyboard 1-16, key number 1-121, on: bool)
      "stop"     (stop number, on: bool)
      "channel"  (analog channel 1-16, value 0-255)
      "sync"     (stops that are on, channel values or None, stop count, unknown
                  sub-record or None) -- a sync block, see README
      "midi"     bytes of a MIDI message
      "console"  code 0-15 (ignored on playback)
      "check"    bytes of a check record
      "code"     the raw byte for $E0-$EF, $FA and anything else
      "end"      None, the $FF terminator
    Delta-time bytes are consumed silently.  The pulse clock is 96 per beat.
    """
    pos, t = 0, 0
    while pos < len(data):
        b = data[pos]; start = pos; pos += 1
        if b < 0x80:                                   # delta time, 1 byte
            t += b
            continue
        if b <= 0xBF:                                  # key event
            key = data[pos]; pos += 1
            yield start, t, "key", ((b & 0x0F) + 1, key, bool(b & 0x20))
        elif b <= 0xCF:
            yield start, t, "console", b & 0x0F
        elif b <= 0xDF:
            val = data[pos]; pos += 1
            yield start, t, "channel", ((b & 0x0F) + 1, val)
        elif b in (0xF0, 0xF1):
            stop = data[pos] << 8 | data[pos + 1]; pos += 2
            yield start, t, "stop", (stop, b == 0xF1)
        elif b == 0xF7:
            status = data[pos]
            ln = 3 if status < 0xC0 or status >= 0xE0 else 2
            if status >= 0xF0: ln = 1
            msg = data[pos:pos + ln]; pos += ln
            yield start, t, "midi", bytes(msg)
        elif b == 0xF8:                                # sync block
            stops_on, values, cnt, unknown = [], None, None, None
            while True:
                sub = data[pos]; pos += 1
                if sub == 0:
                    break
                if sub in (1, 5):
                    cnt = data[pos] << 8 | data[pos + 1]; pos += 2
                    bits = data[pos:pos + (cnt + 7) // 8]; pos += len(bits)
                    stops_on = [i + 1 for i in range(cnt) if bits[i // 8] >> (i % 8) & 1]
                elif sub == 6:
                    n = data[pos]; pos += 1
                    values = list(data[pos:pos + n]); pos += n
                else:
                    unknown = sub; break
            yield start, t, "sync", (stops_on, values, cnt, unknown)
        elif b == 0xF9:
            yield start, t, "endsync", None
        elif b == 0xFB:
            ln = data[pos]; body = data[pos + 1:pos + 1 + ln]; pos += 1 + ln
            yield start, t, "check", bytes(body)
        elif b == 0xFC:
            t += data[pos] << 8 | data[pos + 1]; pos += 2
            continue
        elif b == 0xFD:
            t += int.from_bytes(data[pos:pos + 4], "big")
            pos += 4
            continue
        elif b == 0xFE:                                # end of 1 KB block
            pos = (start // SECTOR + 1) * SECTOR
            continue
        elif b == 0xFF:
            yield start, t, "end", None
            return
        else:
            yield start, t, "code", b

def decode_events(data, limit=None, stop_names=None, key_label=None):
    """Yield (offset, time_pulses, text) for a Track/Song file (see iter_events).
    stop_names (stop number -> text, devdef.Definition.stop_labels) labels the
    stop events; key_label(kbd, key) -> text or None
    (devdef.Definition.key_label) names the keys."""
    n = 0
    for off, t, kind, info in iter_events(data):
        if limit is not None and n >= limit and kind != "end":
            yield off, t, "... (truncated)"
            return
        if kind == "key":
            kbd, key, on = info
            label = key_label(kbd, key) if key_label else None
            txt = f"key {'on ' if on else 'off'} {label or f'kbd {kbd} key {key}'}"
        elif kind == "console":
            txt = f"console change ${info:X}"
        elif kind == "channel":
            txt = f"channel {info[0]} = {info[1]}"
        elif kind == "stop":
            txt = f"stop {'on ' if info[1] else 'off'} {info[0]}"
            if stop_names and info[0] in stop_names:
                txt = f"{txt:<13} {stop_names[info[0]]}"
        elif kind == "midi":
            txt = "midi " + info.hex(" ")
        elif kind == "sync":
            stops_on, values, cnt, unknown = info
            parts = []
            if cnt is not None:
                parts.append(f"{cnt} stops, on: {stops_on}")
            if values is not None:
                parts.append(f"channels {values}")
            if unknown is not None:
                parts.append(f"sub-record {unknown}?")
            txt = "sync block: " + "; ".join(parts)
        elif kind == "endsync":
            txt = "end of sync block"
        elif kind == "check":
            txt = f"check record {info.hex(' ')}"
        elif kind == "end":
            yield off, t, "end of track"
            return
        elif kind == "code":
            if 0xE0 <= info <= 0xEF:
                txt = f"unused code ${info:02X}"
            elif info == 0xFA:
                txt = "code $FA (ignored)"
            else:
                txt = f"code ${info:02X}"
        n += 1
        yield off, t, txt

def fmt_time(pulses, tempo=120.0):
    sec = pulses * 60.0 / (96 * tempo)
    beats, pulse = divmod(pulses, 96)
    meas, beat = divmod(beats, 4)
    return f"{sec:8.3f}s  {meas + 1:3d}:{beat + 1}:{pulse:02d}"

# ----------------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("side0"); ap.add_argument("side1", nargs="?")
    ap.add_argument("--extract", nargs=2, metavar=("SLOT", "OUT"))
    ap.add_argument("--header", metavar="SLOT")
    ap.add_argument("--events", metavar="SLOT")
    ap.add_argument("-n", type=int, default=None, help="max events to print")
    ap.add_argument("--tempo", type=float, default=120.0, help="BPM assumed for the time column")
    ap.add_argument("-d", metavar="SLOT", help="with --events: name stops and keys from this definition "
                    "(a D slot on the same disk, or an extracted definition file)")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    d = Disk(a.side0, a.side1)
    if not d.is_system:
        print("not a system disk (boot byte 1 != $F2); no directory")
        return
    if a.extract:
        e = d.find(a.extract[0]); data = e.read()
        pathlib.Path(a.extract[1]).write_bytes(data)
        print(f"{e.slot} {e.name!r}: wrote {len(data)} bytes to {a.extract[1]}")
        return
    if a.header:
        e = d.find(a.header)
        for off in range(0, 0x80, 16):
            ch = e.header[off:off + 16]
            print(f"{off:03X}  {ch.hex(' ')}  {''.join(chr(c) if 32 <= c < 127 else '.' for c in ch)}")
        print("extents (start, length):", e.extents)
        return
    if a.events:
        e = d.find(a.events); data = e.read()
        print(f"{e.slot} {e.name!r}: {len(data)} bytes; times assume {a.tempo:g} BPM")
        stop_names = key_label = None
        if a.d:
            from devdef import Definition    # devdef imports this module
            try:
                if pathlib.Path(a.d).is_file():
                    defn = Definition(pathlib.Path(a.d).read_bytes()); what = a.d
                else:
                    de = d.find(a.d)
                    if de.letter != "D":
                        raise SystemExit(f"{de.slot} is a {de.type} file, not a definition")
                    defn = Definition(de.read()); what = f"{de.slot} {de.name!r}"
            except (ValueError, KeyError, IndexError, struct.error) as err:
                raise SystemExit(f"error: definition {a.d}: {err}")
            stop_names, key_label = defn.stop_labels(), defn.key_label
            print(f"stops and keys named from {what}")
        for off, t, txt in decode_events(data, a.n, stop_names, key_label):
            print(f"{off:06X}  {t:8d}  {fmt_time(t, a.tempo)}  {txt}")
        return

    print(f"Disk {d.label!r}: {'double' if d.double_sided else 'single'} sided, {d.total_sectors} sectors, "
          f"{d.free_sectors()} free; boot file header at sector {d.boot_header}, load ${d.load_address:04X}")
    print(f"{'slot':5} {'type':12} {'name':26} {'bytes':>7} {'secs':>4} {'hdr':>4}  extents")
    used_by_files = {0}
    for e in d.directory():
        flag = "" if e.header_ok else "  ** header record contains trash **"
        print(f"{e.slot:5} {e.type:12} {e.name:26} {e.size:7d} {len(e.sectors):4d} {e.header_sector:4d}  {e.extents}{flag}")
        used_by_files.add(e.header_sector); used_by_files.update(e.sectors)
    if a.check:
        marked = {n for n in range(1, d.total_sectors) if d.used(n)} | {0}
        lost = sorted(marked - used_by_files); unmarked = sorted(used_by_files - marked)
        print(f"bitmap: {len(marked)} used; {len(lost)} marked but not in any file"
              f"{' (' + str(lost[:20]) + ')' if lost else ''}; {len(unmarked)} in files but not marked"
              f"{' (' + str(unmarked[:20]) + ')' if unmarked else ''}")

if __name__ == "__main__":
    main()
