import re
import subprocess
from pathlib import Path
from typing import List

import httpx
from docx import Document
from pypdf import PdfReader

from app.services.storage import presign_get_url


_chapter_re = re.compile(r"^제\s*\d+\s*장\b\s*(.*)")
_article_re = re.compile(r"^제\s*\d+\s*조\b.*")


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


def _normalize_spaces(line: str) -> str:
    return " ".join(line.split())


def _infer_doc_title(text: str, default_title: str) -> str:
    fallback = _normalize_spaces(Path(default_title).stem or default_title)
    for raw in text.splitlines():
        line = _normalize_spaces(raw.strip())
        if not line or line == "<표>":
            continue
        if _chapter_re.match(line) or _article_re.match(line):
            break
        return line
    return fallback


def chunk_by_article(
    text: str,
    default_doc_title: str,
    words_per_chunk: int,
    overlap_words: int,
) -> tuple[str, List[str]]:
    """
    Split 규약 문서 into 조 단위로 분리하고 "문서명 - 장 제목"을 앞에 붙여 반환한다.
    장/조 패턴을 찾지 못하면 기존 단어 단위 청크로 폴백한다.
    """
    doc_title = _infer_doc_title(text, default_doc_title)
    current_chapter = ""
    current_article = ""
    body_lines: List[str] = []
    chunks: List[str] = []

    def flush_article():
        if not current_article:
            return
        article_body = " ".join(body_lines).strip()
        article_text = current_article
        if article_body:
            article_text = f"{article_text} {article_body}".strip()
        chapter_label = _normalize_spaces(current_chapter) if current_chapter else ""
        header_parts = [p for p in (_normalize_spaces(doc_title), chapter_label) if p]
        prefix = " - ".join(header_parts)
        chunk = f"{prefix}\n{article_text}" if prefix else article_text
        chunks.append(chunk)

    for raw in text.splitlines():
        line = _normalize_spaces(raw.strip())
        if not line or line == "<표>":
            continue

        chapter_match = _chapter_re.match(line)
        if chapter_match:
            # 새 장 시작: 기존 조항이 있으면 먼저 flush
            flush_article()
            body_lines = []
            current_article = ""
            current_chapter = line
            continue

        if _article_re.match(line):
            # 새 조항 시작
            flush_article()
            body_lines = []
            current_article = line
            continue

        if current_article:
            body_lines.append(line)

    flush_article()

    # 장/조 패턴이 없는 경우 기존 단어 단위 청크 방식으로 폴백
    if not chunks:
        return doc_title, chunk_text(text, words_per_chunk, overlap_words)

    return doc_title, chunks
