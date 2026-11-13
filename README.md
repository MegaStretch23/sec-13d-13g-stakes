# sec-13d-13g-stakes

Read **SEC Schedule 13D / 13G ownership stakes** from free EDGAR data: who crossed 5% of a public company, how much they hold, and (for a 13D) why.

- Python 3.9+, **standard library only** (no `pip install`), JSON output.
- Reads the EDGAR daily index, downloads each filing's structured `primary_doc.xml` (13D/13G have been filed as XML since 2024-12-18) and returns one record per filing with **every reporting person as its own row**: type, percent of class, shares, voting and dispositive power, citizenship.
- Adds issuer CUSIP, tickers (from the SEC's own `company_tickers.json`), the event date, filing lag in days, and for a 13D the Item 4 "purpose of transaction" text with simple keyword flags (board, proxy, merger, ...).
- `isActivist` is true for a **new** Schedule 13D (not an amendment, not a 13G): the filing that says a holder crossed 5% with intent.
- Not investment advice. Flags are keyword matches on the filer's own text, not a judgment of what they will do.

## Quickstart

```bash
git clone https://github.com/MegaStretch23/sec-13d-13g-stakes.git
cd sec-13d-13g-stakes

# EDGAR requires a User-Agent with a contact: "Your Name you@example.com"
python -m sec_13d_13g_stakes --user-agent "Your Name you@example.com" --lookback-days 3 --activist-only --out stakes.json
```

`--activist-only` reads only new 13D filings, which is the quick, interesting subset (16 over the 4 business days in the saved run). Other options: `--schedule 13D|13G`, `--no-amendments`, `--min-percent 10`, `--max-filings 25` (quick demo), `--end-date YYYY-MM-DD`. Env `SEC_USER_AGENT` works instead of `--user-agent`. Tests: `python -m unittest discover -s tests` (offline, hand-written fixtures).

Exit code 1 means EDGAR throttled you or every filing fetch failed; the tool never prints "0 stakes" when it could not read the data. Legacy HTML `SC 13D/SC 13G` rows are counted (`legacy_html_skipped`) and skipped.

Pacing is ~7.5 requests/s, under EDGAR's 10/s limit, one request per filing. A full day of 13D + 13G was about 200 filings in the saved run, so a 5-day lookback of everything takes several minutes.

## Real sample output

Saved run from 2026-11-13, lookback of 5 days ending 2026-11-12, all schedules and amendments: **807 unique filings fetched and parsed, 0 failed** (352 new 13G, 354 13G amendments, 16 new 13D, 85 13D amendments). Full file of the 16 new 13D records: [`examples/sample-run-2026-11-13.json`](examples/sample-run-2026-11-13.json).

The first version of this run parsed every filing twice (1,614 rows): EDGAR's daily index lists a filing once under the filer and once under the subject company. The saved file is deduplicated by accession number and the code now does the same (there is a test).

The largest new 13D stakes in that run:

| filed | issuer | ticker | first reporting person | % of class | purpose flags |
|---|---|---|---|---|---|
| 2026-11-09 | Energys Group Ltd | ENGS | LAU Michael Kwok Yan | 98.9% | - |
| 2026-11-09 | Gamehaus Holdings Inc. | GMHS | Xie Feng | 31.5% | - |
| 2026-11-10 | Powell Max Ltd | PMAX | Hyperscale Data, Inc. | 21.7% | board, engage, financing |
| 2026-11-12 | Mentari Therapeutics, Inc. | MTRI | Fairmount Funds Management LLC | 19.99% | board, merger, financing |
| 2026-11-09 | HIGHWAY HOLDINGS LTD | HIHO | Lazar David E. | 16.7% | board, nominate, capital-return, engage, financing |
| 2026-11-12 | Pyxus International, Inc. | PYYX | Owl Creek Asset Management, L.P. | 15.7% | board, engage, financing |

Each record in the file links its `primaryDocUrl` and `filingIndexUrl` on sec.gov so you can check any row against the filing.

## Limits (read these)

- Flags are regexes over the filer's Item 4 text; "financing" can match boilerplate. Read the text before you act.
- A filing with several reporting persons shows the highest percent as `maxPercentOfClass`; persons are not de-grouped from joint filers.
- A field the XML does not carry, or carries unparseably, is `null`, never a guess.
- Data is whatever EDGAR published; nothing is checked against the company's other disclosures.

## Don't want to run it yourself?

The same idea runs hosted on Apify as a pay-per-event Actor: **[SEC 13D/13G Ownership Stakes](https://apify.com/johnveds15/sec-13d-13g-ownership-stakes)**. Prices read from the Apify API on 2026-11-13: $0.001 per Schedule 13D/13G filing parsed, $0.001 per stake record delivered, and $0.02 per new 13D (activist stake) delivered. Check the Actor page for the current prices.

## License

MIT. SEC EDGAR data is public.
