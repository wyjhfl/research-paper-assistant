from dataclasses import dataclass

from pypdf import PdfReader


@dataclass
class PageText:
    page_number: int
    text: str


@dataclass
class ChunkData:
    chunk_index: int
    text: str
    page_start: int
    page_end: int
    section_title: str | None = None


def extract_pages(file_path: str) -> list[PageText]:
    reader = PdfReader(file_path)
    pages: list[PageText] = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append(PageText(page_number=i + 1, text=text))
    return pages


def chunk_pages(
    pages: list[PageText], chunk_size: int = 1000, chunk_overlap: int = 200
) -> list[ChunkData]:
    chunks: list[ChunkData] = []
    chunk_index = 0

    for page in pages:
        text = page.text.strip()
        if not text:
            continue

        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk_text = text[start:end]

            if chunk_text.strip():
                chunks.append(
                    ChunkData(
                        chunk_index=chunk_index,
                        text=chunk_text,
                        page_start=page.page_number,
                        page_end=page.page_number,
                    )
                )
                chunk_index += 1

            if end >= len(text):
                break
            start += chunk_size - chunk_overlap

    return chunks


def parse_pdf(file_path: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list[ChunkData]:
    pages = extract_pages(file_path)
    return chunk_pages(pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
