import asyncio
import json
from pathlib import Path

async def probe_media(path):
    """Return ffprobe metadata for a media file."""
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if proc.returncode:
        raise RuntimeError(err.decode(errors="replace")[-600:])
    return json.loads(out.decode("utf-8", errors="replace") or "{}")

async def write_metadata(source, destination, subtitle=None, audio=None, author=None):
    """Remux streams without re-encoding and set common container metadata."""
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-map", "0", "-c", "copy"]
    if author:
        args += ["-metadata", f"author={author}", "-metadata", f"artist={author}"]
    if audio:
        args += ["-metadata:s:a", f"title={audio}"]
    if subtitle:
        args += ["-metadata:s:s", f"title={subtitle}"]
    args.append(str(destination))
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, err = await proc.communicate()
    if proc.returncode:
        raise RuntimeError(err.decode(errors="replace")[-800:])
    return Path(destination)
