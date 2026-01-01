import json
import hashlib
import datetime
from pathlib import Path
from rich.console import Console

from .config import PROJECT_ROOT

console = Console()

class AICache:
    """Cache AI results for similar files to improve performance and reduce API calls"""

    def __init__(self, cache_ttl_hours=24):  # cache valid for 24 hours by default
        self.cache_file = PROJECT_ROOT / "ai_cache.json"
        self.cache_ttl_hours = cache_ttl_hours
        self.cache = self._load_cache()
        self.hits = 0  # track cache performance
        self.misses = 0

    def _load_cache(self):
        """Load cache from disk"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_cache(self):
        """Save cache to disk"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except IOError as e:
            console.print(f"[dim]Warning: Could not save cache: {e}[/dim]")

    def _generate_cache_key(self, file_meta):
        """Generate a cache key based on file characteristics that affect AI analysis"""
        # Key factors: filename, extension, size, folder, content preview snippet
        key_parts = [
            file_meta.get("original_stem", ""),
            file_meta.get("extension", ""),
            str(file_meta.get("size", 0)),
            file_meta.get("folder_name", ""),
            file_meta.get("content_preview", "")[:100],  # first 100 chars only
        ]

        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()  # hash for compact storage

    def _is_cache_valid(self, cache_entry):
        """Check if cache entry is still valid (not expired)"""
        if "timestamp" not in cache_entry:
            return False

        cached_time = datetime.datetime.fromisoformat(cache_entry["timestamp"])
        now = datetime.datetime.now()
        age_hours = (now - cached_time).total_seconds() / 3600

        return age_hours < self.cache_ttl_hours  # cache is valid if younger than TTL

    def get(self, file_meta):
        """Try to get cached AI result for this file"""
        cache_key = self._generate_cache_key(file_meta)

        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if self._is_cache_valid(cache_entry):
                self.hits += 1
                return cache_entry.get("result")

        self.misses += 1
        return None  # cache miss

    def set(self, file_meta, ai_result):
        """Store AI result in cache"""
        cache_key = self._generate_cache_key(file_meta)

        self.cache[cache_key] = {
            "result": ai_result,
            "timestamp": datetime.datetime.now().isoformat(),
            "filename": file_meta.get("filename", "unknown")  # for debugging
        }

        # Periodically clean old entries to keep cache small
        if len(self.cache) > 1000:  # max 1000 entries
            self._clean_old_entries()

        self._save_cache()

    def _clean_old_entries(self):
        """Remove expired cache entries"""
        keys_to_remove = []

        for key, entry in self.cache.items():
            if not self._is_cache_valid(entry):
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self.cache[key]

        console.print(f"[dim]Cache cleanup: removed {len(keys_to_remove)} expired entries[/dim]")

    def get_stats(self):
        """Get cache performance statistics"""
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
            "cache_size": len(self.cache)
        }

    def clear(self):
        """Clear entire cache"""
        self.cache = {}
        self._save_cache()
        console.print("[dim]Cache cleared[/dim]")


class PatternRules:
    """Extension and filename pattern rules for quick categorization without AI"""

    def __init__(self):
        # Common filename patterns mapped to categories (regex patterns)
        self.filename_patterns = {
            r"hw\d+|homework\d+|assignment\d+": ("Academic", 0.8),  # homework files
            r"lecture\d+|lec\d+|notes\d+": ("Academic", 0.8),  # lecture notes
            r"midterm|final|exam\d+": ("Academic", 0.85),  # exams
            r"receipt|invoice": ("Finance", 0.9),  # receipts/invoices
            r"screenshot|screen.?shot": ("Screenshots", 0.9),  # screenshots
            r"IMG_\d{4}|DSC\d{4}": ("Photos", 0.85),  # camera photos
            r"scan\d+|scanned": ("Scans", 0.8),  # scanned documents
        }

        # Extension-based category hints (more general)
        self.extension_hints = {
            ".pdf": [("Academic", 0.3), ("Finance", 0.2), ("Personal", 0.2)],  # PDFs could be many things
            ".png": [("Screenshots", 0.4), ("Photos", 0.3)],
            ".jpg": [("Photos", 0.6), ("Screenshots", 0.2)],
            ".jpeg": [("Photos", 0.6), ("Screenshots", 0.2)],
            ".xlsx": [("Finance", 0.4), ("Work", 0.3)],
            ".docx": [("Academic", 0.3), ("Work", 0.3), ("Personal", 0.2)],
        }

    def match_pattern(self, file_meta):
        """Try to match filename against known patterns"""
        import re

        filename = file_meta.get("original_stem", "").lower()

        for pattern, (category, confidence) in self.filename_patterns.items():
            if re.search(pattern, filename, re.IGNORECASE):
                return {
                    "context": category,
                    "confidence": confidence,
                    "naming_strategy": "refine-original",
                    "description": filename,
                    "source": "pattern_rule",  # indicate this came from pattern matching
                    "pattern": pattern
                }

        return None  # no pattern match

    def get_extension_hint(self, file_meta):
        """Get category hints based on file extension"""
        ext = file_meta.get("extension", "").lower()

        if ext in self.extension_hints:
            hints = self.extension_hints[ext]
            # Return the highest confidence hint
            best_hint = max(hints, key=lambda x: x[1])
            return best_hint  # (category, confidence)

        return None  # no hint for this extension
