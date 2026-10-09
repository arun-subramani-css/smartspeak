"""Tests for the HTTP middleware: rate limiter correctness and memory safety.

Covers the two bug classes fixed in this file:
  1. X-Forwarded-For spoofing — the bucket key must come from the socket peer
     unless TRUST_X_FORWARDED_FOR is explicitly enabled.
  2. Unbounded memory — stale entries are pruned and the IP map is capped.
"""
from collections import deque
from types import SimpleNamespace

import pytest

from app.config import settings
from app.middleware import RateLimiterMiddleware


def make_request(method="POST", path="/api/v1/upload", client_ip="203.0.113.10",
                 forwarded=None):
    headers = {}
    if forwarded is not None:
        headers["x-forwarded-for"] = forwarded
    return SimpleNamespace(
        method=method,
        url=SimpleNamespace(path=path),
        headers=headers,
        client=SimpleNamespace(host=client_ip),
    )


def make_middleware(monkeypatch, limit=2):
    monkeypatch.setattr(settings, "RATE_LIMIT_UPLOAD_PER_HOUR", limit)
    return RateLimiterMiddleware(app=None)


async def passthrough(request):
    return SimpleNamespace(status_code=200)


def drive(mw, request):
    """Run one dispatch cycle synchronously."""
    import asyncio
    return asyncio.run(mw.dispatch(request, passthrough))


def test_blocks_after_limit_with_retry_after(monkeypatch):
    mw = make_middleware(monkeypatch, limit=2)
    req = make_request()
    assert drive(mw, req).status_code == 200
    assert drive(mw, req).status_code == 200
    blocked = drive(mw, req)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_forwarded_for_ignored_by_default(monkeypatch):
    """With trust off (default), spoofing X-Forwarded-For must NOT mint a
    fresh bucket: the same socket peer stays limited."""
    mw = make_middleware(monkeypatch, limit=1)
    assert drive(mw, make_request()).status_code == 200
    # Same client, but a spoofed "new IP" header — still blocked.
    assert drive(mw, make_request(forwarded="198.51.100.77")).status_code == 429


def test_forwarded_for_honored_when_trusted(monkeypatch):
    monkeypatch.setattr(settings, "TRUST_X_FORWARDED_FOR", True)
    mw = make_middleware(monkeypatch, limit=1)
    assert drive(mw, make_request(forwarded="198.51.100.1")).status_code == 200
    # Different forwarded client -> independent bucket.
    assert drive(mw, make_request(forwarded="198.51.100.2")).status_code == 200
    # Same forwarded client -> limited.
    assert drive(mw, make_request(forwarded="198.51.100.1")).status_code == 429


def test_only_upload_post_is_limited(monkeypatch):
    mw = make_middleware(monkeypatch, limit=1)
    assert drive(mw, make_request()).status_code == 200
    # GET on the same path and POST elsewhere are never counted/blocked.
    assert drive(mw, make_request(method="GET")).status_code == 200
    assert drive(mw, make_request(path="/api/v1/sessions/x/fusion-report")).status_code == 200


def test_pairing_upload_post_is_limited(monkeypatch):
    """The phone-pairing upload reuses the same ingest pipeline, so it must
    share the per-IP upload budget — while status polls stay unlimited."""
    mw = make_middleware(monkeypatch, limit=1)
    pairing_upload = "/api/v1/pairing/sometoken/upload"
    assert drive(mw, make_request(path=pairing_upload)).status_code == 200
    assert drive(mw, make_request(path=pairing_upload)).status_code == 429

    # GET status polls and pairing create/cancel are cheap — never counted.
    assert drive(mw, make_request(method="GET", path="/api/v1/pairing/sometoken")).status_code == 200
    assert drive(mw, make_request(method="POST", path="/api/v1/pairing")).status_code == 200
    assert drive(mw, make_request(method="DELETE", path="/api/v1/pairing/sometoken")).status_code == 200


def test_prune_removes_stale_and_empty_entries(monkeypatch):
    mw = make_middleware(monkeypatch, limit=5)
    mw._hits["gone-empty"] = deque()                      # empty: prunable
    mw._hits["stale"] = deque([-10_000.0])                # newest hit expired
    mw._hits["fresh"] = deque([-10.0, -5.0])              # recent activity
    mw._last_prune = -10_000.0                            # last prune long ago
    mw._prune(now=10.0)
    assert "gone-empty" not in mw._hits
    assert "stale" not in mw._hits
    assert "fresh" in mw._hits


def test_prune_caps_tracked_ips(monkeypatch):
    mw = make_middleware(monkeypatch, limit=5)
    monkeypatch.setattr(RateLimiterMiddleware, "_MAX_TRACKED_IPS", 3)
    # Monotonic-clock-style timestamps near now=10: 10.0.0.0 is the most
    # recently active, 10.0.0.5 the least.
    for i in range(6):
        mw._hits[f"10.0.0.{i}"] = deque([10.0 - float(i)])
    mw._last_prune = -10_000.0
    mw._prune(now=10.0)
    assert len(mw._hits) <= 3
    # The most recently active IPs survive the eviction.
    assert "10.0.0.0" in mw._hits


def test_prune_is_throttled(monkeypatch):
    mw = make_middleware(monkeypatch, limit=5)
    mw._last_prune = 100.0
    mw._hits["gone-empty"] = deque()
    mw._prune(now=200.0)  # within _PRUNE_INTERVAL_SECONDS -> skipped
    assert "gone-empty" in mw._hits
