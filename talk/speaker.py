"""The speaker process: python -m talk.speaker <job.json>

Started detached by control.start_speaking. Speaks one reply, sentence by sentence, and stops
the moment Space/Esc is pressed, a stop is requested, or a newer reply takes over."""
import json
import queue
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from talk import control, paths
from talk.config import load_config
from talk.log import get_logger
from talk.speakable import speech_chunks

FIRST_AUDIO_TIMEOUT = 5.0
NEXT_AUDIO_TIMEOUT = 15.0
POLL_SECONDS = 0.05
_STOPPED = object()
SWEEP_AFTER_SECONDS = 3600


class Player(Protocol):
    def play(self) -> None: ...
    def is_playing(self) -> bool: ...
    def close(self) -> None: ...


class Process(Protocol):
    def poll(self) -> int | None: ...
    def kill(self) -> None: ...


@dataclass
class Deps:
    synthesize: Callable[[str, Path], None]
    open_player: Callable[[Path], Player]
    start_fallback: Callable[[str], Process] | None
    should_stop: Callable[[], bool]
    work_dir: Path


def speak(
    text: str, deps: Deps, first_timeout: float = FIRST_AUDIO_TIMEOUT, next_timeout: float = NEXT_AUDIO_TIMEOUT
) -> str:
    """Speak text. Returns "finished", "stopped", "fallback" (finished in the Windows voice) or "failed"."""
    chunks = speech_chunks(text)
    results: queue.Queue = queue.Queue()
    cancel = threading.Event()

    def produce() -> None:
        for index, chunk in enumerate(chunks):
            if cancel.is_set():
                return
            path = deps.work_dir / f"chunk{index}.mp3"
            try:
                deps.synthesize(chunk, path)
            except Exception as exc:
                results.put(exc)
                return
            results.put(path)

    threading.Thread(target=produce, daemon=True).start()
    try:
        for index in range(len(chunks)):
            item = _wait_for(results, first_timeout if index == 0 else next_timeout, deps.should_stop)
            if item is _STOPPED:
                return "stopped"
            if item is None or isinstance(item, Exception):
                get_logger().warning("online voice failed (%s); using fallback", item or "timed out")
                return _fallback(" ".join(chunks[index:]), deps)
            try:
                if _play(item, deps) == "stopped":
                    return "stopped"
            except Exception:
                get_logger().exception("playback failed; using fallback")
                return _fallback(" ".join(chunks[index:]), deps)
        return "finished"
    finally:
        cancel.set()


def _wait_for(results: queue.Queue, timeout: float, should_stop: Callable[[], bool]):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if should_stop():
            return _STOPPED
        try:
            return results.get(timeout=POLL_SECONDS)
        except queue.Empty:
            continue
    return None


def _play(path: Path, deps: Deps) -> str:
    player = deps.open_player(path)
    try:
        player.play()
        while player.is_playing():
            if deps.should_stop():
                return "stopped"
            time.sleep(POLL_SECONDS)
        return "done"
    finally:
        player.close()


def _fallback(text: str, deps: Deps) -> str:
    if deps.start_fallback is None:
        return "failed"
    proc = deps.start_fallback(text)
    while proc.poll() is None:
        if deps.should_stop():
            proc.kill()
            return "stopped"
        time.sleep(POLL_SECONDS)
    return "fallback"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    log = get_logger()
    token = ""
    try:
        job_path = Path(argv[0])
        job = json.loads(job_path.read_text(encoding="utf-8"))
        job_path.unlink(missing_ok=True)
        token = job["token"]
        _sweep_old_files()
        outcome = _speak_job(job["text"], token)
        log.info("speaker %s: %s", token[:8], outcome)
    except Exception:
        log.exception("speaker failed")
    finally:
        if token:
            control.clear_speaker(token)
    return 0


def _speak_job(text: str, token: str) -> str:
    from talk import playback, tts
    from talk.keys import KeyWatcher

    cfg = load_config()
    keys = KeyWatcher()
    keys.prime()

    def should_stop() -> bool:
        key_pressed = keys.pressed()  # poll every time so held/released keys are tracked
        return key_pressed or control.should_stop(token)

    with tempfile.TemporaryDirectory(prefix="speak-", dir=paths.state_dir(), ignore_cleanup_errors=True) as tmp:
        work_dir = Path(tmp)
        deps = Deps(
            synthesize=lambda chunk, out: tts.synthesize(chunk, cfg.voice, cfg.rate, out),
            open_player=playback.Mp3Player,
            start_fallback=(lambda rest: tts.start_windows_voice(rest, work_dir))
            if cfg.fallback_to_windows_voice else None,
            should_stop=should_stop,
            work_dir=work_dir,
        )
        return speak(text, deps)


def _sweep_old_files() -> None:
    """Remove temp folders and job files left behind by speakers that were killed."""
    cutoff = time.time() - SWEEP_AFTER_SECONDS
    leftovers = list(paths.state_dir().glob("speak-*")) + list(paths.jobs_dir().glob("*.json"))
    for path in leftovers:
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink()
        except OSError:
            continue


if __name__ == "__main__":
    sys.exit(main())
