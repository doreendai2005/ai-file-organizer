import json
import shutil
from pathlib import Path
from rich.console import Console

from .config import PROJECT_ROOT

console = Console()

class UndoHistory:
    """Track file moves to enable undo functionality"""

    def __init__(self):
        self.history_file = PROJECT_ROOT / "undo_history.json"
        self.history = self._load_history()
        self.current_session_moves = []  # moves in current session only

    def _load_history(self):
        """Load undo history from disk"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {"sessions": []}

    def _save_history(self):
        """Save undo history to disk"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f, indent=2)
        except IOError as e:
            console.print(f"[dim]Warning: Could not save undo history: {e}[/dim]")

    def record_move(self, source_path, dest_path, action="moved"):
        """Record a file move operation"""
        move_record = {
            "source": str(source_path),
            "destination": str(dest_path),
            "action": action,  # "moved", "trashed", etc.
            "timestamp": str(Path(dest_path).stat().st_mtime) if Path(dest_path).exists() else ""
        }

        self.current_session_moves.append(move_record)

    def save_session(self, session_label=""):
        """Save current session moves to history"""
        if not self.current_session_moves:
            return

        import datetime
        session = {
            "label": session_label or f"Session {len(self.history['sessions']) + 1}",
            "timestamp": datetime.datetime.now().isoformat(),
            "moves": self.current_session_moves
        }

        self.history["sessions"].append(session)

        # Keep only last 10 sessions to avoid bloat
        if len(self.history["sessions"]) > 10:
            self.history["sessions"] = self.history["sessions"][-10:]

        self._save_history()
        self.current_session_moves = []  # reset for next session

    def undo_last_session(self):
        """Undo all moves from the last session"""
        if not self.history["sessions"]:
            console.print("[yellow]No sessions to undo[/yellow]")
            return False

        last_session = self.history["sessions"][-1]
        console.print(f"\n[bold]Undoing session: {last_session['label']}[/bold]")
        console.print(f"[dim]({len(last_session['moves'])} files)[/dim]\n")

        success_count = 0
        error_count = 0

        # Undo in reverse order
        for move in reversed(last_session["moves"]):
            source = Path(move["source"])
            dest = Path(move["destination"])

            if not dest.exists():
                console.print(f"[yellow]⚠[/yellow]  File not found: {dest.name}")
                error_count += 1
                continue

            try:
                # Move file back to original location
                if source.exists():
                    # Original location exists - add suffix to avoid overwrite
                    from .utils import get_unique_path
                    source = get_unique_path(source.parent, source.name)

                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dest), str(source))
                console.print(f"[green]✓[/green] {dest.name} → {source}")
                success_count += 1

            except Exception as e:
                console.print(f"[red]✗[/red] Failed to undo {dest.name}: {e}")
                error_count += 1

        # Remove session from history after successful undo
        self.history["sessions"].pop()
        self._save_history()

        console.print(f"\n[bold]Undo complete:[/bold] {success_count} restored, {error_count} errors")
        return True

    def show_history(self, limit=5):
        """Show recent undo history"""
        if not self.history["sessions"]:
            console.print("[dim]No undo history available[/dim]")
            return

        console.print(f"\n[bold]Recent Sessions (last {limit}):[/bold]\n")

        for i, session in enumerate(self.history["sessions"][-limit:], 1):
            console.print(f"  {i}. {session['label']} - {len(session['moves'])} files")
            console.print(f"     [dim]{session['timestamp'][:19]}[/dim]")

    def clear_history(self):
        """Clear all undo history"""
        self.history = {"sessions": []}
        self._save_history()
        console.print("[dim]Undo history cleared[/dim]")
