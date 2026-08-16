"""Upload size limiting (Phase 4 security review).

The point of these is the *how*, not just the what: a limit checked after
reading the whole file into memory does not defend against the thing it exists
to defend against.
"""

import io

import pytest
from fastapi import HTTPException

from app.routers.s17_uploads import MAX_UPLOAD_BYTES, read_within_limit


class CountingFile:
    """A file that records how much of it was actually read.

    Standing in for a huge upload without allocating one: it reports an
    enormous size but only ever hands back the chunk requested.
    """

    def __init__(self, size):
        self.size = size
        self.read_total = 0

    def read(self, amount=-1):
        remaining = self.size - self.read_total
        if remaining <= 0:
            return b""
        take = remaining if amount is None or amount < 0 else min(amount, remaining)
        self.read_total += take
        return b"x" * take


def test_a_normal_file_is_read_whole():
    body = read_within_limit(io.BytesIO(b"date,amount\n2026-01-01,10\n"))
    assert body == b"date,amount\n2026-01-01,10\n"


def test_an_empty_file_reads_as_empty_rather_than_failing():
    """The handler has its own message for an empty file; this must reach it."""
    assert read_within_limit(io.BytesIO(b"")) == b""


def test_a_file_at_exactly_the_limit_is_accepted():
    assert len(read_within_limit(CountingFile(MAX_UPLOAD_BYTES))) == MAX_UPLOAD_BYTES


def test_a_file_over_the_limit_is_refused_with_413():
    with pytest.raises(HTTPException) as raised:
        read_within_limit(CountingFile(MAX_UPLOAD_BYTES + 1))

    assert raised.value.status_code == 413
    assert "MB" in raised.value.detail


def test_an_oversized_file_is_never_read_to_the_end():
    """This is the whole point. Reading two gigabytes and *then* measuring
    performs the exhaustion the limit is meant to prevent."""
    huge = CountingFile(2 * 1024 * 1024 * 1024)  # 2 GB, never allocated

    with pytest.raises(HTTPException):
        read_within_limit(huge)

    # Stopped within one chunk of the ceiling, not at the file's size.
    assert huge.read_total <= MAX_UPLOAD_BYTES + 1024 * 1024
    assert huge.read_total < huge.size


def test_the_limit_is_a_parameter_so_the_check_itself_is_testable():
    with pytest.raises(HTTPException):
        read_within_limit(io.BytesIO(b"abcdef"), limit=3)
