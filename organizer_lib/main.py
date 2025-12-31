import shutil
import time
import argparse
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from rich.console import Console
from rich.panel import Panel

from .config import (
    DESTINATION_ROOT, TRASH_DIR, HIGH_CONFIDENCE_THRESHOLD,
    FOLDER_BATCH_MODE, LOW_CONFIDENCE_THRESHOLD, MIN_FILES_FOR_FOLDER_GROUPING  # import the new threshold config
)
from .utils import (
    get_file_metadata, get_unique_path, get_timestamp_for_season,
    open_file_externally, get_season
)
from .trackers import MemoryTracker, SeriesTracker, CategoryTracker
from .ai_handler import analyze_files_with_ai, generate_new_name

console = Console()

def format_confidence_display(ai_result):
    """Format confidence score with color coding and reasons."""
    confidence = ai_result.get("confidence", 0.5)
    reasons = ai_result.get("confidence_reasons", [])
    strategy = ai_result.get("naming_strategy", "unknown")
    original_quality = ai_result.get("original_filename_quality", "unknown")

    if confidence >= HIGH_CONFIDENCE_THRESHOLD:
        color = "green"
        level = "HIGH"
    elif confidence >= LOW_CONFIDENCE_THRESHOLD:
        color = "yellow"
        level = "MEDIUM"
    else:
        color = "red"
        level = "LOW"

    confidence_str = f"[{color}]{level} ({confidence:.0%})[/{color}]"

    strategy_display = f"Strategy: {strategy}"
    if strategy == "use-original":
        strategy_display += " (keeping original name)"
    elif strategy == "refine-original":
        refined = ai_result.get("refined_from_original", "?")
        strategy_display += f" (refined from: {refined})"
    else:
        strategy_display += " (new AI description)"

    return {
        "confidence_str": confidence_str,
        "strategy_display": strategy_display,
        "original_quality": f"Original name quality: {original_quality}",
        "reasons": reasons,
        "confidence_value": confidence
    }

def infer_context_from_folder(folder_name, category_tracker):
    """Tries to match folder name to an existing category."""
    if not category_tracker:
        return None, 0.0

    folder_lower = folder_name.lower().strip()
    all_cats = category_tracker.get_all_categories()

    for cat in all_cats:
        if cat.lower() == folder_lower:
            return cat, 0.95

    for cat in all_cats:
        cat_lower = cat.lower()
        if cat_lower.replace('p', '').replace('-', '') in folder_lower.replace('-', '').replace('_', ''):
            return cat, 0.85
        if folder_lower in cat_lower or cat_lower in folder_lower:
            return cat, 0.75

    return None, 0.0

