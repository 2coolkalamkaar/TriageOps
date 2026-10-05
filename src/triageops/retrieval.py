"""
BM25 keyword-based runbook retrieval.

Runbooks are markdown files stored in the runbooks/ directory.
Each file covers a common infrastructure failure pattern.

Design decision: BM25 first. Upgrade to embeddings only if golden tests
show BM25 is clearly missing relevant runbooks.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from rank_bm25 import BM25Okapi  # type: ignore
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    logger.warning("rank-bm25 not installed — runbook retrieval disabled")


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenizer."""
    return re.findall(r"[a-z0-9_\-]+", text.lower())


class Runbooks:
    """
    Loads markdown runbooks from a directory and provides BM25 search.

    Usage:
        rb = Runbooks("/path/to/runbooks")
        results = rb.search("CrashLoopBackOff OOMKilled", k=2)
        for name, text in results:
            print(name)
    """

    def __init__(self, folder: str | Path = "runbooks") -> None:
        self.folder = Path(folder)
        self.docs: list[tuple[str, str]] = []
        self.bm25: BM25Okapi | None = None
        self._load()

    def _load(self) -> None:
        """Load all .md files from the runbooks directory."""
        if not self.folder.exists():
            logger.warning("Runbooks directory not found: %s", self.folder)
            return

        self.docs = [
            (p.name, p.read_text(encoding="utf-8"))
            for p in sorted(self.folder.glob("*.md"))
        ]

        if not self.docs:
            logger.warning("No runbooks found in %s", self.folder)
            return

        if BM25_AVAILABLE:
            tokenized = [_tokenize(text) for _, text in self.docs]
            self.bm25 = BM25Okapi(tokenized)
            logger.info("Loaded %d runbooks from %s", len(self.docs), self.folder)
        else:
            logger.warning("BM25 not available — runbooks loaded but search disabled")

    def search(self, query: str, k: int = 2) -> list[tuple[str, str]]:
        """
        Return the top-k most relevant runbooks for a query.

        Args:
            query: Search string (typically key_error_lines joined + type).
            k: Number of results to return.

        Returns:
            List of (filename, content) tuples, ordered by relevance.
            Returns an empty list if BM25 is unavailable or no runbooks loaded.
        """
        if not self.bm25 or not self.docs:
            return []

        tokens = _tokenize(query)
        if not tokens:
            return []

        scores = self.bm25.get_scores(tokens)
        ranked = sorted(
            zip(scores, self.docs),
            key=lambda x: x[0],
            reverse=True,
        )

        results = [
            (name, text)
            for score, (name, text) in ranked[:k]
            if score > 0.0
        ]
        logger.debug(
            "Runbook search: query=%r, top results=%s",
            query[:80],
            [name for name, _ in results],
        )
        return results

    def get_runbook(self, name: str) -> str | None:
        """Return the raw markdown content of a specific runbook by name."""
        for doc_name, text in self.docs:
            if doc_name == name or doc_name.replace(".md", "") == name.replace(".md", ""):
                return text
        return None

    def list_runbooks(self) -> list[str]:
        """Return names of all loaded runbooks."""
        return [name for name, _ in self.docs]

    def __len__(self) -> int:
        return len(self.docs)
