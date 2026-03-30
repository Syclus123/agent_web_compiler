"""File reader for local HTML, PDF, and DOCX files."""

from __future__ import annotations

from pathlib import Path

from agent_web_compiler.core.errors import FetchError
from agent_web_compiler.core.interfaces import FetchResult

# Map file extensions to MIME content types.
_EXTENSION_TO_CONTENT_TYPE: dict[str, str] = {
    ".html": "text/html",
    ".htm": "text/html",
    ".xhtml": "text/html",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".xml": "application/xml",
    ".json": "application/json",
}

# Content types that should be read as binary (bytes).
_BINARY_CONTENT_TYPES: set[str] = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class FileReader:
    """Reads local files (HTML, PDF, DOCX)."""

    def read(self, path: str) -> FetchResult:
        """Read a local file and return a FetchResult.

        Args:
            path: Path to the local file.

        Returns:
            FetchResult with file content and detected content type.

        Raises:
            FetchError: If the file does not exist, is not a file, or cannot be read.
        """
        file_path = Path(path).resolve()

        if not file_path.exists():
            raise FetchError(
                f"File not found: {path}",
                context={"path": path},
            )

        if not file_path.is_file():
            raise FetchError(
                f"Path is not a file: {path}",
                context={"path": path},
            )

        extension = file_path.suffix.lower()
        content_type = _EXTENSION_TO_CONTENT_TYPE.get(extension, "application/octet-stream")

        try:
            if content_type in _BINARY_CONTENT_TYPES:
                content: str | bytes = file_path.read_bytes()
            else:
                content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise FetchError(
                f"Failed to read file: {path}: {exc}",
                cause=exc,
                context={"path": path},
            ) from exc

        file_size = file_path.stat().st_size

        return FetchResult(
            content=content,
            content_type=content_type,
            url=file_path.as_uri(),
            status_code=200,
            headers={},
            metadata={
                "file_path": str(file_path.resolve()),
                "file_size": file_size,
                "extension": extension,
            },
        )
