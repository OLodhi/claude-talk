import os
import time

import pytest

from talk import paths, switch


def test_off_by_default():
    assert switch.is_on("s1") is False


def test_toggle_on_then_off():
    assert switch.toggle("s1") is True
    assert switch.is_on("s1") is True
    assert switch.toggle("s1") is False
    assert switch.is_on("s1") is False


def test_sessions_are_independent():
    switch.turn_on("s1")
    assert switch.is_on("s1") is True
    assert switch.is_on("s2") is False


def test_same_prompt_twice_toggles_once():
    assert switch.toggle("s1", "p1") is True
    assert switch.toggle("s1", "p1") is True
    assert switch.is_on("s1") is True
    assert switch.toggle("s1", "p2") is False


def test_empty_or_odd_session_ids():
    assert switch.is_on("") is False
    assert switch.is_on("!!!") is False
    switch.turn_off("")
    with pytest.raises(ValueError):
        switch.toggle("")


def test_session_ids_cannot_escape_the_folder():
    switch.turn_on("../../evil")
    assert (paths.sessions_dir() / "evil").exists()


def test_cleanup_removes_only_old_markers():
    switch.turn_on("old")
    switch.turn_on("fresh")
    eight_days_ago = time.time() - 8 * 86400
    os.utime(paths.sessions_dir() / "old", (eight_days_ago, eight_days_ago))
    assert switch.cleanup_stale() == 1
    assert switch.is_on("old") is False
    assert switch.is_on("fresh") is True
