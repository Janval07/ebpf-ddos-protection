#!/usr/bin/env python3
"""Bounded HTTP load tester — runs from outside the target's container,
against any host:port you pass as arguments."""

from __future__ import annotations

import argparse
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

REQUEST_TIMEOUT_SECONDS = 2
REPORT_INTERVAL_SECONDS = 3
MAX_DURATION_SECONDS = 300
MAX_CONCURRENCY = 500
MAX_REQUESTS_PER_SECOND = 500


def bounded_int(name: str, value: int, maximum: int) -> int:
    """Validate a bounded positive integer coming from the CLI."""
    if not 1 <= value <= maximum:
        raise SystemExit(f"--{name} must be between 1 and {maximum}; got {value}")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bounded HTTP load test against a host:port given on the command line."
    )
    parser.add_argument("host", help="Target host or IP, e.g. localhost or 127.0.0.1")
    parser.add_argument("port", type=int, help="Target port, e.g. 8090 or 8001")
    parser.add_argument("--path", default="/", help="Path to request (default: /)")
    parser.add_argument(
        "--duration", type=int, default=20, help="Seconds to run (max 300, default 20)"
    )
    parser.add_argument(
        "--concurrency", type=int, default=40, help="Parallel workers (max 500, default 40)"
    )
    parser.add_argument(
        "--rps",
        type=int,
        default=50,
        help="Max aggregate requests/second (max 500, default 50)",
    )
    args = parser.parse_args()

    bounded_int("duration", args.duration, MAX_DURATION_SECONDS)
    bounded_int("concurrency", args.concurrency, MAX_CONCURRENCY)
    bounded_int("rps", args.rps, MAX_REQUESTS_PER_SECOND)
    return args


def request_status(opener: urllib.request.OpenerDirector, url: str) -> str:
    """Perform one GET and return its HTTP status, or 000 on network failure."""
    request = urllib.request.Request(url, method="GET")
    try:
        with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return str(response.status)
    except urllib.error.HTTPError as error:
        return str(error.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return "000"


class RateLimiter:
    """Limit aggregate request starts across all workers."""

    def __init__(self, requests_per_second: int) -> None:
        self.interval = 1 / requests_per_second
        self.next_request_at = 0.0
        self.lock = threading.Lock()

    def wait_for_turn(self, stop_event: threading.Event) -> bool:
        with self.lock:
            now = time.monotonic()
            scheduled_at = max(now, self.next_request_at)
            self.next_request_at = scheduled_at + self.interval
        return not stop_event.wait(max(0.0, scheduled_at - now))


def worker(
    url: str,
    deadline: float,
    stop_event: threading.Event,
    rate_limiter: RateLimiter,
    counts: Counter[str],
    counts_lock: threading.Lock,
) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while not stop_event.is_set() and time.monotonic() < deadline:
        if not rate_limiter.wait_for_turn(stop_event):
            break
        if time.monotonic() >= deadline:
            break
        code = request_status(opener, url)
        with counts_lock:
            counts[code] += 1


def snapshot(counts: Counter[str], counts_lock: threading.Lock) -> Counter[str]:
    with counts_lock:
        return counts.copy()


def report(label: str, counts: Counter[str], final: bool = False) -> None:
    total = sum(counts.values())
    ok = counts["200"]
    failed = total - ok
    tag = "RESULT" if final else f"[{datetime.now():%H:%M:%S}] requests so far"
    print(f"  {tag}: total={total} ok(200)={ok} blocked/failed={failed}", flush=True)
    if final and total:
        print(f"  -> {failed * 100 // total}% of responses were non-200", flush=True)


def main() -> None:
    args = parse_args()
    url = f"http://{args.host}:{args.port}{args.path}"

    print(
        f"=== Bounded HTTP load test against {url} ===\n"
        f"    {args.concurrency} workers, up to {args.rps} requests/s, "
        f"{args.duration}s\n",
        flush=True,
    )

    counts: Counter[str] = Counter()
    counts_lock = threading.Lock()
    stop_event = threading.Event()
    rate_limiter = RateLimiter(args.rps)
    deadline = time.monotonic() + args.duration
    interrupted = False

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                worker, url, deadline, stop_event, rate_limiter, counts, counts_lock
            )
            for _ in range(args.concurrency)
        ]
        try:
            while time.monotonic() < deadline:
                time.sleep(min(REPORT_INTERVAL_SECONDS, deadline - time.monotonic()))
                report(url, snapshot(counts, counts_lock))
        except KeyboardInterrupt:
            interrupted = True
            stop_event.set()
            print("\nStopping workers after Ctrl-C...", flush=True)
        finally:
            stop_event.set()

        for future in futures:
            future.result()

    report(url, snapshot(counts, counts_lock), final=True)
    if interrupted:
        print("\n=== Test interrupted. ===")
    else:
        print("\n=== Test finished. ===")
    print("A non-200 result can be a Fail2ban ban, an HTTP error, or a connection timeout.")


if __name__ == "__main__":
    main()