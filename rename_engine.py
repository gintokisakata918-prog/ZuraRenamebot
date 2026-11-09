import re
from datetime import datetime
from pathlib import Path

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MULTI_SPACE = re.compile(r"\s+")

def build_filename(template: str, original_name: str, user_id: int) -> str:
    """Render a safe output filename while retaining the source extension."""
    source = Path(original_name)
    stem = source.stem or "file"
    extension = source.suffix
    now = datetime.now()
    replacements = {
        "filename": stem,
        "ext": extension.lstrip("."),
        "user_id": str(user_id),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H-%M-%S"),
    }
    try:
        rendered = template.format(**replacements).strip()
    except KeyError as exc:
        raise ValueError(f"Unknown placeholder: {{{exc.args[0]}}}") from exc
    except (ValueError, IndexError) as exc:
        raise ValueError("Invalid template syntax.") from exc
    rendered = _INVALID.sub("_", rendered)
    rendered = _MULTI_SPACE.sub(" ", rendered).strip(" .")
    if not rendered:
        raise ValueError("The generated filename is empty.")
    if len(rendered) > 180:
        rendered = rendered[:180].rstrip(" .")
    if extension and Path(rendered).suffix.lower() != extension.lower():
        rendered += extension
    return rendered
