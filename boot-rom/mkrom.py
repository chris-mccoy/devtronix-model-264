#!/usr/bin/env python3
"""Build loader-c04.bin (big-endian 68000 image) from the ROM dump.

loader-c04.raw (the 2011 Bus Pirate dump, devtronix.rom.merged, made by devmerge.py) holds each 16-bit ROM word as
(bits 0-7, bits 8-15).  On this machine that is also the *byte-address* order
the CPU sees for strings, but 68000 instruction words come out byte-swapped,
so for a disassembler we swap the two bytes of every word.
"""
import pathlib, sys
src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                   "boot-rom/loader-c04.raw").read_bytes()
out = bytearray(len(src)); out[0::2] = src[1::2]; out[1::2] = src[0::2]
dst = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "boot-rom/loader-c04.bin")
dst.write_bytes(out)
print(f"{dst}: {len(out)} bytes; SSP={int.from_bytes(out[0:4],'big'):#010x} PC={int.from_bytes(out[4:8],'big'):#010x}")
