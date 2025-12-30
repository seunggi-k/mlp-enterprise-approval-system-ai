import subprocess
from pathlib import Path
from typing import List

import httpx
from docx import Document
from pypdf import PdfReader

from app.services.storage import presign_get_url


def download_object(object_key: str, dst_path: Path):
    """Download an S3 object (via presigned GET) to a local path."""
    url = presign_get_url(object_key)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=300) as http:
        r = http.get(url)
        r.raise_for_status()
        dst_path.write_bytes(r.content)


def extract_text(file_path: Path, content_type: str | None = None) -> str:
    """Extract readable text from a few common document formats."""
    suffix = file_path.suffix.lower()

    if suffix in {".txt", ".md"}:
        return file_path.read_text(encoding="utf-8", errors="replace")

    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)

    if suffix == ".docx":
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs)

    if suffix == ".hwp":
        try:
            proc = subprocess.run(
                ["hwp5txt", str(file_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            return proc.stdout
        except FileNotFoundError as e:
            raise RuntimeError("hwp5txt CLI가 필요합니다. 서버에 설치해주세요.") from e
        except subprocess.CalledProcessError as e:
            raise RuntimeError("HWP 텍스트 추출에 실패했습니다.") from e

    raise RuntimeError(f"지원하지 않는 파일 타입입니다: {suffix or content_type}")


def chunk_text(text: str, words_per_chunk: int, overlap_words: int) -> List[str]:
    words = text.split()
    if not words:
        raise RuntimeError("문서에서 추출된 텍스트가 없습니다.")

    step = max(words_per_chunk - overlap_words, 1)
    chunks: List[str] = []
    for i in range(0, len(words), step):
        piece = words[i : i + words_per_chunk]
        if not piece:
            continue
        chunks.append(" ".join(piece))
    return chunks
