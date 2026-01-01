import json
import datetime
from pathlib import Path
from rich.console import Console

from .config import PROJECT_ROOT

console = Console()

class MemoryTracker:
    """Remembers user corrections to improve future AI suggestions."""

    def __init__(self):
        self.memory_file = PROJECT_ROOT / "memory.json"
        self.memory = self._load_memory()

    def _load_memory(self):
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "corrections": [],
            "folder_patterns": {},
            "extension_patterns": {},
            "description_patterns": [],
            "timing_patterns": {},
            "stats": {
                "total_processed": 0,
                "corrections_made": 0,
                "auto_accepted": 0,  # files accepted without changes
                "pattern_matched": 0,  # files matched by pattern rules
                "cache_hits": 0,  # files served from cache
                "sessions": []  # track accuracy per session
            }
        }

    def _save_memory(self):
        try:
            with open(self.memory_file, 'w') as f:
                json.dump(self.memory, f, indent=2)
        except IOError as e:
            console.print(f"[dim]Warning: Could not save memory: {e}[/dim]")

    def record_correction(self, file_meta, ai_suggestion, user_choice, correction_type):
        correction = {
            "timestamp": datetime.datetime.now().isoformat(),
            "type": correction_type,
            "filename": file_meta.get("filename", ""),
            "folder": file_meta.get("folder_name", ""),
            "extension": file_meta.get("extension", ""),
            "ai_suggested": ai_suggestion,
            "user_chose": user_choice,
            "content_preview": file_meta.get("content_preview", "")[:200]
        }
        self.memory["corrections"].append(correction)
        self.memory["stats"]["corrections_made"] += 1

        if correction_type == "context":
            folder = file_meta.get("folder_name", "")
            if folder:
                if folder not in self.memory["folder_patterns"]:
                    self.memory["folder_patterns"][folder] = {}
                if user_choice not in self.memory["folder_patterns"][folder]:
                    self.memory["folder_patterns"][folder][user_choice] = 0
                self.memory["folder_patterns"][folder][user_choice] += 1

            ext = file_meta.get("extension", "")
            if ext:
                if ext not in self.memory["extension_patterns"]:
                    self.memory["extension_patterns"][ext] = {}
                if user_choice not in self.memory["extension_patterns"][ext]:
                    self.memory["extension_patterns"][ext][user_choice] = 0
                self.memory["extension_patterns"][ext][user_choice] += 1

        elif correction_type == "description":
            self.memory["description_patterns"].append({
                "original_stem": file_meta.get("original_stem", ""),
                "ai_suggested": ai_suggestion,
                "user_chose": user_choice,
                "folder": file_meta.get("folder_name", "")
            })
            if len(self.memory["description_patterns"]) > 100:
                self.memory["description_patterns"] = self.memory["description_patterns"][-100:]

        elif correction_type == "timestamp":
            pass

        if len(self.memory["corrections"]) > 200:
            self.memory["corrections"] = self.memory["corrections"][-200:]

        self._save_memory()

    def record_timing_for_context(self, context, year, season):
        if "timing_patterns" not in self.memory:
            self.memory["timing_patterns"] = {}
        self.memory["timing_patterns"][context] = [year, season]
        self._save_memory()

    def get_timing_for_context(self, context):
        if "timing_patterns" not in self.memory:
            return None
        timing = self.memory.get("timing_patterns", {}).get(context)
        if timing:
            return tuple(timing)
        return None

    def record_acceptance(self, file_meta, was_auto=False, was_pattern=False, was_cached=False):
        """Record that a file was accepted (with optional flags for tracking)"""
        self.memory["stats"]["total_processed"] += 1

        if was_auto:  # file was auto-accepted (high confidence)
            self.memory["stats"]["auto_accepted"] = self.memory["stats"].get("auto_accepted", 0) + 1
        if was_pattern:  # file was matched by pattern rule
            self.memory["stats"]["pattern_matched"] = self.memory["stats"].get("pattern_matched", 0) + 1
        if was_cached:  # file was served from cache
            self.memory["stats"]["cache_hits"] = self.memory["stats"].get("cache_hits", 0) + 1

        self._save_memory()

    def start_session(self):
        """Start a new session for tracking stats"""
        self.current_session = {
            "start_time": datetime.datetime.now().isoformat(),
            "files_processed": 0,
            "corrections": 0,
            "auto_accepted": 0,
            "pattern_matched": 0
        }

    def end_session(self):
        """End current session and save stats"""
        if hasattr(self, 'current_session'):
            self.current_session["end_time"] = datetime.datetime.now().isoformat()

            # Calculate accuracy (files that didn't need correction / total)
            total = self.current_session["files_processed"]
            if total > 0:
                accuracy = ((total - self.current_session["corrections"]) / total) * 100
                self.current_session["accuracy"] = round(accuracy, 1)
            else:
                self.current_session["accuracy"] = 0

            # Save session to history
            if "sessions" not in self.memory["stats"]:
                self.memory["stats"]["sessions"] = []

            self.memory["stats"]["sessions"].append(self.current_session)

            # Keep only last 20 sessions to avoid bloat
            if len(self.memory["stats"]["sessions"]) > 20:
                self.memory["stats"]["sessions"] = self.memory["stats"]["sessions"][-20:]

            self._save_memory()
            delattr(self, 'current_session')

    def get_accuracy_stats(self):
        """Get overall and recent accuracy statistics"""
        stats = self.memory["stats"]
        total = stats.get("total_processed", 0)

        if total == 0:
            return {"overall_accuracy": 0, "recent_sessions": []}

        corrections = stats.get("corrections_made", 0)
        overall_accuracy = ((total - corrections) / total) * 100

        recent_sessions = stats.get("sessions", [])[-5:]  # last 5 sessions

        return {
            "overall_accuracy": round(overall_accuracy, 1),
            "total_files": total,
            "corrections": corrections,
            "auto_accepted": stats.get("auto_accepted", 0),
            "pattern_matched": stats.get("pattern_matched", 0),
            "cache_hits": stats.get("cache_hits", 0),
            "recent_sessions": recent_sessions
        }

    def suggest_pattern_rules(self):
        """Analyze corrections and suggest new pattern rules to user"""
        suggestions = []

        # Look for common folder → category patterns with 3+ occurrences
        for folder, categories in self.memory.get("folder_patterns", {}).items():
            for category, count in categories.items():
                if count >= 3:  # pattern detected (user corrected 3+ times)
                    suggestions.append({
                        "type": "folder_pattern",
                        "pattern": f"Files from '{folder}' → '{category}'",
                        "confidence": count,
                        "reason": f"You've corrected this {count} times"
                    })

        # Look for description patterns (similar stems → same category)
        desc_patterns = self.memory.get("description_patterns", [])
        if len(desc_patterns) >= 5:  # need some data to detect patterns
            # Group by similar stems
            from collections import defaultdict
            stem_groups = defaultdict(list)

            for pattern in desc_patterns[-20:]:  # look at recent 20
                original = pattern.get("original_stem", "").lower()
                user_chose = pattern.get("user_chose", "")

                # Extract common words (simple pattern detection)
                words = original.split("_")
                if words:
                    key_word = words[0]  # first word as key
                    stem_groups[key_word].append(user_chose)

            # Find repeated patterns
            for key_word, descriptions in stem_groups.items():
                if len(descriptions) >= 3 and len(set(descriptions)) == 1:  # same correction 3+ times
                    suggestions.append({
                        "type": "filename_pattern",
                        "pattern": f"Files starting with '{key_word}' → '{descriptions[0]}'",
                        "confidence": len(descriptions),
                        "reason": f"Detected pattern in {len(descriptions)} files"
                    })

        return suggestions[:5]  # return top 5 suggestions

    def get_relevant_context(self, file_meta):
        context = {"folder_hints": [], "extension_hints": [], "recent_corrections": []}
        folder = file_meta.get("folder_name", "")
        ext = file_meta.get("extension", "")

        if folder and folder in self.memory["folder_patterns"]:
            patterns = self.memory["folder_patterns"][folder]
            sorted_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:3]
            context["folder_hints"] = [f"{cat} (used {count}x)" for cat, count in sorted_patterns]

        if ext and ext in self.memory["extension_patterns"]:
            patterns = self.memory["extension_patterns"][ext]
            sorted_patterns = sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:3]
            context["extension_hints"] = [f"{cat} (used {count}x)" for cat, count in sorted_patterns]

        for correction in reversed(self.memory["corrections"][-50:]):
            if correction["folder"] == folder or correction["extension"] == ext:
                context["recent_corrections"].append({
                    "type": correction["type"],
                    "filename": correction["filename"],
                    "ai_suggested": correction["ai_suggested"],
                    "user_chose": correction["user_chose"]
                })
            if len(context["recent_corrections"]) >= 5:
                break

        return context

    def get_prompt_context(self, files_metadata):
        if not self.memory["corrections"]:
            return ""

        prompt_parts = ["\nUSER CORRECTION HISTORY (learn from these to improve suggestions):"]

        if self.memory["folder_patterns"]:
            prompt_parts.append("\nFolder → Category mappings (user preferences):")
            for folder, patterns in list(self.memory["folder_patterns"].items())[:10]:
                top_cat = max(patterns.items(), key=lambda x: x[1])
                prompt_parts.append(f"  - Files from '{folder}' → usually '{top_cat[0]}' ({top_cat[1]}x)")

        recent = self.memory["corrections"][-10:]
        if recent:
            prompt_parts.append("\nRecent user corrections (AI was wrong, user fixed):")
            for corr in recent:
                if corr["type"] == "context":
                    prompt_parts.append(f"  - '{corr['filename']}': AI said '{corr['ai_suggested']}' → user chose '{corr['user_chose']}'")
                elif corr["type"] == "description":
                    prompt_parts.append(f"  - '{corr['filename']}': AI desc '{corr['ai_suggested']}' → user preferred '{corr['user_chose']}'")

        stats = self.memory["stats"]
        prompt_parts.append(f"\nStats: {stats['total_processed']} files processed, {stats['corrections_made']} corrections made")

        return "\n".join(prompt_parts)


