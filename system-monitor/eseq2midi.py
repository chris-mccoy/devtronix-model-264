#!/usr/bin/env python3
"""
eseq2midi.py -- convert Yamaha Disklavier E-SEQ songs (DRC_NN.MDA) to standard MIDI files.

usage:
  eseq2midi.py FILE.MDA [FILE.MDA ...] [-o OUTDIR] [--keep-program]

The two MS-DOS disks (see dosdisk.py) hold songs recorded by a Disklavier's
DRC unit in Yamaha's E-SEQ format.  An .MDA file is an 87-byte header and the
event stream:

  $00      FE 00 00 FF FF 00 00 "COM-ESEQ", then 80 00 21 00 30 00 00 00 at $17
  $1F      dword: length of the event stream (the file is $57 + this)
  $24      tempo: BPM - 29 ($5B = 120 BPM)
  $27      the file's own 8.3 name
  $57      events

The events are MIDI channel messages, every one with its status byte (no
running status), between E-SEQ codes that use the MIDI system bytes:

  F3 n        delay n ticks            F4 lo hi    delay lo + 128*hi ticks
  F9 n p      bar line, time n/2^p     FB lo hi    tempo factor (1000 = 100 %)
  FF c        channel prefix           F0 .. F7    SysEx
  F1 00       start                    F2          end of song
  F6          padding, ignored

There are 384 ticks to the quarter note: every bar of the DRC recordings is
1536 ticks (4/4), and every delay is a multiple of 8 (~10 ms at 120 BPM).
The stream is copied into a format 0 MIDI file at division 384 with the
header's tempo, and the timing is left as recorded, silence before the first
note included.  The Disklavier's own pedal messages (CC 64 sustain, CC 67
soft, repeated as it samples them) and SysEx are kept as they are.

So that any General MIDI player sounds a grand piano, bank 0 / program 0
(Acoustic Grand Piano) is selected on every channel that plays notes, at the
start of the song, and any program change in the stream is set to 0 as well
(--keep-program leaves the stream's own programs alone).
"""
import argparse, pathlib, struct, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from dev2midi import Track, vlq  # noqa: E402

PPQ = 384
HEADER = 0x57
GRAND_PIANO = 0
DATA_BYTES = {0x80: 2, 0x90: 2, 0xA0: 2, 0xB0: 2, 0xC0: 1, 0xD0: 1, 0xE0: 2}

def parse(data):
    """Return (bpm, events, end tick); events are (tick, MIDI event bytes) or (tick, ('tempo'|'timesig', ...))."""
    if data[0:7] != b'\xfe\x00\x00\xff\xff\x00\x00' or data[7:15] != b'COM-ESEQ':
        raise ValueError('not a Yamaha COM-ESEQ file')
    length = struct.unpack_from('<I', data, 0x1F)[0]
    if HEADER + length != len(data):
        raise ValueError(f'stream length {length} does not match the file ({len(data)} bytes)')
    bpm = data[0x24] + 29
    i, t, events, ended = HEADER, 0, [], False
    while i < len(data):
        b = data[i]
        if b < 0x80:
            raise ValueError(f'stray data byte {b:#04x} at {i:#x}')
        if b < 0xF0:
            n = DATA_BYTES[b & 0xF0]
            events.append((t, data[i:i + 1 + n])); i += 1 + n
        elif b == 0xF3:
            t += data[i + 1]; i += 2
        elif b == 0xF4:
            t += data[i + 1] | data[i + 2] << 7; i += 3
        elif b == 0xF9:
            events.append((t, ('timesig', data[i + 1], data[i + 2]))); i += 3
        elif b == 0xFB:
            events.append((t, ('tempo', data[i + 1] | data[i + 2] << 7))); i += 3
        elif b == 0xFF:
            events.append((t, b'\xff\x20\x01' + bytes([data[i + 1] & 0x0F]))); i += 2
        elif b in (0xF0, 0xF7):
            j = data.index(0xF7, i + 1)
            events.append((t, b'\xf0' + vlq(j - i) + data[i + 1:j + 1])); i = j + 1
        elif b == 0xF1:
            i += 2
        elif b == 0xF6:
            i += 1
        elif b == 0xF2:
            ended = True; i += 1
            break
        else:
            raise ValueError(f'unknown E-SEQ code {b:#04x} at {i:#x}')
    if not ended or i != len(data):
        raise ValueError('no F2 end of song at the end of the stream')
    return bpm, events, t

def convert(data, name, keep_program=False):
    """Return (MIDI file bytes, summary dict)."""
    bpm, events, end = parse(data)
    tr = Track(name)
    tr.text(0, 'Yamaha Disklavier E-SEQ, converted by eseq2midi.py')
    tr.meta(0, 0x51, (60_000_000 // bpm).to_bytes(3, 'big'))
    notes = sorted({ev[0] & 0x0F for _, ev in events if isinstance(ev, bytes) and ev[0] & 0xF0 == 0x90 and ev[2]})
    if not keep_program:
        for ch in notes:
            tr.add(0, bytes([0xB0 | ch, 0x00, 0x00]))
            tr.add(0, bytes([0xB0 | ch, 0x20, 0x00]))
            tr.add(0, bytes([0xC0 | ch, GRAND_PIANO]))
    sig = None
    for t, ev in events:
        if isinstance(ev, tuple):
            if ev[0] == 'timesig' and ev[1:] != sig:
                sig = ev[1:]
                tr.meta(t, 0x58, bytes([ev[1], ev[2], 24, 8]))
            elif ev[0] == 'tempo':
                tr.meta(t, 0x51, (60_000_000_000 // (bpm * max(1, ev[1]))).to_bytes(3, 'big'))
            continue
        if ev[0] & 0xF0 == 0xC0 and not keep_program:
            ev = bytes([ev[0], GRAND_PIANO])
        tr.add(t, ev)
    midi = b'MThd' + struct.pack('>IHHH', 6, 0, 1, PPQ) + tr.chunk(end)
    ons = [t for t, ev in events if isinstance(ev, bytes) and ev[0] & 0xF0 == 0x90 and ev[2]]
    return midi, {'bpm': bpm, 'channels': notes, 'notes': len(ons), 'seconds': end * 60 / (bpm * PPQ),
                  'first_note': ons[0] * 60 / (bpm * PPQ) if ons else None}

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='+', metavar='FILE.MDA')
    ap.add_argument('-o', '--out', help='output folder (default: beside each input)')
    ap.add_argument('--keep-program', action='store_true', help="keep the stream's own program changes")
    a = ap.parse_args()
    for f in map(pathlib.Path, a.files):
        name = f'{f.parent.name} {f.stem}' if f.parent.name else f.stem
        midi, s = convert(f.read_bytes(), name, a.keep_program)
        out = (pathlib.Path(a.out) if a.out else f.parent) / (f.stem + '.mid')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(midi)
        m, sec = divmod(round(s['seconds']), 60)
        chans = ','.join(str(c + 1) for c in s['channels']) or '-'
        first = f"first note {s['first_note']:.1f} s" if s['notes'] else 'no notes'
        print(f"{f}: {s['notes']:6} notes on ch {chans:4} {m:2}:{sec:02} at {s['bpm']} BPM, {first} -> {out}")

if __name__ == '__main__':
    main()
