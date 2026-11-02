from __future__ import annotations

import logging

from common.progress import Progress

logger = logging.getLogger("test_progress")


def lines(caplog) -> list[str]:
    return [record.getMessage() for record in caplog.records]


def test_a_line_every_so_many_items_and_one_at_the_last(caplog) -> None:
    clock = iter([0.0, 10.0, 20.0, 25.0])
    progress = Progress(
        logger, "EXTRACT", 5, every=2, monotonic=lambda: next(clock)
    )
    with caplog.at_level(logging.INFO):
        for done in range(1, 6):
            progress.step(done)
    assert lines(caplog) == [
        "EXTRACT 2/5 (40%) elapsed=00:00:10 eta=00:00:15",
        "EXTRACT 4/5 (80%) elapsed=00:00:20 eta=00:00:05",
        "EXTRACT 5/5 (100%) elapsed=00:00:25 eta=00:00:00",
    ]


def test_nothing_is_logged_between_the_steps(caplog) -> None:
    progress = Progress(logger, "READ", 100, every=50)
    with caplog.at_level(logging.INFO):
        for done in range(1, 50):
            progress.step(done)
    assert lines(caplog) == []
