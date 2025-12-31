import os
from pathlib import Path
from dotenv import load_dotenv

# Define Project Root (parent of this library)
PROJECT_ROOT = Path(__file__).parent.parent

# Load environment
load_dotenv(PROJECT_ROOT / ".env", override=True)

# Configuration
DESTINATION_ROOT = Path.home() / "Documents" / "Organized"
TRASH_DIR = Path.home() / ".Trash"
GROQ_KEY = os.getenv("GROQ_API_KEY")

# Supported file types
SUPPORTED_EXTENSIONS = {
    '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp',
    '.txt', '.md', '.docx', '.csv',
    '.zip', '.mov', '.mp4', '.xlsx', '.pptx'
}

# Image Extensions
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

# AI Configuration
VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # Groq Llama 4 vision model
TEXT_MODEL = "llama-3.1-8b-instant"  # fast text model
NEIGHBOR_COUNT = 7
HIGH_CONFIDENCE_THRESHOLD = 0.85
LOW_CONFIDENCE_THRESHOLD = 0.60
FOLDER_BATCH_MODE = True
MIN_FILES_FOR_FOLDER_GROUPING = 3  # minimum files needed to treat folder as a group (not process individually)
