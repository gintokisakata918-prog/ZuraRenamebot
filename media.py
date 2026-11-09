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

async def write_metadata(source, destination, title=None, author=None, artist=None,
                         audio=None, subtitle=None, video=None):
    """Remux all streams without re-encoding and set container/track titles."""
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-map", "0", "-c", "copy"]
    if title:
        args += ["-metadata", f"title={title}"]
    if author:
        args += ["-metadata", f"author={author}"]
        byline = f"By :- {author}"
        if not audio:
            args += ["-metadata:s:a", f"title={byline}"]
        if not subtitle:
            args += ["-metadata:s:s", f"title={byline}"]
        if not video:
            args += ["-metadata:s:v", f"title={byline}"]
    if artist:
        args += ["-metadata", f"artist={artist}"]
    if audio:
        args += ["-metadata:s:a", f"title={audio}"]
    if subtitle:
        args += ["-metadata:s:s", f"title={subtitle}"]
    if video:
        args += ["-metadata:s:v", f"title={video}"]
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
