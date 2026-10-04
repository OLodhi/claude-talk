from talk.log import get_logger


def test_writes_to_log_file_under_home(talk_home):
    get_logger().info("hello from the test")
    assert "hello from the test" in (talk_home / "logs" / "talk.log").read_text(encoding="utf-8")


def test_follows_a_change_of_home(tmp_path, monkeypatch):
    get_logger().info("first")
    other = tmp_path / "other"
    monkeypatch.setenv("CLAUDE_TALK_HOME", str(other))
    get_logger().info("second")
    assert "second" in (other / "logs" / "talk.log").read_text(encoding="utf-8")
    assert len(get_logger().handlers) == 1


def test_log_is_capped_at_one_megabyte_with_one_backup():
    handler = get_logger().handlers[0]
    assert handler.maxBytes == 1_000_000
    assert handler.backupCount == 1
