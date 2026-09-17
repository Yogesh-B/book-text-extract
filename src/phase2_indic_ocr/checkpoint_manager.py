"""Checkpoint manager for Phase 2 IndicOCR batch execution.

Tracks page-by-page progress per book, allowing safe resumption after interruption
or crashes, while ensuring raw OCR outputs remain immutable.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils.logger import get_logger

logger = get_logger("checkpoint_manager")


class CheckpointManager:
    """Manages the state and progress of IndicOCR processing for a book."""

    def __init__(
        self,
        checkpoint_path: Path | str,
        book_slug: str,
        total_pages: int = 0,
    ):
        self.checkpoint_path = Path(checkpoint_path).resolve()
        self.book_slug = book_slug
        self.total_pages = total_pages

        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

        self.completed_pages: List[int] = []
        self.failed_pages: Dict[str, str] = {}
        self.page_stats: Dict[str, Dict[str, Any]] = {}
        self.started_at: str = datetime.now(timezone.utc).isoformat()
        self.last_updated: str = self.started_at
        self.status: str = "in_progress"

        self._load()

    def _load(self) -> None:
        """Load existing checkpoint if present."""
        if not self.checkpoint_path.exists():
            return

        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.completed_pages = sorted(list(set(data.get("completed_pages", []))))
            self.failed_pages = data.get("failed_pages", {})
            self.page_stats = data.get("page_stats", {})
            self.started_at = data.get("started_at", self.started_at)
            if data.get("total_pages") and self.total_pages == 0:
                self.total_pages = data["total_pages"]

            logger.info(
                f"Loaded existing checkpoint for '{self.book_slug}': "
                f"{len(self.completed_pages)} completed, {len(self.failed_pages)} failed."
            )
        except Exception as e:
            logger.warning(f"Failed to read checkpoint at {self.checkpoint_path}: {e}")

    def is_completed(
        self,
        page_num: int,
        raw_json_dir: Optional[Path] = None,
        raw_md_dir: Optional[Path] = None,
    ) -> bool:
        """Check if page is completed and its output files exist on disk."""
        if page_num not in self.completed_pages:
            return False

        filename_base = f"page_{page_num:04d}"
        if raw_json_dir is not None:
            json_file = raw_json_dir / f"{filename_base}.json"
            if not json_file.exists() or json_file.stat().st_size == 0:
                return False

        if raw_md_dir is not None:
            md_file = raw_md_dir / f"{filename_base}.md"
            if not md_file.exists() or md_file.stat().st_size == 0:
                return False

        return True

    def record_success(
        self,
        page_num: int,
        duration_sec: float,
        block_count: int,
    ) -> None:
        """Record successful page processing."""
        if page_num not in self.completed_pages:
            self.completed_pages.append(page_num)
            self.completed_pages.sort()

        # Remove from failures if previously failed
        self.failed_pages.pop(str(page_num), None)

        self.page_stats[str(page_num)] = {
            "duration_sec": round(duration_sec, 2),
            "block_count": block_count,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        self.last_updated = datetime.now(timezone.utc).isoformat()

    def record_failure(self, page_num: int, error_msg: str) -> None:
        """Record page processing error."""
        self.failed_pages[str(page_num)] = str(error_msg)
        self.last_updated = datetime.now(timezone.utc).isoformat()

    def save(self, is_final: bool = False) -> None:
        """Atomically persist checkpoint state to disk."""
        if is_final:
            if self.total_pages > 0 and len(self.completed_pages) >= self.total_pages:
                self.status = "completed"
            elif self.failed_pages:
                self.status = "completed_with_errors"
            else:
                self.status = "partial"

        data = {
            "book_slug": self.book_slug,
            "total_pages": self.total_pages,
            "completed_count": len(self.completed_pages),
            "failed_count": len(self.failed_pages),
            "status": self.status,
            "started_at": self.started_at,
            "last_updated": self.last_updated,
            "completed_pages": self.completed_pages,
            "failed_pages": self.failed_pages,
            "page_stats": self.page_stats,
        }

        # Write atomically via temp file
        temp_path = self.checkpoint_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path.replace(self.checkpoint_path)
        except Exception as e:
            logger.error(f"Failed writing checkpoint to {self.checkpoint_path}: {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def get_pending_pages(self, target_pages: List[int], force: bool = False) -> List[int]:
        """Filter target pages to those not yet completed."""
        if force:
            return list(target_pages)
        return [p for p in target_pages if p not in self.completed_pages]
