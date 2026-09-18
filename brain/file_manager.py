"""
File and Folder CRUD Manager for Neura AI.
Handles creating, reading, updating, deleting, and listing files/folders across the system.
"""

import os
import shutil
from typing import Tuple, List, Optional

class FileManager:
    """
    Handles system File & Directory CRUD operations with user-friendly path resolution.
    """
    def __init__(self, default_workspace: str = None):
        if not default_workspace:
            self.default_workspace = os.path.dirname(os.path.dirname(__file__))
        else:
            self.default_workspace = default_workspace

    def resolve_path(self, target_path: str) -> str:
        """
        Resolves spoken or relative paths into absolute paths.
        Supports keywords: 'desktop', 'downloads', 'documents', 'music', 'home'.
        """
        p = target_path.strip().strip('"\'')
        home = os.path.expanduser("~")

        p_lower = p.lower()
        if p_lower == "desktop" or p_lower.startswith("desktop\\") or p_lower.startswith("desktop/"):
            rest = p[len("desktop"):].lstrip("\\/")
            return os.path.join(home, "Desktop", rest)
        elif p_lower == "downloads" or p_lower.startswith("downloads\\") or p_lower.startswith("downloads/"):
            rest = p[len("downloads"):].lstrip("\\/")
            return os.path.join(home, "Downloads", rest)
        elif p_lower == "documents" or p_lower.startswith("documents\\") or p_lower.startswith("documents/"):
            rest = p[len("documents"):].lstrip("\\/")
            return os.path.join(home, "Documents", rest)
        elif p_lower == "music" or p_lower.startswith("music\\") or p_lower.startswith("music/"):
            rest = p[len("music"):].lstrip("\\/")
            return os.path.join(home, "Music", rest)
        elif p_lower == "home":
            return home

        if os.path.isabs(p):
            return p

        return os.path.join(self.default_workspace, p)

    def create_file(self, filename: str, content: str = "") -> Tuple[bool, str]:
        """Creates a file with optional content."""
        try:
            full_path = self.resolve_path(filename)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            return True, f"File created successfully at {os.path.basename(full_path)}."
        except Exception as e:
            return False, f"Could not create file: {e}"

    def read_file(self, filename: str, max_chars: int = 800) -> Tuple[bool, str]:
        """Reads content from a text file."""
        try:
            full_path = self.resolve_path(filename)
            if not os.path.exists(full_path):
                # Try searching in Desktop or workspace if only a name was passed
                if not os.path.isabs(filename):
                    for alt_base in [self.default_workspace, os.path.join(os.path.expanduser("~"), "Desktop")]:
                        candidate = os.path.join(alt_base, filename)
                        if os.path.exists(candidate):
                            full_path = candidate
                            break

            if not os.path.exists(full_path):
                return False, f"File '{filename}' was not found, Sir."

            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if len(content) > max_chars:
                preview = content[:max_chars] + f"\n... [Truncated {len(content) - max_chars} characters]"
                return True, f"Content of {os.path.basename(full_path)}:\n{preview}"
            elif not content.strip():
                return True, f"The file '{os.path.basename(full_path)}' is currently empty."
            else:
                return True, f"Content of {os.path.basename(full_path)}:\n{content}"
        except Exception as e:
            return False, f"Error reading file: {e}"

    def append_to_file(self, filename: str, content: str) -> Tuple[bool, str]:
        """Appends text to an existing file."""
        try:
            full_path = self.resolve_path(filename)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "a", encoding="utf-8") as f:
                f.write(("\n" if os.path.exists(full_path) and os.path.getsize(full_path) > 0 else "") + content)
            return True, f"Appended text to {os.path.basename(full_path)} successfully, Sir."
        except Exception as e:
            return False, f"Error appending to file: {e}"

    def delete_file(self, filename: str) -> Tuple[bool, str]:
        """Deletes a file safely."""
        try:
            full_path = self.resolve_path(filename)
            if not os.path.exists(full_path):
                # Check Desktop
                desktop_candidate = os.path.join(os.path.expanduser("~"), "Desktop", filename)
                if os.path.exists(desktop_candidate):
                    full_path = desktop_candidate
                else:
                    return False, f"File '{filename}' does not exist, Sir."

            if os.path.isdir(full_path):
                return False, f"'{filename}' is a directory, not a file. Say 'delete folder' instead."

            os.remove(full_path)
            return True, f"File '{os.path.basename(full_path)}' has been deleted, Sir."
        except Exception as e:
            return False, f"Failed to delete file: {e}"

    def create_folder(self, foldername: str) -> Tuple[bool, str]:
        """Creates a directory."""
        try:
            full_path = self.resolve_path(foldername)
            os.makedirs(full_path, exist_ok=True)
            return True, f"Folder '{os.path.basename(full_path)}' created successfully, Sir."
        except Exception as e:
            return False, f"Failed to create folder: {e}"

    def delete_folder(self, foldername: str) -> Tuple[bool, str]:
        """Deletes a directory."""
        try:
            full_path = self.resolve_path(foldername)
            if not os.path.exists(full_path):
                return False, f"Folder '{foldername}' does not exist, Sir."

            shutil.rmtree(full_path)
            return True, f"Folder '{os.path.basename(full_path)}' deleted successfully, Sir."
        except Exception as e:
            return False, f"Failed to delete folder: {e}"

    def list_files(self, foldername: str = "", limit: int = 12) -> Tuple[bool, str]:
        """Lists files in the specified folder or workspace."""
        try:
            full_path = self.resolve_path(foldername) if foldername else self.default_workspace
            if not os.path.exists(full_path):
                return False, f"Folder '{foldername}' not found, Sir."

            items = os.listdir(full_path)
            if not items:
                return True, f"The folder '{os.path.basename(full_path)}' is empty, Sir."

            files = []
            folders = []
            for item in items:
                item_path = os.path.join(full_path, item)
                if os.path.isdir(item_path):
                    folders.append(item + "/")
                else:
                    files.append(item)

            total = len(items)
            display_items = (folders + files)[:limit]
            summary = ", ".join(display_items)
            if total > limit:
                summary += f", and {total - limit} more items."

            return True, f"Files in {os.path.basename(full_path) or 'folder'}: {summary}"
        except Exception as e:
            return False, f"Error listing directory: {e}"