def review_single_file(file_path, meta, ai_result, file_index, total_files, series_tracker=None, auto_accept_high_confidence=True, category_tracker=None, memory_tracker=None):
    """Review a single file with confidence display and auto-accept."""
    context = ai_result.get("context", "Misc")
    desc = ai_result.get("description", "File")
    confidence = ai_result.get("confidence", 0.5)
    original_context = context
    original_desc = desc
    original_timestamp = meta["created"]

    if auto_accept_high_confidence and confidence >= HIGH_CONFIDENCE_THRESHOLD:
        timing = None
        if category_tracker:
            timing = category_tracker.get_timing_for_context(context)
        if not timing and memory_tracker:
            timing = memory_tracker.get_timing_for_context(context)
        if timing:
            year, season = timing
            meta["created"] = get_timestamp_for_season(year, season)

        new_name = generate_new_name(meta, ai_result, series_tracker)
        created_dt = datetime.datetime.fromtimestamp(meta["created"])
        
        season = get_season(created_dt)
        dest_folder = DESTINATION_ROOT / f"{created_dt.year}-{season}" / context
        
        dest_folder.mkdir(parents=True, exist_ok=True)
        final_path = get_unique_path(dest_folder, new_name)
        shutil.move(str(file_path), str(final_path))

        conf_display = format_confidence_display(ai_result)
        console.print(f"[green]AUTO[/green] [{file_index}/{total_files}] {conf_display['confidence_str']} {file_path.name}")
        console.print(f"     → {final_path.name}")

        if memory_tracker:
            memory_tracker.record_acceptance(meta)

        return (True, "moved")

    timing = None
    if category_tracker:
        timing = category_tracker.get_timing_for_context(context)
    if not timing and memory_tracker:
        timing = memory_tracker.get_timing_for_context(context)
    if timing:
        year, season = timing
        meta["created"] = get_timestamp_for_season(year, season)

    while True:
        ai_result_copy = ai_result.copy()
        ai_result_copy["context"] = context
        ai_result_copy["description"] = desc
        
        new_name = generate_new_name(meta, ai_result_copy, series_tracker)
        date_display = datetime.datetime.fromtimestamp(meta["created"]).strftime("%Y-%m-%d")
        created_dt = datetime.datetime.fromtimestamp(meta["created"])
        season = get_season(created_dt)
        dest_folder = DESTINATION_ROOT / f"{created_dt.year}-{season}" / context

        conf_display = format_confidence_display(ai_result)
        neighbors = meta.get("neighboring_files", [])[:3]

        console.clear()
        console.print(Panel(
            f"[bold cyan]File {file_index} of {total_files}[/bold cyan]\n\n"
            f"[bold]Source:[/bold] {file_path}\n"
            f"[bold]Destination:[/bold] [green]{dest_folder / new_name}[/green]\n\n"
            f"[bold]Confidence:[/bold] {conf_display['confidence_str']}\n"
            f"[dim]{conf_display['strategy_display']}[/dim]\n"
            f"[dim]{conf_display['original_quality']}[/dim]\n"
            f"[dim]Reasons: {', '.join(conf_display['reasons'][:2]) if conf_display['reasons'] else 'none'}[/dim]\n\n"
            f"[dim]Size: {meta['size']/1024:.0f}KB | Context: {context} | Date: {date_display}[/dim]\n\n"
            f"[bold]Neighboring Files:[/bold] [dim]{', '.join(neighbors) if neighbors else 'None'}[/dim]\n\n"
            f"[bold]Content Preview:[/bold]\n[dim]{meta.get('content_preview', 'No preview')[:300]}[/dim]",
            title="Review"
        ))

        console.print("\n[bold]Actions:[/bold]")
        console.print("  [green]Enter[/green]  Accept and move file")
        console.print("  [yellow]o[/yellow]      Open file (external)")
        console.print("  [yellow]c[/yellow]      Change context")
        console.print("  [yellow]d[/yellow]      Change description")
        console.print("  [yellow]t[/yellow]      Change timestamp")
        console.print("  [blue]s[/blue]      Skip this file")
        console.print("  [red]x[/red]      Move to Trash")
        console.print("  [red]q[/red]      Quit\n")

        action = console.input("[bold yellow]> [/bold yellow]").lower().strip()

        if action == "":
            dest_folder.mkdir(parents=True, exist_ok=True)
            final_path = get_unique_path(dest_folder, new_name)
            shutil.move(str(file_path), str(final_path))
            
            if memory_tracker:
                if context != original_context:
                    memory_tracker.record_correction(meta, original_context, context, "context")
                if desc != original_desc:
                    memory_tracker.record_correction(meta, original_desc, desc, "description")
                if meta["created"] != original_timestamp:
                    memory_tracker.record_correction(meta, str(original_timestamp), str(meta["created"]), "timestamp")
                memory_tracker.record_acceptance(meta)
            return (True, "moved")

        elif action == "o":
            open_file_externally(file_path)

        elif action == "c":
            if category_tracker:
                all_cats = category_tracker.get_all_categories()
                console.print(f"\n[bold]Available categories:[/bold]")
                cols = 4
                for idx, cat in enumerate(all_cats):
                    end_char = "\n" if (idx + 1) % cols == 0 else "  "
                    console.print(f"[dim]{idx+1:2}.[/dim] {cat}", end=end_char)
                console.print()
            new_context = console.input(f"[yellow]New context[/yellow] (current: {context}, # or name): ").strip()
            if new_context:
                if category_tracker and new_context.isdigit():
                    idx = int(new_context) - 1
                    all_cats = category_tracker.get_all_categories()
                    if 0 <= idx < len(all_cats):
                        context = all_cats[idx]
                    else:
                        console.print("[red]Invalid number[/red]")
                        time.sleep(0.5)
                else:
                    context = new_context
                    if category_tracker and category_tracker.add_category(new_context):
                        console.print(f"[dim]Added '{new_context}' to saved categories[/dim]")
                        time.sleep(0.5)

                timing = None
                if category_tracker:
                    timing = category_tracker.get_timing_for_context(context)
                if not timing and memory_tracker:
                    timing = memory_tracker.get_timing_for_context(context)
                if timing:
                    year, season = timing
                    meta["created"] = get_timestamp_for_season(year, season)
                    console.print(f"[dim]Auto-set timing to {year}-{season}[/dim]")
                    time.sleep(0.5)

        elif action == "d":
            new_desc = console.input(f"[yellow]New description[/yellow] (current: {desc}): ").strip()
            if new_desc:
                desc = new_desc

        elif action == "t":
            console.print("\n[bold]Choose season:[/bold]")
            console.print("  [dim]1.[/dim] Winter  [dim]2.[/dim] Spring  [dim]3.[/dim] Summer  [dim]4.[/dim] Fall")
            year_str = console.input("[yellow]Year[/yellow] (e.g. 2024): ").strip()
            season_str = console.input("[yellow]Season[/yellow] (1-4 or name): ").strip()
            try:
                year = int(year_str)
                season_map = {"1": "Winter", "2": "Spring", "3": "Summer", "4": "Fall",
                             "winter": "Winter", "spring": "Spring", "summer": "Summer", "fall": "Fall"}
                season = season_map.get(season_str.lower(), season_str.capitalize())
                if season in ["Winter", "Spring", "Summer", "Fall"]:
                    meta["created"] = get_timestamp_for_season(year, season)
                    if memory_tracker:
                        memory_tracker.record_timing_for_context(context, year, season)
                        console.print(f"[dim]Set timing to {year}-{season} (learned for {context})[/dim]")
                    else:
                        console.print(f"[dim]Set timing to {year}-{season}[/dim]")
                    time.sleep(0.5)
                else:
                    console.print("[red]Invalid season[/red]")
                    time.sleep(1)
            except ValueError:
                console.print("[red]Invalid year[/red]")
                time.sleep(1)

        elif action == "x":
            TRASH_DIR.mkdir(exist_ok=True)
            trash_path = get_unique_path(TRASH_DIR, file_path.name)
            shutil.move(str(file_path), str(trash_path))
            return (True, "trashed")

        elif action == "s":
            return (True, "skipped")

        elif action == "q":
            return (False, "quit")

