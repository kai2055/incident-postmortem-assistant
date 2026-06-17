"""
Chunking module

Splits documents into sematic chunks based on section headers,
preserving metadata for traceability and filtering.

"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple

from src.ingestion import Document



@dataclass
class Chunk:
    """
    A semantic chunk of text with its metadata.

    Each chunk knows which document and section it came from,
    enabling traceability and strutured filtering in ChromaDB
    
    """
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


def chunk_documents(
        documents: List[Document],
        max_chunk_size: int = 2000,        
) -> List[Chunk]:
    """
    Split each document into sections and paragraphs, returing chunks.

    Args:
        documents: List of Document objects from ingestion
        max_chunk_size: Maximum characters per chunk
            Sections exceeding this are split on paragraph boundaries

    Returns:
        List of Chunk objects, one per logical piece.
    
    """
    chunks = []

    for doc in documents:
        sections = _split_into_sections(doc.text)

        for section_name, section_text in sections:
            # Normalize section name for metadata
            section_meta = _normalize_section_name(section_name)

            if len(section_text) <= max_chunk_size:
                chunk = Chunk(
                    text=section_text.strip(),
                    metadata=_build_chunk_metadata(
                        doc.metadata,
                        section_meta,
                        chunk_index=0,
                        total_chunks=1,
                    )
                )
                chunks.append(chunk)
            else:
                # Split long section by paragraphs
                paragraph_groups = _split_by_paragraphs(
                    section_text, max_chunk_size
                )
                for idx, group in enumerate(paragraph_groups):
                    chunk = Chunk(
                        text=group.strip(),
                        metadata=_build_chunk_metadata(
                            doc.metadata,
                            section_meta,
                            chunk_index=idx,
                            total_chunks=len(paragraph_groups),
                        )
                    )
                    chunks.append(chunk)


    return chunks


def _split_into_sections(text: str) -> List[Tuple[str, str]]:
    """
    Split document by ## headings.

    Returns:
        List of (header_name, content_with_header) tuples.
  
    """
    heading_pattern = re.compile(r"^(##\s+.+)$", re.MULTILINE)
    matches = list(heading_pattern.finditer(text))


    if not matches:
        return [("full_document", text.strip())]
    
    sections = []

    for i, match in enumerate(matches):
        header = match.group(1)
        start = match.start()

        if i == 0:
            # Content before first heading (if any)
            intro = text[0:start].strip()
            if intro:
                sections.append(("intro", intro))

        # Content from this heading to the next heading (or end)
        if i + 1 < len(matches):
            next_start = matches[i + 1].start()
            content = text[start:next_start].strip()
        else:
            content = text[start:].strip()


        sections.append((header, content))

    return sections


def _split_by_paragraphs(text: str, max_chunk_size: int) -> List[str]:
    """
    Split text into paragraph groups, each <= max_chunk_size.

    Args:
        text: Section text (with header included).
        max_chunk_size: Maximum characters per chunk.

    Returns:
        List of text chunks, each <= max_chunk_size.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    if not paragraphs:
        return [text]

    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 > max_chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para
        else:
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para

    if current_chunk:
        chunks.append(current_chunk.strip())

    # Filter out separator-only chunks
    filtered = []
    for chunk in chunks:
        clean = chunk.strip()
        if clean and clean != "---":
            filtered.append(chunk)

    return filtered




def _normalize_section_name(header: str) -> str:
    name = header.replace("##", "").strip().lower()
    name = name.replace(" ", "_")
    return name



def _build_chunk_metadata(
        doc_metadata: Dict[str, Any],
        section: str,
        chunk_index: int,
        total_chunks: int,
) -> Dict[str, Any]:
    """Build metadata for a chunk from document metadata + chunking info"""
    return {
        "doc_id": doc_metadata.get("id"),
        "title": doc_metadata.get("title"),
        "company": doc_metadata.get("company"),
        "date": doc_metadata.get("date"),
        "severity": doc_metadata.get("severity"),
        "root_cause_category": doc_metadata.get("root_cause_category"),
        "section": section,
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
    }




def main():
    """Test chunking by loading documents and printing chunk statistics."""
    from pathlib import Path
    from .ingestion import load_documents

    corpus_path = Path("corpus/raw")
    print(f"Loading documents from: {corpus_path.absolute()}")
    print("-" * 50)

    docs = load_documents(corpus_path)
    print(f"Loaded {len(docs)} documents.")

    chunks = chunk_documents(docs, max_chunk_size=2000)
    print(f"Generated {len(chunks)} chunks.")
    print("-" * 50)

    print("\nSample chunks:")
    for i, chunk in enumerate(chunks[:5]):
        doc_id = chunk.metadata.get("doc_id", "unknown")
        section = chunk.metadata.get("section", "unknown")
        text_preview = chunk.text[:100].replace("\n", " ") + "..."
        print(f"  [{doc_id}] {section} ({chunk.metadata.get('chunk_index', 0)}/{chunk.metadata.get('total_chunks', 1)})")
        print(f"      {text_preview}")
        print()

    if len(chunks) > 5:
        print(f"  ... and {len(chunks) - 5} more chunks")


if __name__ == "__main__":
    main()




