"""
Ingestion module for the RAG pipeline.


Loads corpus documents from disk, parses YAML frontmatter,
and returns structured Document objects for downstream processing.

"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any

import frontmatter
import yaml




@dataclass
class Document:
    """
    A single document with its text content and metadata.

    """
    text: str   # The main body content of the document 
    metadata: Dict[str, Any] = field(default_factory=dict)  # Metadata from YAML frontmatter 



def load_documents(corpus_path: Path) -> List[Document]:
    """
    Load all markdown files with YAML frontmatter from a directory.

    Args:
        corpus_path: Path to directory containing .md files

    Returns:
        List of Document objects with text and metadata populated.

    Raises:
        FileNotFoundError: If corpus_path doesn't exist.
        ValueError: Id a file has invalid YAML frontmatter
    """

    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus directory not found: {corpus_path}")
    
    if not corpus_path.is_dir():
        raise ValueError(f"Path is not a directory: {corpus_path}")
    
    documents = []
    md_files = list(corpus_path.glob("*.md"))

    if not md_files:
        print(f"Warning: No .md files found in {corpus_path}")
        return documents
    
    for file_path in sorted(md_files):
        try:
            post = frontmatter.load(file_path)
        except yaml.YAMLError as e:
            raise ValueError(
                f"Invalid YAML frontmatter in {file_path.name}: {e}"
            ) from e
        
        documents.append(Document(
            text=post.content,          # Exact as on disk
            metadata=dict(post.metadata)

        ))

    return documents


def main():
    """Test ingestion by loading the corpus and printing a summary."""
    corpus_path = Path("corpus/raw")

    print(f"Loading documents from: {corpus_path.absolute()}")
    print("-" * 50)

    docs = load_documents(corpus_path)

    print(f"Loaded {len(docs)} document:\n")

    for doc in docs:
        doc_id = doc.metadata.get("id", "unknown")
        company = doc.metadata.get("company", "unknown")
        severity = doc.metadata.get("severity", "unknown")
        text_len = len(doc.text)

        print(f"    [{doc_id}] {company}  ({severity})")
        print(f"        Text length: {text_len} characters")
        print(f"        Metadata fields: {','.join(doc.metadata.keys())}")
        print()



if __name__ == "__main__":
    main()


    



