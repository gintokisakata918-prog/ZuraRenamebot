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

async def generate_thumbnail(source, destination):
    """Extract a small JPEG preview from a video using FFmpeg."""
    args = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", "00:00:03", "-i", str(source), "-frames:v", "1",
        "-vf", "scale=320:320:force_original_aspect_ratio=decrease",
        "-q:v", "8", str(destination)
    ]
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    _, err = await proc.communicate()
    path = Path(destination)
    if proc.returncode or not path.exists() or path.stat().st_size > 200 * 1024:
        path.unlink(missing_ok=True)
        if proc.returncode:
            raise RuntimeError(err.decode(errors="replace")[-500:])
        raise RuntimeError("Generated thumbnail is missing or exceeds 200 KB")
    return path
