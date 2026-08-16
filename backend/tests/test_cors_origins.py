"""Which origins the API will answer once the frontend is hosted elsewhere.

Worth pinning because a CORS mistake fails in the least helpful way possible:
the server logs a normal 200, and only the browser — on someone else's
machine, in a console nobody is watching — refuses to hand the response to the
page. Every screen just shows "failed to fetch".
"""

from app.core.s02_config import ALLOWED_ORIGINS, LOCAL_ORIGINS, parse_origins


def test_no_configured_origins_means_none_added():
    """Unset and empty are the same thing: run with the dev origins only."""
    assert parse_origins(None) == []
    assert parse_origins("") == []
    assert parse_origins("   ") == []


def test_a_single_origin_is_read():
    assert parse_origins("https://tracker.vercel.app") == ["https://tracker.vercel.app"]


def test_several_origins_split_on_commas_and_ignore_spacing():
    raw = "https://a.vercel.app, https://b.vercel.app ,https://c.vercel.app"
    assert parse_origins(raw) == [
        "https://a.vercel.app",
        "https://b.vercel.app",
        "https://c.vercel.app",
    ]


def test_a_trailing_slash_is_stripped():
    """Copied from a browser address bar, an origin arrives with a slash.

    The Origin header never has one, so keeping it would match nothing.
    """
    assert parse_origins("https://tracker.vercel.app/") == ["https://tracker.vercel.app"]


def test_duplicates_collapse():
    raw = "https://tracker.vercel.app,https://tracker.vercel.app/"
    assert parse_origins(raw) == ["https://tracker.vercel.app"]


def test_empty_entries_between_commas_are_dropped():
    """A trailing comma is the usual way this variable gets edited wrong."""
    assert parse_origins("https://tracker.vercel.app,,") == ["https://tracker.vercel.app"]


def test_both_spellings_of_the_dev_server_are_always_allowed():
    """A browser treats these as different origins even on the same machine."""
    assert "http://localhost:5173" in LOCAL_ORIGINS
    assert "http://127.0.0.1:5173" in LOCAL_ORIGINS


def test_the_deployed_app_keeps_the_dev_origins():
    """A hosted backend stays reachable from a laptop while debugging."""
    for origin in LOCAL_ORIGINS:
        assert origin in ALLOWED_ORIGINS
