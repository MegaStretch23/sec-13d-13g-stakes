"""CLI: python -m sec_13d_13g_stakes --user-agent "Your Name you@example.com" """
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

from . import __version__
from .scanner import Client, SecThrottled, collect_window, load_tickers, parse_filing

PAID = "https://apify.com/johnveds15/sec-13d-13g-ownership-stakes"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m sec_13d_13g_stakes",
                                 description="Read SEC Schedule 13D/13G ownership stakes (free EDGAR data).")
    ap.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT"),
                    help='required by SEC EDGAR: "Your Name you@example.com" (or env SEC_USER_AGENT)')
    ap.add_argument("--lookback-days", type=int, default=3, help="days of daily indexes to read (default %(default)s)")
    ap.add_argument("--end-date", help="YYYY-MM-DD, default today (UTC)")
    ap.add_argument("--schedule", choices=["13D", "13G"], help="only this schedule (default both)")
    ap.add_argument("--no-amendments", action="store_true", help="skip /A amendments")
    ap.add_argument("--activist-only", action="store_true", help="only NEW 13D filings (crossed 5% with intent)")
    ap.add_argument("--min-percent", type=float, default=0.0, help="keep filings whose top reporting person holds at least this percent")
    ap.add_argument("--max-filings", type=int, default=0, help="stop after N filings (quick demo); 0 = all")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    ap.add_argument("--version", action="version", version=__version__)
    a = ap.parse_args(argv)
    if not a.user_agent:
        ap.error('--user-agent "Your Name you@example.com" is required by SEC EDGAR')
    end = dt.date.fromisoformat(a.end_date) if a.end_date else dt.datetime.now(dt.timezone.utc).date()
    client = Client(a.user_agent)
    schedules = {"13D"} if a.activist_only else ({a.schedule} if a.schedule else None)
    rows, legacy = collect_window(client, end, a.lookback_days, not (a.no_amendments or a.activist_only), schedules)
    if a.max_filings:
        rows = rows[:a.max_filings]
    try:
        tickers = load_tickers(client)
    except Exception as e:  # tickers are an enrichment only; say so, do not hide it
        print(f"WARNING: ticker map unavailable ({e}); records carry no tickers", file=sys.stderr)
        tickers = {}
    recs, failed = [], 0
    for f in rows:
        try:
            r = parse_filing(client, f, tickers)
        except SecThrottled:
            print("FAILED: EDGAR kept rate-limiting this IP; try later or from another network", file=sys.stderr)
            return 1
        except Exception as e:
            failed += 1
            print(f"skip {f['accession']}: {e}", file=sys.stderr)
            continue
        if a.min_percent and (r["maxPercentOfClass"] or 0) < a.min_percent:
            continue
        recs.append(r)
    out = {"version": __version__, "window": {"end": end.isoformat(), "lookback_days": a.lookback_days},
           "filings_listed": len(rows), "filings_failed": failed, "legacy_html_skipped": legacy,
           "stakes_found": len(recs), "stakes": recs, "hosted": PAID}
    text = json.dumps(out, indent=2)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {a.out}: {len(recs)} stakes from {len(rows)} filings ({failed} failed)")
    else:
        print(text)
    if rows and failed == len(rows):
        print("FAILED: every filing fetch failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
