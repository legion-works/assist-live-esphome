def test_source_only_boundary():
    from pathlib import Path

    assert Path("components/assist_live/assist_live.h").exists()
    assert "GNU GENERAL PUBLIC LICENSE" in Path("LICENSE").read_text()
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "--", "*.bin"], check=True, capture_output=True
    )
    assert result.stdout == b""
