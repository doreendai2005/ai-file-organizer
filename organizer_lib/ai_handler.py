import json
import re
import datetime
from pathlib import Path
from rich.console import Console
from groq import Groq

from .config import GROQ_KEY, IMAGE_EXTENSIONS, VISION_MODEL, TEXT_MODEL
from .utils import get_season

console = Console()

def analyze_image_with_vision(meta, client):
    """Uses Groq vision model to describe image content for better naming."""
    if not meta.get("image_base64"):
        return None

    vision_prompt = """Describe this image briefly for file naming purposes. Focus on:
1. What the image shows (document scan, screenshot, photo, diagram, chart, etc.)
2. Any visible text, labels, or titles
3. Subject matter (academic, personal, work, etc.)
4. If it appears to be part of a series (like multiple scans or screenshots)

Keep response under 100 words. Be specific and factual."""

    try:
        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": vision_prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{meta['image_base64']}"
                        }
                    }
                ]
            }],
            max_tokens=150,
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        console.print(f"[dim]Vision API unavailable: {e}[/dim]")
        return None

def try_parse_json(text):
    """Try multiple strategies to parse potentially malformed JSON."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    fixed = text
    fixed = re.sub(r',\s*}', '}', fixed)
    fixed = re.sub(r',\s*\]', ']', fixed)
    fixed = fixed.replace("'", '"')
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    match = re.search(r'\[.*\]', fixed, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None

def analyze_files_with_ai(files_metadata, series_tracker=None, category_tracker=None, memory_tracker=None):
    """Sends file metadata to Groq for smart categorization with naming strategy."""
    if not GROQ_KEY:
        console.print("[red]Error: GROQ_API_KEY not found in .env[/red]")
        return None

    client = Groq(api_key=GROQ_KEY)

    # Step 1: For images, get vision descriptions first
    for meta in files_metadata:
        if meta["extension"] in IMAGE_EXTENSIONS and meta.get("image_base64"):
            with console.status(f"[bold green]Analyzing image: {meta['filename']}...[/bold green]"):
                vision_desc = analyze_image_with_vision(meta, client)
                if vision_desc:
                    meta["vision_description"] = vision_desc
                    meta["content_preview"] = f"[Vision]: {vision_desc}"

    # Step 2: Build detailed info string
    items_str = ""
    for i, meta in enumerate(files_metadata):
        preview = meta.get("content_preview", "")[:500]
        exif_str = ", ".join(f"{k}: {v}" for k, v in meta.get("exif", {}).items()) or "none"
        neighbors = ", ".join(meta.get("neighboring_files", [])[:5]) or "none"

        items_str += (
            f"File {i+1}:\n"
            f"  Original Filename: {meta['filename']}\n"
            f"  Original Stem: {meta.get('original_stem', meta['filename'].rsplit('.', 1)[0])}\n"
            f"  Type: {meta['extension']}\n"
            f"  Size: {meta['size']/1024:.0f}KB\n"
            f"  Folder: {meta.get('folder_name', 'unknown')}\n"
            f"  Folder Path: {meta.get('folder_path', 'unknown')}\n"
            f"  Date: {meta.get('created_date', 'unknown')}\n"
            f"  EXIF: {exif_str}\n"
            f"  Neighboring Files: {neighbors}\n"
            f"  Content Preview: {preview}\n\n"
        )

    series_context = ""
    if series_tracker and series_tracker.get_series_info():
        series_context = f"\nCURRENT SERIES IN SESSION:\n{json.dumps(series_tracker.get_series_info(), indent=2)}\n"

    memory_context = ""
    if memory_tracker:
        memory_context = memory_tracker.get_prompt_context(files_metadata)

    if category_tracker:
        categories_str = category_tracker.get_categories_for_prompt()
    else:
        categories_str = "General: Misc (Fallback)" # Should not happen if tracker initialized

    prompt = f"""You are a file naming assistant for a college student. Analyze these files and decide the BEST naming strategy.

⚠️ CRITICAL: LEARN FROM USER CORRECTIONS BELOW - The user has manually corrected your mistakes before. Pay STRONG attention to these patterns!
{memory_context}

NAMING STRATEGY RULES (choose ONE for each file):
1. "use-original": If original filename already has clear, meaningful info, KEEP it
2. "refine-original": If original has some meaning but needs cleanup, REFINE it
3. "use-new-description": If original is meaningless, CREATE new name

CONTEXT SOURCES (use ALL available info to decide):
- Original filename stem
- Folder path and name (IMPORTANT: check correction history for folder patterns!)
- Neighboring files
- Content preview
- EXIF data

EXISTING CATEGORIES (prefer these):
{categories_str}

NOTE: Only create a new category if NONE of the existing ones fit.

SERIES DETECTION:
- Files that appear to be part of a series (homework 1, 2, 3; lecture notes; scans)
- If detected, assign consistent series_name and suggested_number
- Use 3-digit numbers: 001, 002, 003
{series_context}

FILES TO ANALYZE:
{items_str}

Return ONLY valid JSON.
[
  {{"naming_strategy": "use-original", "original_filename_quality": "high", "context": "CS230P", "description": "binary-tree-hw", "refined_from_original": null, "confidence": 0.9, "confidence_reasons": ["descriptive"], "is_series": false, "series_name": null, "series_number": null}}
]
"""

    try:
        response = client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.2
        )
        content = response.choices[0].message.content
        if not content:
            console.print("[red]Error: AI returned empty response[/red]")
            return None

        console.print(f"[dim]AI raw response: {content[:300]}...[/dim]")

        content = content.replace("```json", "").replace("```", "").strip()
        result = try_parse_json(content)
        
        if result:
            return result

        console.print(f"[red]Could not parse AI response as JSON[/red]")
        return None

    except Exception as e:
        console.print(f"[red]Groq Error:[/red] {e}")
        return None

def generate_new_name(meta, ai_result, series_tracker=None):
    """Creates filename based on AI-determined naming strategy."""
    strategy = ai_result.get("naming_strategy", "use-new-description")
    context = ai_result.get("context", "Misc")
    description = ai_result.get("description", "file")
    created_dt = datetime.datetime.fromtimestamp(meta["created"])
    year = created_dt.year
    season = get_season(created_dt)
    ext = meta["extension"]

    is_series = ai_result.get("is_series") or ai_result.get("series_detection", {}).get("is_series", False)
    series_name = ai_result.get("series_name") or ai_result.get("series_detection", {}).get("series_name")
    series_number = ai_result.get("series_number") or ai_result.get("series_detection", {}).get("suggested_number", 1)

    series_suffix = ""
    if is_series and series_name:
        if series_tracker:
            num = series_tracker.register_file(series_name, meta.get("filename", ""))
        else:
            num = series_number or 1
        series_suffix = f"-{num:03d}"

    if strategy == "use-original":
        original_stem = meta.get("original_stem", Path(meta["filename"]).stem)
        clean_stem = original_stem.replace(" ", "-").replace("_", "-").lower()
        return f"{year}-{season}__{context}__{clean_stem}{series_suffix}{ext}"

    elif strategy == "refine-original":
        refined = ai_result.get("refined_from_original") or description
        clean_desc = refined.replace(" ", "-").replace("_", "-").lower()
        return f"{year}-{season}__{context}__{clean_desc}{series_suffix}{ext}"

    else:
        clean_desc = description.replace(" ", "-").replace("_", "-").lower()
        return f"{year}-{season}__{context}__{clean_desc}{series_suffix}{ext}"
