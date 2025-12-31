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
            "stats": {"total_processed": 0, "corrections_made": 0}
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

    def record_acceptance(self, file_meta):
        self.memory["stats"]["total_processed"] += 1
        self._save_memory()

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
    """Tracks series numbering across session."""

    def __init__(self):
        self.series = {}

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
