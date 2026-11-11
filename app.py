"""OpenJarves — a small Windows desktop voice assistant."""

from __future__ import annotations

import os
import re
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv
from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

load_dotenv()
APP_NAME = "OpenJarves"
WAKE_WORDS = ("open jarves", "openjarves", "jarvis")
NOTES_DIR = Path(os.getenv("APPDATA", Path.home())) / "OpenJarves"
NOTES_FILE = NOTES_DIR / "notes.txt"


def handle_local_command(text: str) -> str | None:
    """Handle a small, deliberately allow-listed set of local actions."""
    command = text.strip()
    low = command.lower()

    if low.startswith(("take a note", "make a note", "note ", "remember ")):
        note = re.sub(r"^(take a note|make a note|note|remember)\s*[:,-]?\s*", "", command, flags=re.I).strip()
        if not note:
            return "What would you like me to note?"
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        with NOTES_FILE.open("a", encoding="utf-8") as file:
            file.write(f"[{datetime.now():%Y-%m-%d %H:%M}] {note}\n")
        return "Saved that in your notes."

    if low in ("show my notes", "read my notes", "open my notes"):
        if not NOTES_FILE.exists():
            return "You don't have any notes yet."
        notes = NOTES_FILE.read_text(encoding="utf-8").strip()
        return f"Here are your notes:\n{notes}" if notes else "You don't have any notes yet."

    if low.startswith(("search the web for ", "search for ", "google ")):
        query = re.sub(r"^(search the web for|search for|google)\s+", "", command, flags=re.I).strip()
        if query:
            webbrowser.open(f"https://www.google.com/search?q={quote_plus(query)}")
            return f"Searching the web for {query}."
        return "What should I search for?"

    app_aliases = {
        "notepad": "notepad.exe", "open notepad": "notepad.exe",
        "calculator": "calc.exe", "open calculator": "calc.exe",
        "file explorer": "explorer.exe", "open file explorer": "explorer.exe",
        "explorer": "explorer.exe",
    }
    if low in app_aliases:
        if os.name != "nt":
            return "Opening apps is currently supported on Windows only."
        try:
            os.startfile(app_aliases[low])  # type: ignore[attr-defined]
            return f"Opening {low.removeprefix('open ')}."
        except OSError:
            return "I couldn't open that app."

    if low in ("what time is it", "tell me the time", "what's the time"):
        return f"It's {datetime.now():%I:%M %p}."
    if low in ("what's the date", "what is the date", "what day is it"):
        return f"Today is {datetime.now():%A, %B %d, %Y}."
    return None


class AssistantWorker(QThread):
    finished_text = Signal(str)
    failed = Signal(str)

    def __init__(self, prompt: str):
        super().__init__()
        self.prompt = prompt

    def run(self) -> None:
        local = handle_local_command(self.prompt)
        if local is not None:
            self.finished_text.emit(local)
            return

        base_url = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1").rstrip("/")
        model = os.getenv("OPENAI_MODEL", "llama3.2")
        api_key = os.getenv("OPENAI_API_KEY", "ollama")
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are OpenJarves, a warm and concise Windows desktop voice assistant. Be helpful and clear."},
                        {"role": "user", "content": self.prompt},
                    ],
                    "temperature": 0.7,
                },
                timeout=60,
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"].strip()
            self.finished_text.emit(answer or "I couldn't think of a response just now.")
        except requests.exceptions.ConnectionError:
            self.finished_text.emit(
                "I can still take notes, search the web, and open supported apps. "
                "For AI chat, start Ollama or configure an OpenAI-compatible service; see the README."
            )
        except (requests.RequestException, KeyError, IndexError, ValueError) as error:
            self.failed.emit(f"The AI service couldn't respond: {error}")