def review_folder_batch(folder_info, all_file_metas, ai_results, series_tracker, category_tracker, memory_tracker, folder_index, total_folders):
    folder_path = folder_info["path"]
    folder_name = folder_info["name"]
    files = folder_info["files"]
    file_count = len(files)

    # Check if memory tracker has a strong pattern for this folder (user has corrected files from this folder multiple times)
    learned_context = None
    learned_confidence = 0.0
    if memory_tracker and folder_name in memory_tracker.memory.get("folder_patterns", {}):  # user has corrected files from this folder before
        folder_patterns = memory_tracker.memory["folder_patterns"][folder_name]
        if folder_patterns:  # if there are any patterns for this folder
            # Get the most common category user chose for this folder
            most_common_cat = max(folder_patterns.items(), key=lambda x: x[1])  # (category, count) tuple
            correction_count = most_common_cat[1]
            if correction_count >= 2:  # if user corrected 2+ files from this folder to same category, trust it!
                learned_context = most_common_cat[0]
                learned_confidence = min(0.95, 0.75 + (correction_count * 0.05))  # higher confidence with more corrections

    inferred_context, infer_confidence = infer_context_from_folder(folder_name, category_tracker)

    # Prefer learned context over inferred (user corrections > category matching)
    if learned_context and learned_confidence > infer_confidence:  # learned pattern is stronger
        default_context = learned_context
        best_confidence = learned_confidence
        console.print(f"[dim]📚 Learned pattern: '{folder_name}' → '{learned_context}' (from {correction_count} corrections)[/dim]")
    elif inferred_context and infer_confidence >= 0.75:  # category matching worked
        default_context = inferred_context
        best_confidence = infer_confidence
    else:  # fall back to AI suggestion
        first_ai = ai_results[0] if ai_results else {}
        default_context = first_ai.get("context", "Misc")
        best_confidence = infer_confidence
    
    # Auto-apply if confidence is high enough (either learned or inferred)
    if (learned_context and learned_confidence >= 0.85) or infer_confidence >= 0.85:  # auto-apply strong patterns
        used_context = learned_context if learned_confidence > infer_confidence else inferred_context
        source = "learned from corrections" if learned_confidence > infer_confidence else "inferred from name"
        console.print(f"\n[green]AUTO-FOLDER[/green] {folder_name} → [bold]{used_context}[/bold] ({file_count} files, {source})")
        return ("auto", used_context, None)

    console.clear()
    sample_files = [f.name for f in files[:5]]
    more_count = file_count - len(sample_files)
    first_meta = all_file_metas[0] if all_file_metas else {}
    preview = first_meta.get("content_preview", "No preview")[:200]

    console.print(Panel(
        f"[bold cyan]Folder {folder_index} of {total_folders}[/bold cyan]\n\n"
        f"[bold]Folder:[/bold] {folder_path}\n"
        f"[bold]Files:[/bold] {file_count} files\n\n"
        f"[bold]Sample files:[/bold]\n" + "\n".join(f"  • {f}" for f in sample_files) +
        (f"\n  [dim]...and {more_count} more[/dim]" if more_count > 0 else "") +
        f"\n\n[bold]Suggested context:[/bold] [yellow]{default_context}[/yellow]" +
        (f" [dim](inferred from folder name)[/dim]" if infer_confidence >= 0.5 else "") +
        f"\n\n[bold]First file preview:[/bold]\n[dim]{preview}[/dim]",
        title="Folder Review"
    ))

    console.print("\n[bold]Actions:[/bold]")
    console.print(f"  [green]Enter[/green]  Accept '{default_context}' for all")
    console.print("  [yellow]c[/yellow]      Change context for this folder")
    console.print("  [blue]r[/blue]      Review individually")
    console.print("  [blue]s[/blue]      Skip folder")
    console.print("  [red]q[/red]      Quit\n")

    action = console.input("[bold yellow]> [/bold yellow]").lower().strip()

    if action == "":
        return ("batch", default_context, None)
    elif action == "c":
        if category_tracker:
            all_cats = category_tracker.get_all_categories()
            console.print(f"\n[bold]Available categories:[/bold]")
            cols = 4
            for idx, cat in enumerate(all_cats):
                end_char = "\n" if (idx + 1) % cols == 0 else "  "
                console.print(f"[dim]{idx+1:2}.[/dim] {cat}", end=end_char)
            console.print()
        new_context = console.input(f"[yellow]Context[/yellow] (# or name): ").strip()
        if new_context:
            if category_tracker and new_context.isdigit():
                idx = int(new_context) - 1
                all_cats = category_tracker.get_all_categories()
                if 0 <= idx < len(all_cats):
                    new_context = all_cats[idx]
            if category_tracker and category_tracker.add_category(new_context):
                console.print(f"[dim]Added '{new_context}' to saved categories[/dim]")
            return ("batch", new_context, None)
        return ("batch", default_context, None)
    elif action == "r":
        return ("individual", None, None)
    elif action == "s":
        return ("skip", None, None)
    elif action == "q":
        return ("quit", None, None)
    return ("batch", default_context, None)

