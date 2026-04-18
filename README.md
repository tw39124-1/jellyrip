# jellyrip

A command-line tool for ripping DVDs into a [Jellyfin](https://jellyfin.org)-compatible media library. It uses MakeMKV to extract titles and copies them as MKV files. Everything is interactive — insert a disc, pick your titles, and walk away.

---

## Features

- Detects disc label automatically and prompts for title/year confirmation
- Scans all titles via MakeMKV and presents an interactive selection table
- Auto-identifies the main feature (longest title) vs. extras/bonus content
- Output: **direct MKV copy** (fast, lossless)
- Live progress display with spinner, percentage, and data throughput
- Saves extras into an `extras/` subdirectory alongside the main feature
- Triggers a Jellyfin library scan automatically after ripping
- No Python dependencies — stdlib only

---

## Requirements

### System tools

All three must be on your `PATH`:

| Tool | Purpose | Install |
|---|---|---|
| `makemkvcon` | DVD decryption and title extraction | See [MakeMKV forum](https://www.makemkv.com/forum/viewtopic.php?t=224) |
| `eject` | Tray control | Pre-installed on most Linux distros |
| `blkid` | Disc label detection | Pre-installed on most Linux distros |

### Python

Python 3.10+ is required. No third-party packages are needed.

### Hardware

- A DVD drive accessible at `/dev/sr0` (overridable with `--device`)
- Sufficient disk space: ~8 GB per disc

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd jellyrip
```

### 2. Install system dependencies

On Ubuntu/Debian:

```bash
sudo apt update
sudo apt install eject util-linux
```

For `makemkvcon`, follow the official build instructions on the [MakeMKV forum](https://www.makemkv.com/forum/viewtopic.php?t=224) — it is not available in standard package repositories.

Verify everything is on your PATH:

```bash
makemkvcon --version
eject --version
blkid --version
```

### 3. Configure the output directory

By default, ripped media is saved to `/mnt/raid1/media/movies`. Create it (or update `jellyrip/config.py` — see [Configuration](#configuration)):

```bash
sudo mkdir -p /mnt/raid1/media/movies
sudo chown $USER:$USER /mnt/raid1/media/movies
```

### 4. Set up Jellyfin integration (optional)

Create a `.env` file in the project root:

```
JELLYFIN_API_KEY=your_api_key_here
```

To get your API key: Jellyfin dashboard → Administration → API Keys → + (add key).

If `JELLYFIN_API_KEY` is not set, the Jellyfin scan step is silently skipped.

---

## Configuration

Edit the constants in [jellyrip/config.py](jellyrip/config.py):

```python
DEVICE = "/dev/sr0"                          # DVD drive device path (default, overridable via --device)
OUTPUT_ROOT = Path("/mnt/raid1/media/movies") # Where to save ripped media
JELLYFIN_URL = "http://localhost:8096"        # Jellyfin server address
DISC_READY_TIMEOUT = 60                       # Seconds to wait for disc to become readable
```

---

## Usage

```bash
python -m jellyrip
```

To use a specific DVD drive:

```bash
python -m jellyrip --device /dev/sr1
```

The script walks you through the full workflow interactively:

1. **Tray opens** — insert your DVD when prompted
2. **Disc detected** — label is read and cleaned; you confirm or override the title and year
3. **Title scan** — MakeMKV scans the disc and displays a table of all titles with duration, chapter count, and size
4. **Select titles** — enter numbers, ranges (`1-3`), or `all`; the main feature is highlighted automatically
5. **Confirm destination** — shows the output path before anything is written
6. **Rip and process** — live progress shown throughout
7. **Done** — Jellyfin scan triggered (if configured); disc is ejected automatically

To cancel at any point, press `Ctrl+C`. The script will clean up temporary files and eject the disc.

---

## Output structure

```
/mnt/raid1/media/movies/
└── Movie Title (2008)/
    ├── Movie Title (2008).mkv    ← main feature
    └── extras/
        ├── Extra - 0h 05m 30s.mkv
        └── Behind the Scenes.mkv
```

---

## Notes

- `.env` contains your Jellyfin API key — do not commit it to a public repository.
- MakeMKV requires a valid (paid or beta) license key to rip commercial DVDs. The beta key is renewed periodically on the MakeMKV forum.
- Linux-only (`eject`, `blkid`, `/dev/sr*`).
