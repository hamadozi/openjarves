# OpenJarves

A futuristic Windows desktop voice assistant with a chat app, wake-word listening, app launching, web search, notes, and an optional AI chat backend.

## Run on Windows

1. Install Python 3.10 or newer.
2. In this folder, run `setup.bat` (or install with `python -m pip install -r requirements.txt`).
3. Run `python app.py`.
4. Click **Start listening** and say **“Jarvis”** or **“OpenJarves”**, followed by a request. You can also type requests at any time.

Try: `open Notepad`, `open Calculator`, `open File Explorer`, `search the web for easy pasta recipes`, `take a note: call Sam`, or `show my notes`.

## AI chat: local or API

OpenJarves uses an OpenAI-compatible chat-completions endpoint. It defaults to local Ollama at `http://localhost:11434/v1` with model `llama3.2` (no API key needed for Ollama). Install Ollama, download a model, and leave the app defaults to chat locally.

To use another OpenAI-compatible provider, set these environment variables before launching the app:

```powershell
$env:OPENAI_BASE_URL = "https://your-provider.example/v1"
$env:OPENAI_MODEL = "your-model-name"
$env:OPENAI_API_KEY = "your-api-key"
python app.py
```

You can put the values in a local `.env` file (never commit API keys):

```dotenv
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=llama3.2
OPENAI_API_KEY=ollama
```

Basic local commands (notes, supported app launching, and web search) work without an AI service.

## Voice and privacy

Wake-word recognition currently uses Windows microphone input and Google Speech Recognition through the `SpeechRecognition` library, so recognized audio is sent to Google's recognition service. Voice listening is off until you explicitly click **Start listening**; click **Stop listening** to disable it. Text-to-speech uses the Windows speech engine through `pyttsx3`. Typed chat is sent only to the AI endpoint configured above. Notes are stored locally at `%APPDATA%\OpenJarves\notes.txt`.

## Supported local actions

- Open Notepad, Calculator, or File Explorer (allow-listed; arbitrary shell commands are not executed).
- Search the web using the default browser.
- Save and read simple timestamped notes.
- Tell the time and date.

## Package as a Windows executable

```powershell
python -m pip install pyinstaller
pyinstaller --noconsole --onefile --name OpenJarves app.py
```

The executable is written to `dist\OpenJarves.exe`.