class VoiceListener(QThread):
    command = Signal(str)
    status = Signal(str)

    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
        self._recognizer = None

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            with sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.6)
                self.status.emit("Listening for “Jarvis” or “OpenJarves”…")
                awaiting_command = False
                while not self._stop_event.is_set():
                    try:
                        audio = self._recognizer.listen(source, timeout=1, phrase_time_limit=7)
                        phrase = self._recognizer.recognize_google(audio).strip()
                    except sr.WaitTimeoutError:
                        continue
                    except sr.UnknownValueError:
                        continue
                    except sr.RequestError as error:
                        self.status.emit(f"Speech recognition unavailable: {error}")
                        self.msleep(1500)
                        continue
                    low = phrase.lower()
                    if awaiting_command:
                        awaiting_command = False
                        self.command.emit(phrase)
                        self.status.emit("Listening for wake word…")
                        continue
                    found = next((word for word in WAKE_WORDS if word in low), None)
                    if found:
                        remainder = re.sub(re.escape(found), "", phrase, count=1, flags=re.I).strip(" ,.!?")
                        if remainder:
                            self.command.emit(remainder)
                        else:
                            awaiting_command = True
                            self.status.emit("I'm listening — what's up?")
        except Exception as error:
            self.status.emit(f"Microphone unavailable: {error}")
        finally:
            self.status.emit("Voice listening is off.")


class SpeechWorker(QThread):
    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def run(self) -> None:
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty("rate", 175)
            engine.say(self.text[:1200])
            engine.runAndWait()
            engine.stop()
        except Exception:
            pass


