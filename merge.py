import asyncio
from pathlib import Path


def _concat_quote(path):
    return str(Path(path).resolve()).replace("'", "'\\''")


async def merge_videos(input_files, output_file):
    """Join compatible video/audio/subtitle streams without re-encoding.

    Matroska files can contain attachments (fonts), data streams, or other
    non-media tracks. Do not map those into the output; keep only video,
    audio and subtitle streams.
    """
    if len(input_files) < 2:
        raise ValueError("At least two video files are required.")

    output = Path(output_file)
    listing = output.parent / "concat_list.txt"
    listing.write_text(
        "\n".join(f"file '{_concat_quote(path)}'" for path in input_files) + "\n",
        encoding="utf-8",
    )

    args = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(listing),
        "-map", "0:v?", "-map", "0:a?", "-map", "0:s?",
        "-c", "copy", str(output),
    ]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()

    if proc.returncode or not output.exists() or output.stat().st_size == 0:
        output.unlink(missing_ok=True)
        detail = err.decode(errors="replace")[-1000:]
        raise RuntimeError(
            "FFmpeg concat failed. Non-video attachments/data tracks are now "
            "excluded, but all parts must still have compatible video, audio "
            "and subtitle streams. " + detail
        )
    return output
