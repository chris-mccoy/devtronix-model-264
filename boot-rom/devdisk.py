#!/usr/bin/env python3
"""Read a Devtronix floppy the way the Loader C.04 ROM does.

Geometry (from the ROM): 1024-byte sectors, 5 per track, logical sector n ->
track n//5, sector-in-track n%5+1.  Double-sided disks (boot byte 0 bit 0):
cylinder = track>>1, side = track&1.  The *_s0 / *_s1 files are per-side
images of 80 cylinders x 5 sectors x 1024 bytes = 409600 bytes.

16-bit fields are stored little-endian in byte-addressed memory on this
machine (code must be byte-swapped to disassemble; strings are in order).

usage: devdisk.py SIDE0 [SIDE1] [--extract OUT.bin]
"""
import argparse, pathlib, struct

SECTOR = 1024
SPT = 5

def w16(buf, off):          # little-endian 16-bit word as the 68000 here sees it
    return struct.unpack_from("<H", buf, off)[0]

class Disk:
    def __init__(self, side0, side1=None):
        self.sides = [pathlib.Path(side0).read_bytes()]
        if side1:
            self.sides.append(pathlib.Path(side1).read_bytes())
        self.boot = self.read_logical(0, double_sided=False)
        self.double_sided = bool(self.boot[0] & 1)

    def read_logical(self, n, double_sided=None):
        ds = self.double_sided if double_sided is None else double_sided
        track, sec = divmod(n, SPT)
        side = 0
        if ds:
            track, side = track >> 1, track & 1
        off = track * SPT * SECTOR + sec * SECTOR
        img = self.sides[side]
        return img[off:off + SECTOR]

    def extents(self, header):
        """Extent table at header+0x40: (start_sector, length) word pairs, 0-terminated."""
        out, off = [], 0x40
        while True:
            start = w16(header, off); length = w16(header, off + 2)
            if start == 0:
                return out
            out.append((start, length)); off += 4

    def file_sectors(self, header):
        secs = []
        for start, length in self.extents(header):
            secs += list(range(start, start + length))
        return secs

ap = argparse.ArgumentParser()
ap.add_argument("side0"); ap.add_argument("side1", nargs="?")
ap.add_argument("--extract", help="write the system-monitor file here")
a = ap.parse_args()

d = Disk(a.side0, a.side1)
b = d.boot
print(f"boot byte0 = ${b[0]:02x} (double-sided={d.double_sided})  byte1 = ${b[1]:02x} (expect $f2)")
label = b[0x1c:0x2c].split(b"\0")[0]
print(f"label @$1c      = {label!r}")
hdr_sec = w16(b, 0x36); entry = w16(b, 0x38)
print(f"monitor header  = logical sector {hdr_sec}")
print(f"load/entry addr = ${entry:04x}  (RAM $0000-${entry:04x} is zeroed first)")
if b[1] != 0xF2:
    print("not a system disk: ROM would load logical sector 1 to address 0 and jump there")
    raise SystemExit
hdr = d.read_logical(hdr_sec)
print("header bytes 0..0x40:", hdr[:0x40].hex(" "))
ext = d.extents(hdr)
print("extents (start,len):", ext, "->", sum(l for _, l in ext), "sectors =",
      sum(l for _, l in ext) * SECTOR, "bytes")
secs = d.file_sectors(hdr)
data = b"".join(d.read_logical(s) for s in secs)
print(f"monitor image: {len(data)} bytes, loaded at ${entry:04x}-${entry+len(data):05x}")
print("first 32 bytes (disk order):", data[:32].hex(" "))
if a.extract:
    pathlib.Path(a.extract).write_bytes(data)
    print("wrote", a.extract)
