# Devtronix Model 264

This repository contains reverse engineering and analysis of the 
Devtronix Model 264, a Motorola 68000-based pipe-organ
relay and combination action with a record/playback facility, from its boot ROM
and its floppy disks. The 264's computer is Devtronix's own board, built to reflect 
the design of the [Alpha Microsystems](https://en.wikipedia.org/wiki/Alpha_Microsystems)
68000-based systems, which is why 16-bit words in its memory and on its disks are stored low
byte first: Alpha Micro wired its 68000 machines with the data-bus bytes swapped
to stay compatible with the little-endian WD16 of its earlier AM-100 line (see Cameron
Kaiser's [Alpha Micro AM-1000E and AM-1200 refurb](https://oldvcr.blogspot.com/2026/03/refurb-weekend-double-header-alpha.html)
for a hands-on account of these machines).

The aim was to recover and preserve the performances recorded on the disks I
have, and that has been done: every recording now renders to a standard MIDI
file.  Many of the artists that performed are no longer with us.

Most (all?) of this code was written by Dick Wilcox and Tim Rickman, both
recipients of the
[American Theatre Organ Society (ATOS) Award for Industry Achievement](https://www.atos.org/programs-awards/industry-achievement).

----

![Devtronix Front](img/dev.jpg)

Start with **[docs/README.md](docs/README.md)**, the one-page summary of what was
found, with links to the detailed write-ups:

- [boot-rom/](boot-rom/README.md): the boot ROM, annotated disassembly, memory and I/O maps
- [system-monitor/](system-monitor/README.md): the operating software, the file system,
  the Track, Definition and Combination file formats, and the tools that read them

## Links

- [devtronix.org](https://devtronix.org/): Dominic Cheshire's Devtronix organ fan site and repository.
- [Alpha Micro AM-1000E and AM-1200 refurb](https://oldvcr.blogspot.com/2026/03/refurb-weekend-double-header-alpha.html): Cameron Kaiser's hands-on account of the computer the 264 is built on.
- [ampm.floodgap.com](https://ampm.floodgap.com/): Cameron Kaiser's Alpha Micro site, served from a real Alpha Micro, with the company's history and a list of its models.

## What is not in this repository

The floppy disk images, the flux dumps, the HFE images, the decoded sector images
and the rendered MIDI files are deliberately left out (`disk-images/`,
`decoded-images/`, `renders/`) until permission to publish the recordings is
settled. Links into those folders from the write-ups will not resolve here. The
tools work on a local copy that has them.

The tools are Python 3, managed with [uv](https://docs.astral.sh/uv/): dependencies are in
`pyproject.toml` and locked in `uv.lock`.

```
uv sync                                   # one-time: create .venv with the locked packages
uv run system-monitor/devfs.py SIDE0 SIDE1   # run any tool
```
