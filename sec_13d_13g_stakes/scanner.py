"""Core: EDGAR daily index -> Schedule 13D/13G primary_doc.xml -> one record per filing.

Standard library only. SEC EDGAR requires a User-Agent that identifies you (name + email)
and allows 10 requests/second; this client paces itself at ~7.5/s.
Since 2024-12-18 13D/13G are filed as XML, so the cover page and items are fields, not prose.
Legacy HTML "SC 13D/SC 13G" rows are counted and skipped, never guessed at.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

EDGAR_BASE = "https://www.sec.gov"
DAILY_INDEX_FMT = EDGAR_BASE + "/Archives/edgar/daily-index/{year}/QTR{q}/form.{ymd}.idx"
TICKERS_URL = EDGAR_BASE + "/files/company_tickers.json"
RATE_LIMIT_S = 0.13
FORMS = {"SCHEDULE 13D": ("13D", False), "SCHEDULE 13D/A": ("13D", True),
         "SCHEDULE 13G": ("13G", False), "SCHEDULE 13G/A": ("13G", True)}
LEGACY_FORMS = {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}
PERSON_TYPES = {"BD": "broker-dealer", "BK": "bank", "IC": "insurance company", "IV": "investment company",
                "IA": "investment adviser", "EP": "employee benefit plan", "HC": "parent holding company",
                "SA": "savings association", "CP": "church plan", "CO": "corporation", "PN": "partnership",
                "IN": "individual", "OO": "other", "FI": "non-US institution"}
PURPOSE_FLAGS = {
    "board": r"\bboard\b|\bdirectors?\b", "proxy": r"\bproxy\b|\bsolicit", "nominate": r"\bnominat",
    "merger": r"\bmerger\b|\bacqui(re|sition)\b|\btender offer\b",
    "strategic-alternatives": r"strategic alternatives|\bsale of the (company|issuer)\b|\bgo(ing)?[- ]private\b",
    "management-change": r"\bmanagement\b.{0,60}\b(change|replace|remov)",
    "capital-return": r"\bbuyback\b|\brepurchase\b|\bdividend\b|\bcapital allocation\b",
    "engage": r"\bengage\b|\bdiscussions?\b|\bcommunicat", "financing": r"\bfinanc|\bloan\b|\bcredit\b"}
_INDEX_LINE_RE = re.compile(r"^(.+?)\s{2,}(.+?)\s+(\d+)\s+(\d{8})\s+(\S+)$")


class SecThrottled(RuntimeError):
    """EDGAR kept answering 403/429 after the allowed pauses."""


class Client:
    def __init__(self, user_agent: str, pause_s: float = 600, pauses_max: int = 2):
        if not user_agent or "@" not in user_agent:
            raise ValueError('EDGAR needs a User-Agent with a contact, e.g. "Your Name you@example.com"')
        self.ua, self.pause_s, self.pauses_max, self._last = user_agent, pause_s, pauses_max, 0.0

    def get(self, url: str) -> bytes:
        pauses = 0
        while True:
            wait = RATE_LIMIT_S - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept-Encoding": "identity"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    self._last = time.monotonic()
                    return r.read()
            except urllib.error.HTTPError as e:
                self._last = time.monotonic()
                if e.code in (403, 429) and "daily-index" not in url:
                    if pauses >= self.pauses_max:
                        raise SecThrottled(url)
                    pauses += 1
                    time.sleep(self.pause_s)
                    continue
                raise


def quarter_for(d: dt.date) -> int:
    return (d.month - 1) // 3 + 1


def parse_index(text: str, include_amendments: bool = True, schedules=None):
    """(rows, legacy_count). The form column holds a space ("SCHEDULE 13D/A"), so split on 2+ spaces."""
    out, legacy, in_data = [], 0, False
    for raw in text.splitlines():
        if raw.startswith("---"):
            in_data = True
            continue
        if not in_data or not raw.strip():
            continue
        m = _INDEX_LINE_RE.match(raw.rstrip())
        if not m:
            continue
        form, name, cik, ymd, fname = m.groups()
        form = form.strip()
        if form in LEGACY_FORMS:
            legacy += 1
            continue
        if form not in FORMS:
            continue
        sched, amend = FORMS[form]
        if (amend and not include_amendments) or (schedules and sched not in schedules):
            continue
        acc = re.search(r"(\d{10}-\d{2}-\d{6})\.txt$", fname)
        if not acc:
            continue
        out.append({"form": form, "schedule": sched, "isAmendment": amend, "filer_cik": cik.zfill(10),
                    "filer_name": name.strip(), "accession": acc.group(1),
                    "filed_date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}",
                    "xml_url": f"{EDGAR_BASE}/Archives/edgar/data/{int(cik)}/{acc.group(1).replace('-', '')}/primary_doc.xml"})
    return out, legacy


def fetch_daily(client: Client, d: dt.date, include_amendments=True, schedules=None):
    url = DAILY_INDEX_FMT.format(year=d.year, q=quarter_for(d), ymd=d.strftime("%Y%m%d"))
    try:
        text = client.get(url).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):      # weekend / holiday: EDGAR publishes no index
            return [], 0
        raise
    return parse_index(text, include_amendments, schedules)


def collect_window(client: Client, end: dt.date, lookback_days: int, include_amendments=True, schedules=None):
    out, legacy, seen = [], 0, set()
    for i in range(lookback_days):
        rows, n = fetch_daily(client, end - dt.timedelta(days=i), include_amendments, schedules)
        for r in rows:       # EDGAR lists a filing once per party (filer and subject company): keep one
            if r["accession"] not in seen:
                seen.add(r["accession"])
                out.append(r)
        legacy += n
    return out, legacy


# ---------- XML ----------
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_all(el, *names):
    return [e for e in el.iter() if _local(e.tag) in names]


def _t(el, tag: str):
    r = _find_all(el, tag)
    if not r:
        return None
    s = " ".join(" ".join(r[0].itertext()).split())
    return s or None


def _num(s):
    if s is None:
        return None
    try:
        return float(s.replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _date(s):
    if not s:
        return None
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(1)}-{m.group(2)}"
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    return m.group(0) if m else None


def purpose_flags(text):
    if not text:
        return []
    low = text.lower()
    return [k for k, rx in PURPOSE_FLAGS.items() if re.search(rx, low)]


def parse_xml(data: bytes) -> dict:
    """Cover page + items of a Schedule 13D/13G primary_doc.xml -> one dict (reporting persons as a list)."""
    root = ET.fromstring(data)
    sub = (_t(root, "submissionType") or "").upper()
    sched = "13D" if "13D" in sub else "13G" if "13G" in sub else None
    persons = []
    for p in _find_all(root, "reportingPersonInfo", "coverPageHeaderReportingPersonDetails"):
        code = (_t(p, "typeOfReportingPerson") or "").strip().upper() or None
        persons.append({
            "name": _t(p, "reportingPersonName"), "cik": _t(p, "reportingPersonCIK"), "typeCode": code,
            "type": PERSON_TYPES.get(code, code),
            "percentOfClass": _num(_t(p, "percentOfClass") or _t(p, "classPercent")),
            "aggregateShares": _num(_t(p, "aggregateAmountOwned")
                                    or _t(p, "reportingPersonBeneficiallyOwnedAggregateNumberOfShares")
                                    or _t(p, "amountBeneficiallyOwned")),
            "soleVoting": _num(_t(p, "soleVotingPower")), "sharedVoting": _num(_t(p, "sharedVotingPower")),
            "soleDispositive": _num(_t(p, "soleDispositivePower")),
            "sharedDispositive": _num(_t(p, "sharedDispositivePower")),
            "citizenship": _t(p, "citizenshipOrOrganization")})
    item4 = _find_all(root, "item4")
    purpose = _t(item4[0], "transactionPurpose") if item4 else None
    item3 = _find_all(root, "item3")
    funds = _t(item3[0], "fundsSource") if item3 else None
    pct = [p["percentOfClass"] for p in persons if p["percentOfClass"] is not None]
    sh = [p["aggregateShares"] for p in persons if p["aggregateShares"] is not None]
    icik = _t(root, "issuerCIK") or _t(root, "issuerCik") or ""
    return {"schedule": sched, "submissionType": sub or None, "issuerName": _t(root, "issuerName"),
            "issuerCik": icik.zfill(10) if icik else None, "cusip": _t(root, "issuerCusipNumber"),
            "securityClass": _t(root, "securitiesClassTitle"),
            "eventDate": _date(_t(root, "dateOfEvent") or _t(root, "eventDateRequiresFilingThisStatement")),
            "reportingPersons": persons, "personCount": len(persons),
            "maxPercentOfClass": max(pct) if pct else None, "maxAggregateShares": max(sh) if sh else None,
            "purposeOfTransaction": purpose[:2000] if purpose else None, "purposeFlags": purpose_flags(purpose),
            "sourceOfFunds": funds[:600] if funds else None}


def load_tickers(client: Client) -> dict:
    d = json.loads(client.get(TICKERS_URL))
    out: dict = {}
    for row in d.values():
        out.setdefault(str(row["cik_str"]).zfill(10), []).append(row["ticker"])
    return out


def parse_filing(client: Client, f: dict, tickers: dict) -> dict:
    x = parse_xml(client.get(f["xml_url"]))
    sched = x["schedule"] or f["schedule"]
    folder = f["xml_url"].rsplit("/", 1)[0] + "/"
    rec = {"form": f["form"], "schedule": sched, "isAmendment": f["isAmendment"],
           "isActivist": sched == "13D" and not f["isAmendment"],   # a NEW 13D: crossed 5% with intent
           "accession": f["accession"], "filedDate": f["filed_date"], "filerName": f["filer_name"],
           **{k: v for k, v in x.items() if k not in ("schedule", "submissionType")},
           "tickers": tickers.get(x["issuerCik"] or "", []),
           "primaryDocUrl": f["xml_url"], "filingIndexUrl": f"{folder}{f['accession']}-index.htm"}
    rec["lagDays"] = ((dt.date.fromisoformat(f["filed_date"]) - dt.date.fromisoformat(x["eventDate"])).days
                      if x["eventDate"] else None)
    return rec
