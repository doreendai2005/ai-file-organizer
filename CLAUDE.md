# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered terminal tool for organizing files (PDFs, images, documents) into a standardized directory structure using metadata extraction and AI-generated categorization. macOS-only (uses Quick Look for file preview).

## Commands

```bash
# Install dependencies (use the existing .venv)
source .venv/bin/activate
pip install -r requirements.txt

# Run the organizer
python3 organizer.py --dir ~/Downloads

# Run tests
python3 -m pytest -q
```

## Architecture

Single-file application (`organizer.py`) with these key components:

- **AI Integration**: Uses OpenAI (`gpt-4o-mini`) via `analyze_files_with_openai()` to batch-analyze files and suggest context/description. Requires `OPENAI_API_KEY` in `.env`.

- **File Processing Flow**:
  1. `process_files()` - Scans directory, filters by `SUPPORTED_EXTENSIONS`, sorts by creation date (newest first), processes in batches
  2. `get_file_metadata()` - Extracts size, dates, content preview (PDF text via pypdf, text file snippets)
  3. `review_single_file()` - Interactive TUI using `rich` for approve/rename/skip/trash actions

- **Naming Convention**: Files are renamed to `{YYYY}-{Season}__{Context}__{description}{ext}` and moved to `~/Documents/Organized/{YYYY-Season}/{Context}/`

- **Duplicate Handling**: `get_unique_path()` appends `(1)`, `(2)`, etc. to prevent overwrites

## Environment Variables

Required in `.env`:
- `OPENAI_API_KEY` - For AI-powered file categorization

Note: README mentions multi-provider support (Groq, Gemini, Ollama, Anthropic, HuggingFace) but current implementation only uses OpenAI.

## Notes
- When making changes (whether adding, changing or removing) add a comment in the same line that explains what you did as if talk to a middleschooler 