def batch_process_folder_files(files, metas, context, series_tracker, category_tracker, memory_tracker):
    stats = {"moved": 0, "errors": 0}
    timing = None
    if category_tracker:
        timing = category_tracker.get_timing_for_context(context)
    if not timing and memory_tracker:
        timing = memory_tracker.get_timing_for_context(context)

    for file_path, meta in zip(files, metas):
        try:
            if timing:
                year, season = timing
                meta["created"] = get_timestamp_for_season(year, season)

            created_dt = datetime.datetime.fromtimestamp(meta["created"])
            season = get_season(created_dt)
            
            ai_result = {
                "naming_strategy": "refine-original",
                "context": context,
                "description": meta["original_stem"].replace("_", "-").replace(" ", "-").lower(),
                "confidence": 0.9,
                "is_series": False
            }

            new_name = generate_new_name(meta, ai_result, series_tracker)
            dest_folder = DESTINATION_ROOT / f"{created_dt.year}-{season}" / context
            dest_folder.mkdir(parents=True, exist_ok=True)
            final_path = get_unique_path(dest_folder, new_name)
            shutil.move(str(file_path), str(final_path))
            console.print(f"  [green]✓[/green] {file_path.name} → {final_path.name}")
            stats["moved"] += 1
            if memory_tracker:
                memory_tracker.record_acceptance(meta)
        except Exception as e:
            console.print(f"  [red]✗[/red] {file_path.name}: {e}")
            stats["errors"] += 1
    return stats

