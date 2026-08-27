import subprocess, pytest
from pathlib import Path

@pytest.fixture(scope="session")
def video_teste(tmp_path_factory):
    p = tmp_path_factory.mktemp("v") / "t.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6", "-c:v", "libx264", "-c:a", "aac", str(p)], check=True)
    return p
