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


def test_mode_is_stored_per_session():
    switch.turn_on("s1", "summary")
    switch.turn_on("s2")
    assert switch.mode("s1") == "summary"
    assert switch.mode("s2") is None  # plain /talk: follow the default


def test_refreshing_the_marker_keeps_the_mode():
    switch.turn_on("s1", "full")
    switch.turn_on("s1")
    assert switch.mode("s1") == "full"
    assert switch.is_on("s1") is True


def test_turning_off_forgets_the_mode():
    switch.turn_on("s1", "full")
    switch.turn_off("s1")
    switch.turn_on("s1")
    assert switch.mode("s1") is None


def test_marker_from_before_modes_existed_follows_the_default():
    (paths.sessions_dir() / "s1").touch()  # empty marker, as written by the previous version
    assert switch.is_on("s1") is True
    assert switch.mode("s1") is None


def test_unknown_word_in_a_marker_means_default():
    (paths.sessions_dir() / "s1").write_text("loud", encoding="utf-8")
    assert switch.mode("s1") is None


def test_mode_of_missing_or_bad_sessions_is_none():
    assert switch.mode("nobody") is None
    assert switch.mode("") is None
