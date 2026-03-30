"""PDF compilation pipeline.

Uses pymupdf (fitz) as the default backend, with optional docling support.
"""

from __future__ import annotations

import time

from agent_web_compiler.core.block import Block, BlockType
from agent_web_compiler.core.config import CompileConfig
from agent_web_compiler.core.document import AgentDocument, Quality, SourceType
from agent_web_compiler.core.errors import CompilerError, ParseError
from agent_web_compiler.core.provenance import PageProvenance, Provenance


class PDFCompiler:
    """Compiles PDF files into AgentDocuments."""

    def compile(
        self,
        content: str | bytes,
        *,
        source_file: str | None = None,
        config: CompileConfig | None = None,
    ) -> AgentDocument:
        """Compile PDF content into an AgentDocument.

        Args:
            content: PDF content as bytes.
            source_file: Path to the source file.
            config: Compilation configuration.

        Returns:
            An AgentDocument with extracted blocks.
        """
        if config is None:
            config = CompileConfig()

        timings: dict[str, float] = {}
        t0 = time.perf_counter()

        if isinstance(content, str):
            content = content.encode("latin-1")

        backend = config.pdf_backend
        if backend == "auto":
            backend = self._detect_backend()

        if backend == "pymupdf":
            blocks, title, warnings = self._extract_pymupdf(content, config)
        elif backend == "docling":
            blocks, title, warnings = self._extract_docling(content, config)
        else:
            blocks, title, warnings = self._extract_pymupdf(content, config)

        timings["extract"] = time.perf_counter() - t0

        # Build canonical markdown
        from agent_web_compiler.exporters.markdown_exporter import to_markdown

        canonical_md = to_markdown(blocks)

        doc = AgentDocument(
            doc_id=AgentDocument.make_doc_id(content),
            source_type=SourceType.PDF,
            source_file=source_file,
            title=title,
            blocks=blocks,
            canonical_markdown=canonical_md,
            actions=[],
            quality=Quality(
                block_count=len(blocks),
                action_count=0,
                warnings=warnings,
            ),
            debug={"timings": timings} if config.debug else {},
        )

        return doc

    def _detect_backend(self) -> str:
        """Detect best available PDF backend."""
        try:
            import fitz  # noqa: F401

            return "pymupdf"
        except ImportError:
            pass

        try:
            import docling  # noqa: F401

            return "docling"
        except ImportError:
            pass

        raise CompilerError(
            "No PDF backend available. Install pymupdf or docling: "
            "pip install 'agent-web-compiler[pdf]'",
            stage="pdf",
        )

    def _extract_pymupdf(
        self, content: bytes, config: CompileConfig
    ) -> tuple[list[Block], str, list[str]]:
        """Extract blocks using PyMuPDF (fitz)."""
        try:
            import fitz
        except ImportError as exc:
            raise CompilerError(
                "pymupdf not installed. Run: pip install 'agent-web-compiler[pdf]'",
                stage="pdf",
            ) from exc

        warnings: list[str] = []
        blocks: list[Block] = []
        order = 0
        title = ""

        try:
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception as e:
            raise ParseError(f"Failed to parse PDF: {e}", cause=e) from e

        # Try to get title from metadata
        metadata = doc.metadata
        if metadata and metadata.get("title"):
            title = metadata["title"]

        for page_num in range(len(doc)):
            page = doc[page_num]
            text_dict = page.get_text("dict")

            for block_data in text_dict.get("blocks", []):
                if block_data.get("type") == 0:  # Text block
                    text_lines: list[str] = []
                    for line in block_data.get("lines", []):
                        line_text = ""
                        for span in line.get("spans", []):
                            line_text += span.get("text", "")
                        if line_text.strip():
                            text_lines.append(line_text.strip())

                    if not text_lines:
                        continue

                    text = "\n".join(text_lines)

                    # Detect block type from font size and style
                    block_type = BlockType.PARAGRAPH
                    level = None
                    importance = 0.6

                    first_span = (
                        block_data.get("lines", [{}])[0]
                        .get("spans", [{}])[0]
                        if block_data.get("lines")
                        and block_data["lines"][0].get("spans")
                        else {}
                    )
                    font_size = first_span.get("size", 12)
                    font_flags = first_span.get("flags", 0)
                    is_bold = bool(font_flags & 2**4)  # Bold flag

                    if font_size >= 18 or (font_size >= 14 and is_bold):
                        block_type = BlockType.HEADING
                        level = 1 if font_size >= 20 else 2 if font_size >= 16 else 3
                        importance = 0.9
                        if not title:
                            title = text
                    elif font_size >= 13 and is_bold:
                        block_type = BlockType.HEADING
                        level = 3
                        importance = 0.85

                    bbox = block_data.get("bbox", [])

                    provenance = None
                    if config.include_provenance and bbox:
                        provenance = Provenance(
                            page=PageProvenance(
                                page=page_num + 1,
                                bbox=list(bbox),
                            ),
                        )

                    blocks.append(
                        Block(
                            id=f"b_{order:03d}",
                            type=block_type,
                            text=text,
                            order=order,
                            importance=importance,
                            level=level,
                            provenance=provenance,
                            metadata={"page": page_num + 1, "font_size": font_size},
                        )
                    )
                    order += 1

                elif block_data.get("type") == 1:  # Image block
                    blocks.append(
                        Block(
                            id=f"b_{order:03d}",
                            type=BlockType.IMAGE,
                            text="[Image]",
                            order=order,
                            importance=0.4,
                            metadata={"page": page_num + 1},
                        )
                    )
                    order += 1

        doc.close()

        if not blocks:
            warnings.append("No text blocks extracted from PDF — may be a scanned document")

        return blocks, title, warnings

    def _extract_docling(
        self, content: bytes, config: CompileConfig
    ) -> tuple[list[Block], str, list[str]]:
        """Extract blocks using docling (if available)."""
        raise CompilerError(
            "Docling backend not yet implemented. Use pymupdf for now.",
            stage="pdf",
        )
