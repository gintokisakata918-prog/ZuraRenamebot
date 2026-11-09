import asyncio
from pathlib import Path

def _concat_quote(path):
    return str(Path(path).resolve()).replace("'", "'\\''")

async def merge_videos(input_files, output_file):
    """Join compatible video files in order without re-encoding."""
    if len(input_files) < 2:
        raise ValueError("At least two video files are required.")
    output = Path(output_file)
    listing = output.parent / "concat_list.txt"
    listing.write_text("\n".join(f"file '{_concat_quote(p)}'" for p in input_files) + "\n", encoding="utf-8")
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-map", "0", "-c", "copy", str(output)]
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode or not output.exists() or output.stat().st_size == 0:
        output.unlink(missing_ok=True)
        raise RuntimeError("FFmpeg concat failed. Parts need compatible codecs, resolution, frame rate and streams. " + err.decode(errors="replace")[-800:])
    return output
