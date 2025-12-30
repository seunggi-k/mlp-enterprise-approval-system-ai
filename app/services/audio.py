import subprocess
from pathlib import Path
from typing import List

import httpx


def ensure_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
    except Exception as e:
        raise RuntimeError("ffmpeg가 필요합니다. 서버에 ffmpeg 설치해줘요.") from e


def split_audio(input_path: Path, out_dir: Path, seconds: int) -> List[Path]:
    """Split audio into N-second mp3 chunks using ffmpeg."""
    ensure_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "chunk_%03d.mp3")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-f",
        "segment",
        "-segment_time",
        str(seconds),
        "-reset_timestamps",
        "1",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "4",
        pattern,
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    chunks = sorted(out_dir.glob("chunk_*.mp3"))
    if not chunks:
        raise RuntimeError("오디오 분할 결과가 없습니다.")
    return chunks


def download_audio(download_url: str, dst_path: Path):
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=300) as http:
        r = http.get(download_url)
        r.raise_for_status()
        dst_path.write_bytes(r.content)
