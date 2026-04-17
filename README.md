# dvd-ripper

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

All four must be on your `PATH`:

| Tool | Purpose | Install |
|---|---|---|
| `makemkvcon` | DVD decryption and title extraction | See [MakeMKV forum](https://www.makemkv.com/forum/viewtopic.php?t=224) |
| `ffprobe` | Framerate detection | `sudo apt install ffmpeg` |
| `eject` | Tray control | Pre-installed on most Linux distros |
| `blkid` | Disc label detection | Pre-installed on most Linux distros |

### Python

Python 3.6+ is required. No third-party packages are needed.

### Hardware

- A DVD drive accessible at `/dev/sr0` (configurable — see below)
- Sufficient disk space: ~8 GB per disc

---

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd dvd-ripper
```

### 2. Install system dependencies

On Ubuntu/Debian:

```bash
sudo apt update
sudo apt install ffmpeg eject util-linux
```

For `makemkvcon`, follow the official build instructions on the [MakeMKV forum](https://www.makemkv.com/forum/viewtopic.php?t=224) — it is not available in standard package repositories.

After installing, verify everything is on your PATH:

```bash
makemkvcon --version
ffprobe -version
eject --version
blkid --version
```

### 3. Configure the output directory

By default, ripped media is saved to `/srv/media/movies`. Create it (or update the path — see [Configuration](#configuration)):

```bash
sudo mkdir -p /srv/media/movies
sudo chown $USER:$USER /srv/media/movies
```

### 4. Set up Jellyfin integration (optional)

If you want the script to trigger a Jellyfin library scan after each rip, create a `.env` file in the project root:

```bash
cp .env.example .env   # or create it manually
```

`.env` contents:

```
JELLYFIN_API_KEY=your_api_key_here
```

To get your API key: Jellyfin dashboard → Administration → API Keys → + (add key).

If `JELLYFIN_API_KEY` is not set, the Jellyfin scan step is silently skipped.

---

## Configuration

Edit the constants at the top of `rip.py` to match your setup:

```python
DEVICE = "/dev/sr0"                    # DVD drive device path
OUTPUT_ROOT = Path("/srv/media/movies") # Where to save ripped media
JELLYFIN_URL = "http://localhost:8096"  # Jellyfin server address
DISC_READY_TIMEOUT = 60                 # Seconds to wait for disc to become readable
```

---

## Usage

```bash
python3 rip.py
```

The script walks you through the full workflow interactively:

1. **Tray opens** — insert your DVD when prompted
2. **Disc detected** — label is read and cleaned; you confirm or override the title and year
3. **Title scan** — MakeMKV scans the disc and displays a table of all titles with duration, chapter count, and size
4. **Select titles** — enter numbers, ranges (`1-3`), or `all`; the main feature is highlighted automatically
5. **Confirm destination** — shows the output path before anything is written
6. **Rip and process** — live progress shown throughout
8. **Done** — Jellyfin scan triggered (if configured); option to eject disc

To cancel at any point, press `Ctrl+C`. The script will clean up temporary files and eject the disc.

---

## Output structure

```
/srv/media/movies/
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
- The script is Linux-only (`/dev/sr0`, `eject`, `blkid`).