def group_files_by_folder(files, scan_dir):  # added scan_dir parameter to detect top-level loose files
    """Smart folder grouping that avoids treating all desktop files as one folder"""
    folders = {}
    loose_files = []  # files in the scan directory itself, not in subfolders

    for f in files:
        folder_path = str(f.parent)
        if f.parent == scan_dir:  # file is directly in scan dir (Desktop, Downloads, etc.), not in a subfolder
            loose_files.append(f)  # treat these individually, not as one giant "Desktop" folder
        else:
            if folder_path not in folders:
                folders[folder_path] = {"path": f.parent, "files": [], "name": f.parent.name}
            folders[folder_path]["files"].append(f)

    # Filter out tiny folders (< MIN_FILES_FOR_FOLDER_GROUPING files) and add them to loose_files
    meaningful_folders = {}  # folders with enough files to warrant batch processing
    for folder_path, folder_info in folders.items():
        file_count = len(folder_info["files"])
        if file_count >= MIN_FILES_FOR_FOLDER_GROUPING:  # only group folders with enough files
            meaningful_folders[folder_path] = folder_info
        else:
            # Tiny folder - process files individually instead of as a folder batch
            loose_files.extend(folder_info["files"])

    return meaningful_folders, loose_files  # return both grouped folders and loose files

