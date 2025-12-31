#!/bin/bash
# Simple launcher for AI File Organizer - Double-click this file to run!

# Get the directory where this script is located (so it works from anywhere)
cd "$(dirname "$0")"

# Check if virtual environment exists, activate it if it does
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed!"
    echo "Please install Python 3 from https://www.python.org/downloads/"
    read -p "Press Enter to exit..."
    exit 1
fi

# Check if dependencies are installed
if ! python3 -c "import rich" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    python3 -m pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "❌ Error: Failed to install dependencies!"
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

# Check if .env file exists and has GROQ_API_KEY
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found!"
    echo "Creating .env file..."
    echo "GROQ_API_KEY=" > .env
    echo ""
    echo "Please get a free API key from https://console.groq.com"
    read -p "Enter your Groq API key: " api_key
    echo "GROQ_API_KEY=$api_key" > .env
fi

# Run the organizer in interactive mode
echo ""
echo "🚀 Starting AI File Organizer..."
echo ""
python3 organizer.py --interactive

# Keep terminal open after completion
echo ""
read -p "Press Enter to close..."
