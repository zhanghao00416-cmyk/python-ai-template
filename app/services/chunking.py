"""Document chunking service with multiple strategies and parent-child support."""
from __future__ import annotations

import hashlib
import re
from typing import Protocol

import structlog
from pydantic import BaseModel

from app.schemas.knowledge import ChunkingParams, ChunkingStrategy, ParentChunkParams

logger = structlog.get_logger(__name__)


class TextChunk(BaseModel):
    """A single text chunk produced by the chunker."""

    chunk_id: str
    text: str
    chunk_index: int
    is_parent: bool = False
    parent_id: str | None = None
    heading: str = ""
    heading_level: int = 0


class ChunkingService:
    """Service that chunks documents using configurable strategies.

    Supports four strategies:
    - fixed_overlap: fixed-size windows with overlap
    - delimiter_max: split by delimiter, then subdivide oversized pieces
    - semantic: paragraph-aware boundary splitting
    - paragraph: split by markdown headings / blank lines

    Parent-child mode produces coarse parent chunks with fixed_overlap and
    finer child chunks using the selected strategy. Child chunks reference
    their parent via ``parent_id``.
    """

    def __init__(self) -> None:
        self._strategies: dict[ChunkingStrategy, Chunker] = {
            ChunkingStrategy.FIXED_OVERLAP: _FixedOverlapChunker(),
            ChunkingStrategy.DELIMITER_MAX: _DelimiterMaxChunker(),
            ChunkingStrategy.SEMANTIC: _SemanticChunker(),
            ChunkingStrategy.PARAGRAPH: _ParagraphChunker(),
        }

    def chunk(
        self,
        text: str,
        doc_id: str,
        strategy: ChunkingStrategy,
        params: ChunkingParams,
        enable_parent_child: bool = False,
        parent_params: ParentChunkParams | None = None,
    ) -> list[TextChunk]:
        """Chunk ``text`` according to the requested strategy.

        Args:
            text: Raw document text.
            doc_id: Stable document identifier used to derive chunk ids.
            strategy: Chunking strategy to apply.
            params: Parameters for the primary (child) chunker.
            enable_parent_child: If True, also emit parent chunks.
            parent_params: Parameters for parent chunks when parent-child mode
                is enabled. Defaults to a sensible preset when omitted.

        Returns:
            List of chunks. In parent-child mode parents appear first in the
            list, followed by their children.
        """
        if not text or not text.strip():
            return []

        parent_params = parent_params or ParentChunkParams()
        base = self._strategies[strategy]

        if not enable_parent_child:
            return base.chunk(text, doc_id, params)

        parents = _FixedOverlapChunker().chunk(
            text, doc_id, _to_chunking_params(parent_params), is_parent=True
        )
        result: list[TextChunk] = []
        for parent in parents:
            result.append(parent)
            children = base.chunk(parent.text, doc_id, params)
            for child in children:
                child.parent_id = parent.chunk_id
                child.chunk_index = len(result)
                result.append(child)
        return result


class Chunker(Protocol):
    """Protocol for a chunking implementation."""

    def chunk(
        self, text: str, doc_id: str, params: ChunkingParams, is_parent: bool = False
    ) -> list[TextChunk]: ...


class _FixedOverlapChunker:
    """Fixed-size sliding window chunker with overlap."""

    def chunk(
        self, text: str, doc_id: str, params: ChunkingParams, is_parent: bool = False
    ) -> list[TextChunk]:
        size = params.chunk_size
        overlap = params.chunk_overlap
        step = max(1, size - overlap)
        chunks: list[TextChunk] = []
        idx = 0
        pos = 0
        while pos < len(text):
            end = min(pos + size, len(text))
            # Try not to break in the middle of a word unless necessary.
            if end < len(text) and text[end] not in {" ", "\n", "\t"}:
                boundary = text.rfind(" ", pos, end)
                if boundary == -1:
                    boundary = text.rfind("\n", pos, end)
                if boundary != -1 and boundary > pos:
                    end = boundary
            chunk_text = text[pos:end].strip()
            if chunk_text:
                chunks.append(
                    TextChunk(
                        chunk_id=_chunk_id(doc_id, idx, chunk_text, is_parent),
                        text=chunk_text,
                        chunk_index=idx,
                        is_parent=is_parent,
                    )
                )
                idx += 1
            pos += step
            if end == len(text):
                break
        return chunks


