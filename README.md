# AI File Organizer 🔧

A small terminal-based tool to help you organize files (PDFs and images) into a standardized directory structure using metadata and optional AI assistance.

---

## ✅ Features

- Scans a directory (optionally recursively) for supported files (.pdf, .png, .jpg, .jpeg, .gif, .webp)
- Extracts basic metadata (size, creation date, image EXIF, PDF text preview when supported)
- **Uses AI to propose file contexts and descriptions** with automatic provider fallback
- **Multiple free AI providers** (Groq, Gemini, Ollama, HuggingFace) — no paid subscriptions required
- Interactive review loop to accept/modify context, description, or skip/trash
- Moves files into `~/Documents/Organized/<YYYY-Season>/<Context>/` with standardized filenames

---

## 🔧 Prerequisites

- Python 3.8+
- macOS (note: the script uses `qlmanage -p` to Quick Look files during review)

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Notes:
- `pypdf` is optional. If it is not installed, PDF parsing will be skipped and an explanatory message is added to metadata.
- `anthropic` is optional. If not installed or if `ANTHROPIC_API_KEY` is not set, AI-assisted naming will be disabled and the tool will fall back to manual review.

---

## 🧭 Usage

Run the organizer from the project root:

```bash
python3 organizer.py --scan-dir ~/Downloads --batch-size 3 -r
```

Options:
- `--scan-dir` : Directory to scan (default `~/Desktop`)
- `--batch-size` : Number of files processed per batch (default 3)
- `-r` / `--recursive` : Recursively scan subdirectories

During interactive review:
- Press Enter to accept the proposed filename and move the file
- `c` to edit or choose a different context
- `d` to edit the description
- `t` to override the date
- `s` to skip
- `x` to move the file to the Trash
- `q` to quit the organizer

Files are moved to `~/Documents/Organized/<YYYY-Season>/<Context>/` with names like:

```
2024-Fall__CS220__Project-Report.pdf
```

---

## 🧪 Tests

Run the test suite with:

```bash
python3 -m pytest -q
```

The repository contains unit tests for the core utilities and AI interaction is mocked for reliable testing.

---

## 🛠 Troubleshooting & Notes

- If you don't want AI integration, simply don't set the `ANTHROPIC_API_KEY` env var and/or don't install the `anthropic` package.
- If `pypdf` is missing, the tool will still run but will not extract PDF previews.
- The script opens files using Quick Look on macOS (`qlmanage -p`). If you're on a different OS you may want to edit/remove the Quick Look invocation in `serial_batch_loop`.

---

## 🤖 AI Integration & Multi-Provider Support

This tool supports multiple free and paid AI providers with automatic fallback on rate limits:

**Supported providers** (in preference order):
1. **Groq** (free tier, very fast, generous limits) — set `GROQ_API_KEY`
2. **Gemini** (free tier available) — set `GEMINI_API_KEY`
3. **Ollama** (completely free, runs locally) — install Ollama, set `OLLAMA_URL`
4. **Anthropic Claude** (may have free credits) — set `ANTHROPIC_API_KEY`
5. **OpenAI** (paid) — set `OPENAI_API_KEY`
6. **HuggingFace** (free tier available) — set `HUGGINGFACE_API_KEY`

**Auto-fallback on rate limits**: If one provider hits a rate limit (429 error), the tool automatically switches to the next available provider.

Environment variables
- `GROQ_API_KEY`: Free Groq API key from https://console.groq.com
- `GEMINI_API_KEY`: Google Gemini API key
- `OLLAMA_URL`: Local Ollama endpoint (default: http://localhost:11434)
- `ANTHROPIC_API_KEY`: Anthropic API key
- `OPENAI_API_KEY`: OpenAI API key
- `HUGGINGFACE_API_KEY`: HuggingFace API token
- `NO_AI`: Set to `1`, `true`, or `yes` to disable AI entirely

CLI flags
- `--ai-status`: Show which AI provider is currently active and rate-limited providers
- `--scan-dir`: Directory to scan
- `--batch-size`: Files per batch
- `-r` / `--recursive`: Recursively scan subdirectories

**Quick start with Groq** (recommended free option):
1. Get a free API key from https://console.groq.com
2. Set the environment variable: `export GROQ_API_KEY=your_key`
3. Run the organizer: `python3 organizer.py --scan-dir ~/Downloads -r`

---

---

## Contributing

Feel free to open an issue or submit a PR to add features, tests, or improve cross-platform compatibility.

---

## License

MIT-style (document your own licence as needed)
