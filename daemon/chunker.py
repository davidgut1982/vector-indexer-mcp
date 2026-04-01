"""Text chunking module for vector indexer.

Provides token-aware text chunking using tiktoken with overlap support.
Respects line boundaries where possible for better semantic coherence.
"""

import logging
from dataclasses import dataclass
from typing import List

import tiktoken

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """Represents a text chunk with metadata.

    Attributes:
        text: The chunk text content
        index: Sequential index of this chunk (0-based)
        start_line: Starting line number in source file
        end_line: Ending line number in source file
        char_offset: Character offset from start of file
        token_count: Number of tokens in this chunk
    """
    text: str
    index: int
    start_line: int
    end_line: int
    char_offset: int
    token_count: int


class TextChunker:
    """Token-aware text chunker with overlap support.

    Uses tiktoken (cl100k_base encoding) for accurate token counting.
    Respects line boundaries where possible to maintain semantic coherence.

    Args:
        max_tokens: Maximum tokens per chunk (default: 500)
        overlap_tokens: Number of overlapping tokens between chunks (default: 50)
        encoding_name: Tiktoken encoding to use (default: cl100k_base)
    """

    def __init__(
        self,
        max_tokens: int = 500,
        overlap_tokens: int = 50,
        encoding_name: str = "cl100k_base"
    ):
        """Initialize the text chunker."""
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.encoding = tiktoken.get_encoding(encoding_name)

        logger.info(
            f"TextChunker initialized: max_tokens={max_tokens}, "
            f"overlap={overlap_tokens}, encoding={encoding_name}"
        )

    def chunk_text(self, text: str) -> List[Chunk]:
        """Chunk text into overlapping segments respecting line boundaries.

        Args:
            text: Input text to chunk

        Returns:
            List of Chunk objects with metadata
        """
        if not text.strip():
            return []

        lines = text.split('\n')
        chunks: List[Chunk] = []

        current_chunk_lines: List[str] = []
        current_tokens = 0
        current_start_line = 0
        current_char_offset = 0
        chunk_index = 0

        # Track character offset as we process lines
        char_offset = 0

        for line_num, line in enumerate(lines):
            line_with_newline = line + '\n' if line_num < len(lines) - 1 else line
            line_tokens = len(self.encoding.encode(line_with_newline))

            # If adding this line would exceed max_tokens, create a chunk
            if current_tokens + line_tokens > self.max_tokens and current_chunk_lines:
                # Create chunk from accumulated lines
                chunk_text = '\n'.join(current_chunk_lines)
                chunk = Chunk(
                    text=chunk_text,
                    index=chunk_index,
                    start_line=current_start_line,
                    end_line=line_num - 1,
                    char_offset=current_char_offset,
                    token_count=current_tokens
                )
                chunks.append(chunk)
                chunk_index += 1

                # Calculate overlap
                overlap_lines = self._get_overlap_lines(
                    current_chunk_lines,
                    self.overlap_tokens
                )

                # Start new chunk with overlap
                current_chunk_lines = overlap_lines
                current_tokens = len(self.encoding.encode('\n'.join(overlap_lines)))
                current_start_line = line_num - len(overlap_lines)
                current_char_offset = char_offset - sum(
                    len(l) + 1 for l in overlap_lines
                )

            # Add current line to chunk
            current_chunk_lines.append(line)
            current_tokens += line_tokens

            # Update character offset
            char_offset += len(line_with_newline)

        # Add final chunk if there's content
        if current_chunk_lines:
            chunk_text = '\n'.join(current_chunk_lines)
            chunk = Chunk(
                text=chunk_text,
                index=chunk_index,
                start_line=current_start_line,
                end_line=len(lines) - 1,
                char_offset=current_char_offset,
                token_count=current_tokens
            )
            chunks.append(chunk)

        logger.debug(f"Created {len(chunks)} chunks from {len(lines)} lines")
        return chunks

    def _get_overlap_lines(
        self,
        lines: List[str],
        target_overlap_tokens: int
    ) -> List[str]:
        """Get last N lines that fit within target overlap tokens.

        Args:
            lines: List of lines from previous chunk
            target_overlap_tokens: Target number of tokens for overlap

        Returns:
            List of lines that fit within overlap token budget
        """
        if not lines:
            return []

        overlap_lines: List[str] = []
        current_tokens = 0

        # Work backwards from end of lines
        for line in reversed(lines):
            line_tokens = len(self.encoding.encode(line + '\n'))

            if current_tokens + line_tokens > target_overlap_tokens:
                break

            overlap_lines.insert(0, line)
            current_tokens += line_tokens

        return overlap_lines

    def count_tokens(self, text: str) -> int:
        """Count tokens in text using the configured encoding.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        return len(self.encoding.encode(text))