class _DelimiterMaxChunker:
    """Split by an optional delimiter, then subdivide oversized pieces."""

    def chunk(
        self, text: str, doc_id: str, params: ChunkingParams, is_parent: bool = False
    ) -> list[TextChunk]:
        delimiter = params.delimiter
        size = params.chunk_size
        overlap = params.chunk_overlap

        if delimiter:
            parts = [p.strip() for p in text.split(delimiter) if p.strip()]
        else:
            parts = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

        chunks: list[TextChunk] = []
        idx = 0
        for part in parts:
            if len(part) <= size:
                chunks.append(
                    TextChunk(
                        chunk_id=_chunk_id(doc_id, idx, part, is_parent),
                        text=part,
                        chunk_index=idx,
                        is_parent=is_parent,
                    )
                )
                idx += 1
                continue

            # Subdivide oversized part using fixed overlap.
            step = max(1, size - overlap)
            pos = 0
            while pos < len(part):
                end = min(pos + size, len(part))
                if end < len(part) and part[end] not in {" ", "\n", "\t"}:
                    boundary = part.rfind(" ", pos, end)
                    if boundary == -1:
                        boundary = part.rfind("\n", pos, end)
                    if boundary != -1 and boundary > pos:
                        end = boundary
                sub = part[pos:end].strip()
                if sub:
                    chunks.append(
                        TextChunk(
                            chunk_id=_chunk_id(doc_id, idx, sub, is_parent),
                            text=sub,
                            chunk_index=idx,
                            is_parent=is_parent,
                        )
                    )
                    idx += 1
                pos += step
                if end == len(part):
                    break
        return chunks


class _SemanticChunker:
    """Paragraph-aware chunker that tries to keep semantic boundaries."""

    def chunk(
        self, text: str, doc_id: str, params: ChunkingParams, is_parent: bool = False
    ) -> list[TextChunk]:
        size = params.chunk_size
        overlap = params.chunk_overlap
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

        chunks: list[TextChunk] = []
        idx = 0
        current: list[str] = []
        current_len = 0

        def flush() -> None:
            nonlocal idx, current, current_len
            if not current:
                return
            body = "\n\n".join(current)
            chunks.append(
                TextChunk(
                    chunk_id=_chunk_id(doc_id, idx, body, is_parent),
                    text=body,
                    chunk_index=idx,
                    is_parent=is_parent,
                )
            )
            idx += 1
            # Carry last paragraphs into overlap window.
            carry_len = 0
            carry: list[str] = []
            for p in reversed(current):
                if carry_len + len(p) > overlap and carry:
                    break
                carry.insert(0, p)
                carry_len += len(p) + 2
            current = carry
            current_len = carry_len

        for para in paragraphs:
            para_len = len(para)
            if para_len > size:
                flush()
                # Oversized paragraph: fall back to fixed overlap.
                step = max(1, size - overlap)
                pos = 0
                while pos < len(para):
                    end = min(pos + size, len(para))
                    sub = para[pos:end].strip()
                    if sub:
                        chunks.append(
                            TextChunk(
                                chunk_id=_chunk_id(doc_id, idx, sub, is_parent),
                                text=sub,
                                chunk_index=idx,
                                is_parent=is_parent,
                            )
                        )
                        idx += 1
                    pos += step
                    if end == len(para):
                        break
                current = []
                current_len = 0
                continue

            if current_len + para_len + 2 > size and current:
                flush()

            current.append(para)
            current_len += para_len + 2

        flush()
        return chunks


class _ParagraphChunker:
    """Split by markdown headings or blank-line paragraphs."""

    _HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    def chunk(
        self, text: str, doc_id: str, params: ChunkingParams, is_parent: bool = False
    ) -> list[TextChunk]:
        size = params.chunk_size
        # Find heading boundaries.
        matches = list(self._HEADING_RE.finditer(text))
        if not matches:
            # No headings: fall back to semantic chunking.
            return _SemanticChunker().chunk(text, doc_id, params, is_parent)

        chunks: list[TextChunk] = []
        idx = 0
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if not body:
                continue
            heading = match.group(2).strip()
            level = len(match.group(1))

            if len(body) <= size:
                chunks.append(
                    TextChunk(
                        chunk_id=_chunk_id(doc_id, idx, body, is_parent),
                        text=body,
                        chunk_index=idx,
                        is_parent=is_parent,
                        heading=heading,
                        heading_level=level,
                    )
                )
                idx += 1
            else:
                # Split oversized heading section with semantic chunker but
                # preserve heading metadata.
                subs = _SemanticChunker().chunk(body, doc_id, params, is_parent)
                for sub in subs:
                    sub.heading = heading
                    sub.heading_level = level
                    sub.chunk_index = idx
                    chunks.append(sub)
                    idx += 1
        return chunks


def _chunk_id(doc_id: str, index: int, text: str, is_parent: bool = False) -> str:
    """Generate a deterministic chunk id."""
    suffix = ":parent" if is_parent else ""
    digest = hashlib.sha256(f"{doc_id}:{index}:{text}".encode()).hexdigest()[:16]
    return f"{doc_id}:chunk:{index}{suffix}:{digest}"


def _to_chunking_params(parent: ParentChunkParams) -> ChunkingParams:
    """Convert parent params into the generic chunking params shape."""
    return ChunkingParams(
        chunk_size=parent.chunk_size,
        chunk_overlap=parent.chunk_overlap,
    )