class SeriesTracker:
    """Tracks series numbering across session with improved detection."""

    def __init__(self):
        self.series = {}

    def detect_series_from_filenames(self, filenames):
        """Detect if files form a series by analyzing filenames"""
        import re

        # Look for common series patterns in filenames
        patterns = [
            r'(\D+?)(\d+)',  # letters followed by numbers (hw1, lecture2)
            r'(\D+)_(\d+)',  # underscore separated (scan_001)
            r'(\D+)-(\d+)',  # hyphen separated (page-01)
        ]

        series_groups = {}  # group files by detected series name

        for filename in filenames:
            stem = Path(filename).stem if isinstance(filename, str) else filename
            for pattern in patterns:
                match = re.search(pattern, stem, re.IGNORECASE)
                if match:
                    series_name = match.group(1).strip('_- ')  # series name (e.g., "hw", "lecture")
                    number = match.group(2)  # the number part

                    if series_name not in series_groups:
                        series_groups[series_name] = []
                    series_groups[series_name].append((stem, int(number)))
                    break  # found a match, don't try other patterns

        # Filter out "series" with only 1 file (not really a series)
        real_series = {k: v for k, v in series_groups.items() if len(v) >= 2}

        return real_series  # {series_name: [(filename, number), ...]}

    def register_file(self, series_name, file_path):
        if series_name not in self.series:
            self.series[series_name] = {"next_num": 1, "files": []}
        num = self.series[series_name]["next_num"]
        self.series[series_name]["files"].append(str(file_path))
        self.series[series_name]["next_num"] += 1
        return num

    def get_series_info(self):
        return {k: {"count": len(v["files"]), "files": v["files"][-3:]}
                for k, v in self.series.items()}


