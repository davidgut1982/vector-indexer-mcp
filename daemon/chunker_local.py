"""Token-aware text chunker for local asyncpg-based vector indexer."""

from dataclasses import dataclass
from typing import List


@dataclass
class TextChunk:
    text: str
    start_line: int
    end_line: int
    chunk_index: int
    token_count: int


class TextChunker:
    def __init__(self, chunk_size_tokens: int = 500, overlap_tokens: int = 50):
        self.chunk_size = chunk_size_tokens
        self.overlap = overlap_tokens
        try:
            import tiktoken

            self.enc = tiktoken.get_encoding("cl100k_base")
            self._use_tiktoken = True
        except Exception:
            self._use_tiktoken = False

    def _count_tokens(self, text: str) -> int:
        if self._use_tiktoken:
            return len(self.enc.encode(text))
        return len(text.split())

    def chunk_text(self, text: str, file_path: str = "") -> List[TextChunk]:
        lines = text.splitlines(keepends=True)
        chunks = []
        current_lines = []
        current_tokens = 0
        chunk_idx = 0
        start_line = 1

        for line_num, line in enumerate(lines, 1):
            line_tokens = self._count_tokens(line)
            if current_tokens + line_tokens > self.chunk_size and current_lines:
                chunk_text = "".join(current_lines)
                chunks.append(
                    TextChunk(
                        text=chunk_text,
                        start_line=start_line,
                        end_line=line_num - 1,
                        chunk_index=chunk_idx,
                        token_count=current_tokens,
                    )
                )
                chunk_idx += 1
                # Overlap: keep last N tokens worth of lines
                overlap_lines = []
                overlap_tokens = 0
                for prev_line in reversed(current_lines):
                    t = self._count_tokens(prev_line)
                    if overlap_tokens + t > self.overlap:
                        break
                    overlap_lines.insert(0, prev_line)
                    overlap_tokens += t
                current_lines = overlap_lines + [line]
                current_tokens = overlap_tokens + line_tokens
                start_line = line_num - len(overlap_lines)
            else:
                current_lines.append(line)
                current_tokens += line_tokens

        if current_lines:
            chunks.append(
                TextChunk(
                    text="".join(current_lines),
                    start_line=start_line,
                    end_line=len(lines),
                    chunk_index=chunk_idx,
                    token_count=current_tokens,
                )
            )

        return chunks
