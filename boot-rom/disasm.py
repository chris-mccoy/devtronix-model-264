#!/usr/bin/env python3
"""Linear-sweep 68000 disassembly of the Devtronix loader ROM.

usage: disasm.py ROM.bin [--base 0x800000] [--data START-END ...]
Ranges given with --data are dumped as hex/ASCII instead of being decoded.
"""
import argparse, pathlib
from capstone import Cs, CS_ARCH_M68K, CS_MODE_M68K_000

def parse_range(s):
    a, b = s.split("-")
    return int(a, 16), int(b, 16)

ap = argparse.ArgumentParser()
ap.add_argument("rom")
ap.add_argument("--base", type=lambda x: int(x, 16), default=0x800000)
ap.add_argument("--data", nargs="*", default=[], type=parse_range,
                help="ROM-offset ranges (hex, inclusive-exclusive) to show as data")
args = ap.parse_args()

rom = pathlib.Path(args.rom).read_bytes()
md = Cs(CS_ARCH_M68K, CS_MODE_M68K_000)
data_ranges = sorted(args.data)

def in_data(off):
    for a, b in data_ranges:
        if a <= off < b:
            return b
    return None

off = 0
while off < len(rom):
    end = in_data(off)
    if end is not None:
        while off < end:
            chunk = rom[off:min(off + 16, end)]
            hx = " ".join(f"{b:02x}" for b in chunk)
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            print(f"{args.base+off:06X}  {hx:<48} |{asc}|")
            off += len(chunk)
        continue
    # decode one instruction at a time so a bad decode does not swallow the rest
    insns = list(md.disasm(rom[off:off + 10], args.base + off, count=1))
    if not insns:
        w = rom[off:off + 2]
        print(f"{args.base+off:06X}  {w.hex():<22} dc.w    ${w.hex()}")
        off += 2
        continue
    i = insns[0]
    print(f"{i.address:06X}  {i.bytes.hex():<22} {i.mnemonic:<8}{i.op_str}")
    off += i.size
