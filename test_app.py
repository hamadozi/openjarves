import unittest
from unittest.mock import patch

import app


class LocalCommandTests(unittest.TestCase):
    def test_time_command(self):
        self.assertIn("It's ", app.handle_local_command("what time is it"))

    def test_unknown_command_falls_through_to_ai(self):
        self.assertIsNone(app.handle_local_command("tell me a story"))

    def test_note_is_saved_locally(self):
        with patch.object(app, "NOTES_DIR") as directory, patch.object(app, "NOTES_FILE") as file_path:
            directory.mkdir = lambda **kwargs: None
            file_path.open.return_value.__enter__.return_value = file_path.open.return_value
            with patch("builtins.open"):
                # Use a normal temporary path to verify the persisted note content.
                import tempfile
                from pathlib import Path
                temp = Path(tempfile.mkdtemp()) / "notes.txt"
                with patch.object(app, "NOTES_DIR", temp.parent), patch.object(app, "NOTES_FILE", temp):
                    result = app.handle_local_command("take a note: test note")
                    self.assertEqual(result, "Saved that in your notes.")
                    self.assertIn("test note", temp.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
