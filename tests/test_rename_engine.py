from rename_engine import build_filename

def test_preserves_extension():
    result = build_filename("NETQUBO - {filename}", "episode 01.mkv", 123)
    assert result == "NETQUBO - episode 01.mkv"

def test_can_use_extension_placeholder():
    result = build_filename("{filename}.{ext}", "movie.mp4", 123)
    assert result == "movie.mp4"

def test_sanitizes_path_separators():
    result = build_filename("{filename}", "../bad/name.mp4", 123)
    assert "/" not in result
    assert result.endswith(".mp4")