class CategoryTracker:
    """Tracks and persists user categories."""

    def __init__(self):
        self.categories_file = PROJECT_ROOT / "categories.json"
        self.categories = self._load_categories()

    def _load_categories(self):
        if self.categories_file.exists():
            try:
                with open(self.categories_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "academic": ["PHIL-TR013", "SOC-TR011", "WGST-TR000", "CS111", "GER101", "GER102",
                        "GER201", "GER202W", "GER232", "MATH116", "SOC223", "MUS100", "MUS275",
                        "PHIL108Y", "PHIL221", "ARTH100", "PHYS104", "CS-TR000", "ENG-TR002",
                        "ARTS109", "ARTS240", "CPLT275", "CS230P", "CS220", "HIST293", "SOC256",
                        "MIT4031", "CAMS235", "WGST250", "WGST307"],
            "general": ["Personal", "Finance", "Medical", "Identity", "Receipts", "Photos",
                       "Screenshots", "Reference", "Work", "Travel", "Projects"],
            "custom": [],
            "timings": {
                "PHIL-TR013": [2021, "Fall"],
                "SOC-TR011": [2021, "Fall"],
                "WGST-TR000": [2021, "Fall"],
                "CS111": [2021, "Fall"],
                "GER101": [2021, "Fall"],
                "GER102": [2022, "Spring"],
                "GER201": [2022, "Fall"],
                "GER202W": [2023, "Spring"],
                "GER232": [2023, "Fall"],
                "MATH116": [2022, "Spring"],
                "SOC223": [2022, "Spring"],
                "MUS100": [2022, "Spring"],
                "MUS275": [2022, "Fall"],
                "PHIL108Y": [2022, "Fall"],
                "PHIL221": [2023, "Spring"],
                "ARTH100": [2022, "Fall"],
                "PHYS104": [2023, "Spring"],
                "CS-TR000": [2021, "Fall"],
                "ENG-TR002": [2021, "Fall"],
                "ARTS109": [2023, "Fall"],
                "ARTS240": [2024, "Spring"],
                "CPLT275": [2023, "Fall"],
                "CS230P": [2024, "Fall"],
                "CS220": [2024, "Spring"],
                "HIST293": [2024, "Spring"],
                "SOC256": [2024, "Spring"],
                "MIT4031": [2024, "Fall"],
                "CAMS235": [2024, "Fall"],
                "WGST250": [2024, "Fall"],
                "WGST307": [2024, "Fall"]
            }
        }

    def _save_categories(self):
        try:
            with open(self.categories_file, 'w') as f:
                json.dump(self.categories, f, indent=2)
        except IOError as e:
            console.print(f"[dim]Warning: Could not save categories: {e}[/dim]")

    def add_category(self, category):
        category = category.strip()
        all_existing = self.get_all_categories()
        if category and category not in all_existing:
            self.categories["custom"].append(category)
            self._save_categories()
            return True
        return False

    def get_all_categories(self):
        return (self.categories.get("academic", []) +
                self.categories.get("general", []) +
                self.categories.get("custom", []))

    def get_timing_for_context(self, context):
        timings = self.categories.get("timings", {})
        if context in timings:
            return tuple(timings[context])
        return None

    def get_categories_for_prompt(self):
        academic = ", ".join(self.categories.get("academic", []))
        general = ", ".join(self.categories.get("general", []))
        custom = ", ".join(self.categories.get("custom", []))

        result = f"ACADEMIC: {academic}\nGENERAL: {general}"
        if custom:
            result += f"\nUSER CUSTOM: {custom}"
        return result
