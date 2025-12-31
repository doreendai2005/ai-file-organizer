import datetime
import shutil
import subprocess
import pypdf
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS
import io
import base64

from .config import SUPPORTED_EXTENSIONS, NEIGHBOR_COUNT, IMAGE_EXTENSIONS

def get_unique_path(folder, filename):
    """Prevents overwriting by adding (1), (2), etc."""
    path = folder / filename
    if not path.exists():
        return path
    
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while path.exists():
        path = folder / f"{stem}({counter}){suffix}"
        counter += 1
    return path

def get_season(date_obj):
    month = date_obj.month
    if 3 <= month <= 5: return "Spring"
    elif 6 <= month <= 8: return "Summer"
    elif 9 <= month <= 11: return "Fall"
    return "Winter"

def get_timestamp_for_season(year, season):
    """Convert year and season to a timestamp (middle of that season)."""
    season_months = {"Winter": 1, "Spring": 4, "Summer": 7, "Fall": 10}
    month = season_months.get(season, 1)
    date_obj = datetime.datetime(year, month, 15)
    return date_obj.timestamp()

def open_file_externally(file_path):
    """Opens file with default system application (non-blocking)."""
    try:
        subprocess.run(["open", str(file_path)], check=False)
    except Exception:
        pass

def get_file_metadata(file_path, include_neighbors=True):
    """Extract file metadata including neighbors for context."""
    try:
        stats = file_path.stat()
    except FileNotFoundError:
        return None
        
    created_dt = datetime.datetime.fromtimestamp(stats.st_ctime)
    meta = {
        "filename": file_path.name,
        "original_stem": file_path.stem,
        "extension": file_path.suffix.lower(),
        "size": stats.st_size,
        "created": stats.st_ctime,
        "created_date": created_dt.strftime("%Y-%m-%d"),
        "folder_name": file_path.parent.name,
        "folder_path": str(file_path.parent),
        "content_preview": "No preview available",
        "exif": {},
        "neighboring_files": [],
        "image_base64": None
    }

    if include_neighbors:
        try:
            siblings = [
                f.name for f in file_path.parent.iterdir()
                if f.is_file()
                and not f.name.startswith('.')
                and f.suffix.lower() in SUPPORTED_EXTENSIONS
                and f.name != file_path.name
            ]
            siblings.sort()
            meta["neighboring_files"] = siblings[:NEIGHBOR_COUNT]
        except Exception:
            pass

    try:
        if meta["extension"] == '.pdf':
            reader = pypdf.PdfReader(file_path)
            if len(reader.pages) > 0:
                meta["content_preview"] = reader.pages[0].extract_text()[:500]
        elif meta["extension"] in {'.txt', '.md', '.csv'}:
            with open(file_path, 'r', errors='ignore') as f:
                meta["content_preview"] = f.read(500)
        elif meta["extension"] in IMAGE_EXTENSIONS:
            with Image.open(file_path) as img:
                exif_data = img.getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        tag = TAGS.get(tag_id, tag_id)
                        if tag in ['Make', 'Model', 'DateTime', 'DateTimeOriginal', 'GPSInfo', 'ImageDescription']:
                            meta["exif"][tag] = str(value)[:100]

                max_dim = 1024
                if max(img.size) > max_dim:
                    ratio = max_dim / max(img.size)
                    new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)

                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')

                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85)
                meta["image_base64"] = base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception:
        pass
        
    return meta