def choose_directory():
    """Interactive directory chooser with file count preview"""
    from .config import SUPPORTED_EXTENSIONS  # import here to show file counts

    common_dirs = {
        "1": ("Downloads", Path.home() / "Downloads"),
        "2": ("Desktop", Path.home() / "Desktop"),
        "3": ("Documents", Path.home() / "Documents"),
    }

    console.print("\n[bold cyan]📁 Choose a directory to organize:[/bold cyan]\n")

    # Show file counts for each directory
    for key, (name, path) in common_dirs.items():
        if path.exists():
            try:
                file_count = sum(1 for f in path.rglob('*') if f.is_file() and not f.name.startswith('.') and f.suffix.lower() in SUPPORTED_EXTENSIONS)
                console.print(f"  [yellow]{key}[/yellow]  {name:<15} [dim]({file_count} files)[/dim]")
            except:
                console.print(f"  [yellow]{key}[/yellow]  {name:<15} [dim](unable to count)[/dim]")
        else:
            console.print(f"  [yellow]{key}[/yellow]  {name:<15} [dim](doesn't exist)[/dim]")

    console.print("  [yellow]4[/yellow]  Enter custom path\n")

    try:
        choice = console.input("[bold yellow]Your choice > [/bold yellow]").strip()
    except EOFError:
        return common_dirs["1"][1]

    if choice in common_dirs:
        return common_dirs[choice][1]
    elif choice == "4":
        custom_path = console.input("[yellow]Enter full path:[/yellow] ").strip()
        return Path(custom_path).expanduser()

    return common_dirs["1"][1]  # default to Downloads

def interactive_setup():
    """Simple interactive setup wizard for non-technical users"""
    console.clear()
    console.print(Panel(
        "[bold cyan]🤖 AI File Organizer[/bold cyan]\n\n"
        "This tool helps you organize files into a clean folder structure\n"
        "using AI to categorize them automatically.\n\n"
        "[dim]Files will be organized into:[/dim]\n"
        "[dim]~/Documents/Organized/YYYY-Season/Category/filename[/dim]",
        title="Welcome"
    ))

    # Step 1: Choose directory
    scan_dir = choose_directory()

    if not scan_dir.exists():
        console.print(f"\n[red]❌ Directory not found:[/red] {scan_dir}")
        return None, None, None

    # Step 2: Choose mode
    console.print("\n[bold cyan]⚙️  Choose processing mode:[/bold cyan]\n")
    console.print("  [yellow]1[/yellow]  Smart mode [green](Recommended)[/green]")
    console.print("      [dim]• Auto-groups folders with similar files[/dim]")
    console.print("      [dim]• Auto-accepts high-confidence suggestions[/dim]")
    console.print("      [dim]• Learns from your corrections[/dim]\n")
    console.print("  [yellow]2[/yellow]  Review mode")
    console.print("      [dim]• Review every file manually[/dim]")
    console.print("      [dim]• No auto-accept[/dim]\n")
    console.print("  [yellow]3[/yellow]  Folder-only mode")
    console.print("      [dim]• Only process files in subfolders[/dim]")
    console.print("      [dim]• Skip loose files[/dim]\n")

    try:
        mode_choice = console.input("[bold yellow]Your choice (1-3) > [/bold yellow]").strip()
    except EOFError:
        mode_choice = "1"

    if mode_choice == "1":
        folder_mode = True
        auto_accept = True
    elif mode_choice == "2":
        folder_mode = False
        auto_accept = False
    elif mode_choice == "3":
        folder_mode = True
        auto_accept = True
    else:
        folder_mode = True
        auto_accept = True

    return scan_dir, folder_mode, auto_accept

