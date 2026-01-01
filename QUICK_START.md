# Quick Start Guide - AI File Organizer

## For Non-Technical Users 👋

### First Time Setup

1. **Get a Free API Key**
   - Go to https://console.groq.com
   - Sign up for a free account
   - Copy your API key

2. **Run the Organizer**
   - Double-click `organize.command` file
   - When prompted, paste your API key
   - Follow the on-screen instructions

### Every Time You Want to Organize Files

1. Double-click `organize.command`
2. Choose which folder to organize (Downloads, Desktop, etc.)
3. Choose a mode:
   - **Smart mode** (Recommended) - Auto-organizes most files
   - **Review mode** - Review every file manually
   - **Folder-only** - Only organize files in subfolders
4. Review and approve the AI suggestions
5. Done! Your files are organized!

### Where Do Files Go?

Files are organized into:
```
~/Documents/Organized/
  ├── 2024-Fall/
  │   ├── CS230P/
  │   ├── Personal/
  │   └── Finance/
  ├── 2024-Winter/
  │   └── ...
```

### Tips for Best Results

- **Let it learn**: After you correct a few files from the same folder, it will remember!
- **Be consistent**: Use the same category names for similar files
- **Check the preview**: You can open files before deciding (press 'o')
- **Don't worry**: Files are moved, not deleted (you can undo manually)

---

## For Technical Users 💻

### Command Line Usage

```bash
# Interactive mode (default)
python3 organizer.py

# Organize specific directory
python3 organizer.py --dir ~/Downloads

# Dry run (preview without moving files)
python3 organizer.py --dir ~/Desktop --dry-run

# Show accuracy statistics
python3 organizer.py --show-stats

# Undo last session
python3 organizer.py --undo

# Disable auto-accept
python3 organizer.py --dir ~/Desktop --no-auto-accept

# Force folder mode
python3 organizer.py --dir ~/Documents --folder-mode
```

### Environment Variables

Create a `.env` file with:
```
GROQ_API_KEY=your_groq_api_key_here
```

### How It Works

1. **Smart Folder Grouping**: Groups folders with 3+ files, processes loose files individually
2. **AI Categorization**: Uses Groq AI to analyze file content and suggest categories
3. **Learning System**: Remembers your corrections and applies patterns automatically
4. **Auto-Apply**: After 2+ corrections for the same folder, auto-applies the pattern

### Customization

Edit `organizer_lib/config.py` to customize:
- `MIN_FILES_FOR_FOLDER_GROUPING` - Minimum files to treat folder as group (default: 3)
- `HIGH_CONFIDENCE_THRESHOLD` - Auto-accept threshold (default: 0.85)
- `SUPPORTED_EXTENSIONS` - File types to process

### Advanced Features

#### Performance & Caching
- **AI Result Caching**: Similar files use cached AI results (faster, fewer API calls)
- **Pattern Rules**: Recognizes common patterns (homework1, receipt_jan) without AI
- **Smart Vision**: Skips vision API for obvious screenshots (saves $)
- **Cache Stats**: Shows hit rate and performance gains in summary

#### Accuracy & Learning
- **Learned Patterns**: After 2+ corrections for same folder → auto-apply category
- **Pattern Suggestions**: Shows detected patterns at end of session
- **Accuracy Tracking**: Tracks accuracy over time with session history
- **Extension Hints**: Smart guesses based on file type
- **Better Series Detection**: Improved number recognition (hw1, lecture-02, scan_001)

#### User Experience
- **Dry Run Mode**: Preview changes without moving files (`--dry-run`)
- **Undo Functionality**: Reverse entire sessions (`--undo`)
- **Undo History**: Tracks last 10 sessions for easy recovery
- **Accuracy Stats**: View performance over time (`--show-stats`)
- **Interactive Mode**: User-friendly menu for non-technical users
- **Double-Click Launcher**: `organize.command` for easy access

#### Smart Features
- **Session Tracking**: Monitors accuracy per session
- **Folder Intelligence**: Groups folders with 3+ files, handles loose files separately
- **Context Memory**: Remembers folder → category mappings
- **Description Learning**: Learns from filename corrections
- **Timing Auto-Set**: Automatically applies learned year/season to categories
