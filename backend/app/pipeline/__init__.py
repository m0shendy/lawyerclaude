"""Document ingestion pipeline (T043–T050).

Public API surface:
  * ``normalize_ar.normalize``       — Arabic text normalization [R5]
  * ``preprocess.preprocess``        — byte validation + MIME check
  * ``confidence.assess_confidence`` — OCR quality gate [C-VII]
  * ``chunk.chunk_pages``            — page-aware overlapping chunker [R3]
  * ``embed.embed_texts``            — Google Generative AI batch embedder [R1]
  * ``ocr_documentai.ocr_document``  — Document AI OCR client
  * ``run.process_document``         — full pipeline orchestration (entry point
                                       for the background worker)
"""

from app.pipeline.chunk import Chunk, chunk_pages
from app.pipeline.confidence import assess_confidence
from app.pipeline.embed import EmbedError, embed_texts
from app.pipeline.normalize_ar import normalize
from app.pipeline.ocr_documentai import OcrError, OcrResult, ocr_document
from app.pipeline.preprocess import PreprocessError, preprocess
from app.pipeline.run import process_document

__all__ = [
    "Chunk",
    "EmbedError",
    "OcrError",
    "OcrResult",
    "PreprocessError",
    "assess_confidence",
    "chunk_pages",
    "embed_texts",
    "normalize",
    "ocr_document",
    "preprocess",
    "process_document",
]