def process_files(scan_dir, batch_size=3, recursive=False, auto_accept=True, folder_mode=None):
    series_tracker = SeriesTracker()
    category_tracker = CategoryTracker()
    memory_tracker = MemoryTracker()
    
    if recursive:
        iterator = scan_dir.rglob('*')
    else:
        iterator = scan_dir.iterdir()
    
    from .config import SUPPORTED_EXTENSIONS
    files = [f for f in iterator if f.is_file() and not f.name.startswith('.') and f.suffix.lower() in SUPPORTED_EXTENSIONS]
    
    if not files:
        console.print(f"[yellow]No supported files found in {scan_dir}[/yellow]")
        return
        
    files.sort(key=lambda x: x.stat().st_ctime, reverse=True)
    total = len(files)
    stats = {"moved": 0, "trashed": 0, "skipped": 0, "auto_accepted": 0, "folder_batched": 0}
    
    console.print(f"[bold green]Found {total} files to process...[/bold green]")
    use_folder_mode = folder_mode if folder_mode is not None else FOLDER_BATCH_MODE
    folders, loose_files = group_files_by_folder(files, scan_dir)  # get both meaningful folders and loose files

    console.print(f"[dim]Found {len(folders)} folders with {MIN_FILES_FOR_FOLDER_GROUPING}+ files, {len(loose_files)} loose files[/dim]")  # show user what we found

    if use_folder_mode and len(folders) >= 1:  # process meaningful folders first
        folder_index = 0
        for folder_path, folder_info in folders.items():
            folder_index += 1
            folder_files = folder_info["files"]
            
            # Parallel Metadata Extraction
            with ThreadPoolExecutor() as executor:
                folder_metas = list(executor.map(lambda f: get_file_metadata(f, True), folder_files))
            
            # Filter out None (in case of errors)
            folder_metas = [m for m in folder_metas if m is not None]
            if len(folder_metas) != len(folder_files):
                # Filter files list to match metas
                folder_files = [f for f, m in zip(folder_files, folder_metas) if m is not None]

            sample_size = min(3, len(folder_files))
            with console.status(f"[bold green]Analyzing folder: {folder_info['name']}...[/bold green]"):
                ai_results = analyze_files_with_ai(folder_metas[:sample_size], series_tracker, category_tracker, memory_tracker)
            
            if not ai_results:
                 ai_results = [{"context": "Misc", "confidence": 0.3}]

            action, context, _ = review_folder_batch(
                folder_info, folder_metas, ai_results,
                series_tracker, category_tracker, memory_tracker,
                folder_index, len(folders)
            )

            if action == "quit": break
            elif action == "skip":
                stats["skipped"] += len(folder_files)
                console.print(f"[blue]Skipped[/blue] {len(folder_files)} files")
                continue
            elif action in ("batch", "auto"):
                console.print(f"\n[bold]Processing {len(folder_files)} files with context: {context}[/bold]")
                batch_stats = batch_process_folder_files(folder_files, folder_metas, context, series_tracker, category_tracker, memory_tracker)
                stats["moved"] += batch_stats["moved"]
                stats["folder_batched"] += batch_stats["moved"]
                console.print(f"[green]Done![/green] Moved {batch_stats['moved']} files\n")
                time.sleep(0.5)
            elif action == "individual":
                 for j, (file_path, meta) in enumerate(zip(folder_files, folder_metas)):
                    if j < len(ai_results): result = ai_results[j]
                    else:
                        with console.status(f"[bold green]Analyzing {file_path.name}...[/bold green]"):
                             res = analyze_files_with_ai([meta], series_tracker, category_tracker, memory_tracker)
                             result = res[0] if res else {"context": "Misc", "confidence": 0.3}
                    
                    cont, act = review_single_file(file_path, meta, result, j+1, len(folder_files), series_tracker, auto_accept, category_tracker, memory_tracker)
                    if act in stats: stats[act] += 1
                    if not cont: break

        # After processing folders, handle loose files individually
        if loose_files:  # process loose files if any remain
            console.print(f"\n[bold]Processing {len(loose_files)} loose files individually...[/bold]")
            for i in range(0, len(loose_files), batch_size):
                batch = loose_files[i : i + batch_size]

                with ThreadPoolExecutor() as executor:
                    batch_meta = list(executor.map(lambda f: get_file_metadata(f, True), batch))

                # Filter None
                batch = [b for b, m in zip(batch, batch_meta) if m]
                batch_meta = [m for m in batch_meta if m]
                if not batch: continue

                with console.status("[bold green]Asking AI...[/bold green]"):  # clearer status message
                    ai_results = analyze_files_with_ai(batch_meta, series_tracker, category_tracker, memory_tracker)

                if not ai_results or len(ai_results) != len(batch):
                    ai_results = [{"confidence": 0.3, "context": "Review", "description": "file"} for _ in batch]

                for j, (file_path, meta, result) in enumerate(zip(batch, batch_meta, ai_results)):
                    file_index = i + j + 1
                    cont, act = review_single_file(file_path, meta, result, file_index, len(loose_files), series_tracker, auto_accept, category_tracker, memory_tracker)
                    if act == "moved" and result.get("confidence", 0) >= HIGH_CONFIDENCE_THRESHOLD:
                        stats["auto_accepted"] += 1
                    if act in stats: stats[act] += 1
                    if not cont: return

    else:
        # File batch mode (fallback) - process all files when folder mode is disabled
        for i in range(0, total, batch_size):
            batch = files[i : i + batch_size]
            
            with ThreadPoolExecutor() as executor:
                batch_meta = list(executor.map(lambda f: get_file_metadata(f, True), batch))
            
            # Filter None
            batch = [b for b, m in zip(batch, batch_meta) if m]
            batch_meta = [m for m in batch_meta if m]
            if not batch: continue

            with console.status("[bold green]Asking AI...[/bold green]"):  # clearer status message
                ai_results = analyze_files_with_ai(batch_meta, series_tracker, category_tracker, memory_tracker)

            if not ai_results or len(ai_results) != len(batch):
                ai_results = [{"confidence": 0.3, "context": "Review", "description": "file"} for _ in batch]

            for j, (file_path, meta, result) in enumerate(zip(batch, batch_meta, ai_results)):
                file_index = i + j + 1
                cont, act = review_single_file(file_path, meta, result, file_index, total, series_tracker, auto_accept, category_tracker, memory_tracker)
                if act == "moved" and result.get("confidence", 0) >= HIGH_CONFIDENCE_THRESHOLD:
                    stats["auto_accepted"] += 1
                if act in stats: stats[act] += 1
                if not cont: return

    console.print(Panel(
        f"[bold]Session Summary[/bold]\n\n"
        f"[green]Moved:[/green]   {stats['moved']} ({stats['auto_accepted']} auto, {stats['folder_batched']} batch)\n"
        f"[red]Trashed:[/red] {stats['trashed']}\n"
        f"[blue]Skipped:[/blue] {stats['skipped']}",
        title="Complete"
    ))

