# Changelog

## 1.0.0 - 2026-11-24

Initial release.

* Driver qualification file audit over a CSV export:
  missing DQ file items (CDL number, medical
  certificate, MVR, annual review, road test
  certificate, previous-employer inquiry), expired CDL
  and medical certificates, CDL and medical
  certificates expiring soon, MVR older than 12 months,
  annual review overdue past the 365 day cycle,
  previous-employer inquiry past the 30 day window
  after hire, and drivers dispatched while any item is
  expired.
* Readiness count: drivers with no error findings are
  ready to drive, with a per-driver readiness table
  (driver id, name, error and warning counts, READY or
  NOT READY).
* Previous-employer inquiry window measured from the
  hire date under 49 CFR 391.23; an inquiry exactly 30
  days after hire passes, and an inquiry dated before
  hire also passes.
* Data quality checks: duplicate and missing driver
  ids, missing and invalid dates, future hire dates,
  and malformed rows.
* Defensive timestamp parsing (ISO 8601 with or without
  a timezone, plus common day/month/year forms); a bad
  row is reported as a finding and never crashes the
  run. UTF-8 BOM headers and extra columns handled.
* Findings carry a driver id, a rule name, a severity
  (error or warning), and a message; errors and warnings
  are counted in the summary.
* Text and --json output, --out file output,
  --expiry-days, --mvr-days, and --as-of thresholds,
  and a --check CI gate that exits 1 on errors (and on
  warnings with --strict).
* Zero dependencies, Python 3.9 or newer.