class MessageBubble(QFrame):
    def __init__(self, text: str, user: bool = False):
        super().__init__()
        self.setObjectName("userBubble" if user else "assistantBubble")
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 11, 16, 11)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setMaximumWidth(590)
        layout.addWidget(label)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenJarves")
        self.resize(1060, 720)
        self.setMinimumSize(780, 560)
        self.voice: VoiceListener | None = None
        self.workers: list[QThread] = []
        self._build_ui()
        self._add_message("Hey, I'm OpenJarves. Ask me anything, or try ‘open Notepad’, ‘search for…’, or ‘take a note…’.")

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(32, 24, 32, 24)
        outer.setSpacing(18)

        header = QHBoxLayout()
        brand = QHBoxLayout()
        orb = QLabel("✦")
        orb.setObjectName("logoOrb")
        orb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(orb)
        title_stack = QVBoxLayout()
        title = QLabel("OPENJARVES")
        title.setObjectName("brandTitle")
        subtitle = QLabel("YOUR DESKTOP, IN GOOD HANDS")
        subtitle.setObjectName("brandSub")
        title_stack.addWidget(title)
        title_stack.addWidget(subtitle)
        brand.addLayout(title_stack)
        header.addLayout(brand)
        header.addStretch()
        self.voice_button = QPushButton("◉   Start listening")
        self.voice_button.setObjectName("voiceButton")
        self.voice_button.clicked.connect(self.toggle_voice)
        header.addWidget(self.voice_button)
        outer.addLayout(header)

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        self.status_label = QLabel("READY WHEN YOU ARE")
        self.status_label.setObjectName("statusLabel")
        hero_title = QLabel("What can I help you with?")
        hero_title.setObjectName("heroTitle")
        hero_hint = QLabel("Type a message, or turn on voice and say “Jarvis”.")
        hero_hint.setObjectName("muted")
        hero_layout.addWidget(self.status_label)
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_hint)
        outer.addWidget(hero)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("chatScroll")
        self.chat_content = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_content)
        self.chat_layout.setContentsMargins(4, 8, 4, 8)
        self.chat_layout.setSpacing(12)
        self.chat_layout.addStretch()
        self.scroll.setWidget(self.chat_content)
        outer.addWidget(self.scroll, 1)

        quick = QHBoxLayout()
        quick.setSpacing(10)
        for label, prompt in (("Open Notepad", "open notepad"), ("Search the web", "search the web for "), ("Take a note", "take a note: ")):
            button = QPushButton(label)
            button.setObjectName("chip")
            button.clicked.connect(lambda checked=False, value=prompt: self._quick_action(value))
            quick.addWidget(button)
        quick.addStretch()
        outer.addLayout(quick)

        composer = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setObjectName("composer")
        self.input.setPlaceholderText("Message OpenJarves…")
        self.input.returnPressed.connect(self.send_message)
        composer.addWidget(self.input, 1)
        send = QPushButton("Send  ➤")
        send.setObjectName("sendButton")
        send.clicked.connect(self.send_message)
        composer.addWidget(send)
        outer.addLayout(composer)

        self.setStyleSheet("""
            QWidget#root { background:#0b0e14; color:#e7edf7; font-family:'Segoe UI'; }
            QLabel { color:#e7edf7; }
            QLabel#logoOrb { background:#143438; border:1px solid #35e0c1; color:#48f0ce; border-radius:24px; font-size:24px; min-width:48px; max-width:48px; min-height:48px; max-height:48px; }
            QLabel#brandTitle { font-size:16px; font-weight:700; letter-spacing:2px; }
            QLabel#brandSub, QLabel#muted { color:#8591a5; font-size:11px; letter-spacing:1px; }
            QLabel#statusLabel { color:#49e4c4; font-size:10px; font-weight:700; letter-spacing:2px; }
            QFrame#hero { background:#111923; border:1px solid #1e3038; border-radius:16px; }
            QLabel#heroTitle { font-size:23px; font-weight:600; padding:3px 0; }
            QScrollArea#chatScroll { background:transparent; border:0; }
            QFrame#assistantBubble { background:#141c27; border:1px solid #202b39; border-radius:14px; }
            QFrame#userBubble { background:#123a38; border:1px solid #1b625b; border-radius:14px; }
            QPushButton { color:#e7edf7; border:1px solid #263342; border-radius:10px; padding:10px 15px; background:#141b25; }
            QPushButton:hover { border-color:#38cdb2; background:#17252b; }
            QPushButton#voiceButton { color:#54e8ca; border-color:#235b55; padding:11px 16px; }
            QPushButton#sendButton { background:#18a990; border:0; color:#061310; font-weight:700; padding:0 20px; }
            QPushButton#chip { color:#aab8ca; padding:8px 12px; font-size:12px; }
            QLineEdit#composer { background:#111923; border:1px solid #263342; border-radius:12px; padding:14px 16px; color:#f0f4fa; font-size:14px; }
            QLineEdit#composer:focus { border-color:#35cbb0; }
        """)

    def _add_message(self, text: str, user: bool = False) -> None:
        bubble = MessageBubble(text, user)
        row = QHBoxLayout()
        row.addWidget(bubble)
        row.addStretch() if user else row.insertStretch(0)
        self.chat_layout.insertLayout(self.chat_layout.count() - 1, row)
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def _quick_action(self, prompt: str) -> None:
        self.input.setText(prompt)
        self.input.setFocus()

    @Slot()
    def send_message(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._add_message(text, user=True)
        self.status_label.setText("THINKING…")
        worker = AssistantWorker(text)
        worker.finished_text.connect(self._receive_answer)
        worker.failed.connect(self._receive_error)
        worker.finished.connect(lambda w=worker: self._cleanup_worker(w))
        self.workers.append(worker)
        worker.start()

    @Slot(str)
    def _receive_answer(self, answer: str) -> None:
        self._add_message(answer)
        self.status_label.setText("READY WHEN YOU ARE")
        if self.voice and self.voice.isRunning():
            speech = SpeechWorker(answer)
            speech.finished.connect(lambda w=speech: self._cleanup_worker(w))
            self.workers.append(speech)
            speech.start()

    @Slot(str)
    def _receive_error(self, error: str) -> None:
        self._add_message(error)
        self.status_label.setText("READY WHEN YOU ARE")

    def _cleanup_worker(self, worker: QThread) -> None:
        if worker in self.workers:
            self.workers.remove(worker)
        worker.deleteLater()

    @Slot()
    def toggle_voice(self) -> None:
        if self.voice and self.voice.isRunning():
            self.voice.stop()
            self.voice.wait(2000)
            self.voice = None
            self.voice_button.setText("◉   Start listening")
            self.status_label.setText("VOICE LISTENING OFF")
            return
        self.voice = VoiceListener()
        self.voice.command.connect(self._voice_command)
        self.voice.status.connect(self._voice_status)
        self.voice.start()
        self.voice_button.setText("■   Stop listening")
        self.status_label.setText("STARTING MICROPHONE…")

    @Slot(str)
    def _voice_command(self, command: str) -> None:
        self.input.setText(command)
        self.send_message()

    @Slot(str)
    def _voice_status(self, status: str) -> None:
        self.status_label.setText(status.upper())
        if status == "Voice listening is off." and self.voice and not self.voice.isRunning():
            self.voice_button.setText("◉   Start listening")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        if self.voice and self.voice.isRunning():
            self.voice.stop()
            self.voice.wait(2000)
        for worker in self.workers:
            if worker.isRunning():
                worker.wait(1500)
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Segoe UI", 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
