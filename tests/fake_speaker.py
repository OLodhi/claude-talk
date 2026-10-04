"""Stand-in for talk.speaker in control tests.

Usage: python fake_speaker.py <job.json> <polite|stubborn>
polite: waits until control.should_stop(token), then clears itself and exits.
stubborn: ignores stop requests and sleeps for 30 s."""
import json
import sys
import time
from pathlib import Path

from talk import control

job_path = Path(sys.argv[1])
job = json.loads(job_path.read_text(encoding="utf-8"))
job_path.with_suffix(".ready").write_text("ready", encoding="utf-8")
if sys.argv[2] == "stubborn":
    time.sleep(30)
else:
    deadline = time.monotonic() + 30
    while not control.should_stop(job["token"]) and time.monotonic() < deadline:
        time.sleep(0.02)
    control.clear_speaker(job["token"])
