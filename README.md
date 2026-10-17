# Devtronix Model 264

Reverse engineering of the Devtronix Model 264, a Motorola 68000-based pipe-organ
relay and combination action with a record/playback facility, from its boot ROM
and its floppy disks. The aim was to recover the performances recorded on the
disks, and that has been done: every recording now renders to a standard MIDI file.

![Devtronix Front](img/dev.jpg)

Start with **[docs/README.md](docs/README.md)**, the one-page summary of what was
found, with links to the detailed write-ups:

- [boot-rom/](boot-rom/README.md): the boot ROM, annotated disassembly, memory and I/O maps
- [system-monitor/](system-monitor/README.md): the operating software, the file system,
  the Track, Definition and Combination file formats, and the tools that read them

## What is not in this repository

The floppy disk images, the flux dumps, the HFE images, the decoded sector images
and the rendered MIDI files are deliberately left out (`disk-images/`,
`decoded-images/`, `renders/`) until permission to publish the recordings is
settled. Links into those folders from the write-ups will not resolve here. The
tools work on a local copy that has them.

The tools are Python 3; `capstone` is needed for the disassemblers:

```
python3 -m venv .venv && .venv/bin/pip install capstone
```
