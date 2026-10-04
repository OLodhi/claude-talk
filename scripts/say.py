"""Manual smoke test: speak text through the real pipeline (detached speaker, online voice, playback).

Usage: .venv\\Scripts\\python.exe scripts\\say.py "Hello there. This is Claude Talk."
Press Space or Esc while it talks to check that it stops."""
import sys

from talk import control
from talk.speakable import to_speech

text = " ".join(sys.argv[1:]) or "Hello. This is Claude Talk, reading a reply aloud. Press Space to stop me."
speech = to_speech(text)
print(f"Speaking: {speech}")
print(f"Speaker pid: {control.start_speaking(speech, 'manual-test')}")