def main():
    parser = argparse.ArgumentParser(
        description="AI-powered file organizer with smart naming",
        epilog="Run without arguments for interactive mode"  # tell users about interactive mode
    )
    parser.add_argument("--dir", default=None, help="Folder to scan")
    parser.add_argument("--no-auto-accept", action="store_true", help="Disable auto-accept")
    parser.add_argument("--confidence-threshold", type=float, default=None, help="Confidence threshold (unused currently)")
    parser.add_argument("--no-folder-mode", action="store_true", help="Disable folder batch mode")
    parser.add_argument("--folder-mode", action="store_true", help="Force folder batch mode")
    parser.add_argument("--interactive", action="store_true", help="Force interactive mode (default if no args)")
    args = parser.parse_args()

    # If no arguments provided OR --interactive flag, use interactive wizard for non-technical users
    import sys
    if len(sys.argv) == 1 or args.interactive:  # no arguments = show interactive wizard
        result = interactive_setup()
        if result[0] is None:  # user cancelled or error
            console.print("\n[yellow]Cancelled.[/yellow]")
            return
        scan_path, folder_mode, auto_accept = result
    else:
        # Command-line mode for technical users
        if args.dir:
            scan_path = Path(args.dir)
        else:
            scan_path = choose_directory()

        if not scan_path.exists():
            console.print(f"[red]Directory not found: {scan_path}[/red]")
            return

        folder_mode = True if args.folder_mode else (False if args.no_folder_mode else None)
        auto_accept = not args.no_auto_accept

    # Run the organizer with chosen settings
    process_files(scan_path, recursive=True, auto_accept=auto_accept, folder_mode=folder_mode)

if __name__ == "__main__":
    main()
