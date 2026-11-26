# driver-qualification-doctor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/aamirtechs/driver-qualification-doctor/blob/main/LICENSE) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/aamirtechs/driver-qualification-doctor/issues)

A zero-dependency Python CLI that audits a driver
qualification file CSV export for the problems that
quietly put a carrier out of compliance: a missing DQ
file item, an expired CDL or medical certificate, a
medical certificate expiring soon, an MVR older than
12 months, an overdue annual review, a missing road
test certificate, a previous-employer inquiry that is
missing or past the 30 day window after hire, and
drivers dispatched while any item is expired. It also
prints a per-driver readiness table, so a dispatcher
can see at a glance which drivers are ready to run and
which files need chasing.

Every motor carrier must keep a qualification file for
each driver it employs under 49 CFR 391.51, with the
annual MVR inquiry and review under 391.25, the
medical examiner's certificate under 391.43, and the
road test under 391.31, and missing file items (no DQ
file, missing MVR inquiry, missing medical certificate)
are listed as critical audit findings. DQ file
management lives in paid SaaS tools or paper folders,
but nobody audits the DQ spreadsheet itself first to
say which drivers are ready, which are one document
away, and which must not be dispatched. This tool is
that audit: it ranks the files in the export alone, and
never touches a live FMCSA or state lookup.

## Install

Requires Python 3.9 or newer. No dependencies beyond the
standard library.

```bash
pip install driver-qualification-doctor
```

Or run it straight from the source checkout:

```bash
python3 driver_qualification_doctor.py examples/drivers.csv
```

## Input format

A CSV export with a header row, from a carrier
spreadsheet, a TMS export, or a manual DQ file
checklist. Columns used: `driver_id` (or `id`,
`driver`), `driver_name` (or `name`), `cdl_number`
(or `cdl`), `cdl_expiry` (or `cdl_expiration`),
`medical_expiry` (or `medical_certificate_expiry`),
`mvr_date` (or `mvr`), `annual_review_date` (or
`review_date`), `road_test_date` (or `road_test`),
`prev_employer_inquiry_date` (or
`employer_inquiry_date`), `hire_date` (or
`hired_date`), and `dispatched` (or `is_dispatched`).
Extra columns are ignored, so a full DQ export works
as-is. A UTF-8 BOM header is handled. Only
`driver_id`, `cdl_expiry`, and `medical_expiry` are
required; the other columns are optional, and the
checks that need a missing column are skipped.

`driver_name` also accepts `full_name`, `cdl_number`
also accepts `cdl_no` or `license_number`,
`cdl_expiry` also accepts `cdl_expires` or
`cdl_expiry_date`, `medical_expiry` also accepts
`medical_expires`, `med_cert_expiry`, or
`medical_certificate_expiration`, `mvr_date` also
accepts `last_mvr_date` or `mvr_inquiry_date`,
`annual_review_date` also accepts `last_annual_review`
or `annual_review`, `road_test_date` also accepts
`last_road_test` or `road_test_certificate_date`,
`prev_employer_inquiry_date` also accepts
`previous_employer_inquiry_date` or
`prev_employer_inquiry`, `hire_date` also accepts
`employment_date` or `date_of_hire`, and `dispatched`
also accepts `currently_dispatched` or `on_dispatch`.

Dates accept ISO 8601 with or without a timezone
(`2026-11-17 10:00`, `2026-11-17T10:00:00Z`,
`2026-11-17`), plus day/month/year and month/day/year
forms. A date with no timezone is read as UTC. A
`dispatched` value of `yes`, `true`, `1`, or
`dispatched` counts as dispatched.

```csv
driver_id,driver_name,cdl_number,cdl_expiry,medical_expiry,mvr_date,annual_review_date,road_test_date,prev_employer_inquiry_date,hire_date,dispatched
D-101,Alice Hart,CDL-1001,2027-06-30,2027-01-15,2026-06-01,2026-05-01,2024-03-01,2026-02-01,2026-01-15,no
D-102,Bob Lane,CDL-1002,2026-10-01,2027-02-01,2026-07-01,2026-06-01,2024-05-01,2026-02-10,2026-02-01,yes
D-103,Carla Moss,CDL-1003,2027-03-01,2026-09-15,2026-08-01,2026-07-01,2024-06-01,2026-03-01,2026-02-15,yes
D-104,Dan Cole,CDL-1004,2027-04-01,2026-12-10,2026-09-01,2026-08-01,2024-07-01,2026-03-20,2026-03-01,no
D-105,Erin Fox,CDL-1005,2027-05-01,2027-03-01,2025-09-01,2026-09-01,2024-08-01,2026-05-01,2026-04-01,no
```

## What it checks

Errors, the ones that mean a driver must not be
dispatched or data that cannot be trusted:

* `cdl-expired`: a CDL that expired before `--as-of`
  (default now). The message names the expiry date and
  how many days ago it lapsed.
* `medical-expired`: a medical certificate that expired
  before `--as-of`. The message names the expiry date
  and how many days ago it lapsed.
* `missing-cdl-number`: a driver with no CDL number
  recorded, so the license cannot be checked.
* `missing-medical-certificate`: a driver with no
  medical certificate expiry recorded, so the DQ file
  has no medical certificate.
* `missing-mvr`: a driver with no MVR date recorded, so
  the annual MVR inquiry is missing from the DQ file.
* `missing-annual-review`: a driver with no annual
  review date recorded, so the annual review is missing
  from the DQ file.
* `missing-road-test`: a driver with no road test date
  recorded, so the road test certificate is missing
  from the DQ file.
* `missing-employer-inquiry`: a driver with no
  previous-employer inquiry date recorded, so the
  inquiry is missing from the DQ file.
* `stale-mvr`: an MVR older than `--mvr-days` (default
  365, the 12 month cycle under 49 CFR 391.25).
* `annual-review-overdue`: an annual review older than
  365 days, past the annual cycle under 49 CFR 391.25.
* `employer-inquiry-late`: a previous-employer inquiry
  completed more than 30 days after the hire date, past
  the window under 49 CFR 391.23.
* `dispatched-while-expired`: a driver flagged as
  dispatched while the CDL or the medical certificate
  is expired. The message names which item is expired.
* `duplicate-driver-id`: the same driver id twice in
  the export.
* `missing-driver-id`: a row with no driver id, so the
  driver cannot be matched to a DQ file.
* `invalid-date`: a CDL, medical, MVR, review, road
  test, inquiry, or hire date that matches no known
  format. The row is still audited on the fields that
  did parse.
* `future-timestamp`: a `hire_date` after `--as-of`
  (default now).
* `malformed-row`: a row with the wrong number of fields.
  The row is skipped and reported, never a crash.

Warnings, files worth a closer look:

* `cdl-expiring-soon`: a CDL expiring within
  `--expiry-days` (default 30).
* `medical-expiring-soon`: a medical certificate
  expiring within `--expiry-days` (default 30).

The summary reports the driver, finding, error, and
warning counts, how many drivers are ready to drive
(no error findings), the counts per problem (expired
CDL, expired medical, CDL and medical expiring soon,
stale MVR, overdue review, missing road test, missing
and late employer inquiry, dispatched while expired),
and a per-driver readiness table (driver id, name,
error and warning counts, READY or NOT READY).

## Usage

```bash
python3 driver_qualification_doctor.py examples/drivers.csv --as-of 2026-11-18
```

Captured output:

```
ERROR [missing-road-test] D-107: driver has no road test date recorded, so the road test certificate is missing from the DQ file
ERROR [missing-employer-inquiry] D-108: driver has no previous-employer inquiry date recorded, so the inquiry is missing from the DQ file
ERROR [missing-cdl-number] D-110: driver has no CDL number recorded, so the license cannot be checked
ERROR [missing-medical-certificate] D-111: driver has no medical certificate expiry recorded, so the DQ file has no medical certificate
ERROR [missing-mvr] D-112: driver has no MVR date recorded, so the annual MVR inquiry is missing from the DQ file
ERROR [missing-annual-review] D-113: driver has no annual review date recorded, so the annual review is missing from the DQ file
ERROR [invalid-date] D-115: medical certificate expiry date 'not-a-date' is not a readable date
ERROR [future-timestamp] D-116: hire date 2026-12-05 00:00 is after the as-of date 2026-11-18 00:00
ERROR [duplicate-driver-id] D-101: driver id appears more than once in the export
ERROR [malformed-row] row 19: row has 12 fields but the header has 11, so the row was skipped
ERROR [missing-driver-id] row 20: row has no driver id, so the driver cannot be matched to a DQ file
ERROR [cdl-expired] D-102: CDL expired on 2026-10-01, 48.0 days ago
ERROR [dispatched-while-expired] D-102: driver is dispatched while the CDL is expired
ERROR [medical-expired] D-103: medical certificate expired on 2026-09-15, 64.0 days ago
ERROR [dispatched-while-expired] D-103: driver is dispatched while the medical certificate is expired
WARNING [medical-expiring-soon] D-104: medical certificate expires on 2026-12-10, in 22.0 days
ERROR [stale-mvr] D-105: MVR is 443.0 days old, older than the 365 day limit
ERROR [annual-review-overdue] D-106: annual review is 413.0 days old, overdue past the 365 day annual cycle
ERROR [employer-inquiry-late] D-109: previous-employer inquiry was completed 64.0 days after hire, past the 30 day window
ERROR [cdl-expired] D-114: CDL expired on 2026-09-01, 78.0 days ago
ERROR [medical-expired] D-114: medical certificate expired on 2026-08-15, 95.0 days ago
ERROR [dispatched-while-expired] D-114: driver is dispatched while the CDL and medical certificate are expired
WARNING [medical-expiring-soon] D-118: medical certificate expires on 2026-11-18, in 0.0 days

Drivers: 22, findings: 23, errors: 21, warnings: 2
Ready to drive: 5 of 22 drivers
Expired CDL: 2, expired medical: 2, CDL expiring soon: 0, medical expiring soon: 2, stale MVR: 1, overdue review: 1, missing road test: 1, missing employer inquiry: 1, late employer inquiry: 1, dispatched while expired: 3

Per-driver readiness:
D-101 (Alice Hart): 1 errors, 0 warnings, NOT READY
D-102 (Bob Lane): 2 errors, 0 warnings, NOT READY
D-103 (Carla Moss): 2 errors, 0 warnings, NOT READY
D-104 (Dan Cole): 0 errors, 1 warnings, READY
D-105 (Erin Fox): 1 errors, 0 warnings, NOT READY
D-106 (Frank Hale): 1 errors, 0 warnings, NOT READY
D-107 (Grace Ives): 1 errors, 0 warnings, NOT READY
D-108 (Hank Joss): 1 errors, 0 warnings, NOT READY
D-109 (Ivy Kent): 1 errors, 0 warnings, NOT READY
D-110 (Jack Lowe): 1 errors, 0 warnings, NOT READY
D-111 (Kim Nash): 1 errors, 0 warnings, NOT READY
D-112 (Leo Park): 1 errors, 0 warnings, NOT READY
D-113 (Mia Reed): 1 errors, 0 warnings, NOT READY
D-114 (Nate Shaw): 3 errors, 0 warnings, NOT READY
D-115 (Olga Tate): 1 errors, 0 warnings, NOT READY
D-116 (Pete Voss): 1 errors, 0 warnings, NOT READY
D-101 (Quinn Wade): 1 errors, 0 warnings, NOT READY
row 20 (No Name Freight): 1 errors, 0 warnings, NOT READY
D-117 (Rosa Diaz): 0 errors, 0 warnings, READY
D-118 (Sam Webb): 0 errors, 1 warnings, READY
D-119 (Tara Xu): 0 errors, 0 warnings, READY
D-120 (Uma Yates): 0 errors, 0 warnings, READY
```

The sample has 23 rows; the malformed row 19 is skipped,
so 22 drivers are audited. The headline numbers are 5
of 22 drivers ready to drive, 2 expired CDLs, 2 expired
medical certificates, 2 medical certificates expiring
soon, 1 stale MVR (443.0 days old), 1 overdue annual
review (413.0 days old), 1 missing road test, 1 missing
employer inquiry, 1 late employer inquiry (64.0 days
after hire), and 3 drivers dispatched while expired.
Nate Shaw (D-114) is the worst file with 3 errors. The
driver id D-101 appears twice, so both drivers sharing
that id count as blocked even though the first one is
otherwise clean. Rosa Diaz (D-117) has an MVR exactly
365 days old, which passes, and Uma Yates (D-120) has
an inquiry exactly 30 days after hire, which also
passes. Sam Webb (D-118) has a medical certificate
expiring exactly on the as-of date, which counts as
expiring soon, not expired.

Use it as a CI gate: `--check` exits 1 when any error is
found, and 0 otherwise. On the sample above it exits 1:

```bash
python3 driver_qualification_doctor.py examples/drivers.csv --as-of 2026-11-18 --check
```

On `examples/clean.csv`, five clean drivers, it exits 0:

```
Drivers: 5, findings: 0, errors: 0, warnings: 0
Ready to drive: 5 of 5 drivers
Expired CDL: 0, expired medical: 0, CDL expiring soon: 0, medical expiring soon: 0, stale MVR: 0, overdue review: 0, missing road test: 0, missing employer inquiry: 0, late employer inquiry: 0, dispatched while expired: 0

Per-driver readiness:
D-301 (Alice Hart): 0 errors, 0 warnings, READY
D-302 (Bob Lane): 0 errors, 0 warnings, READY
D-303 (Carla Moss): 0 errors, 0 warnings, READY
D-304 (Dan Cole): 0 errors, 0 warnings, READY
D-305 (Erin Fox): 0 errors, 0 warnings, READY

All drivers clean.
```

With `--strict`, `--check` also fails on warnings.
`examples/warnings-only.csv` has two medical certificates
expiring soon and one CDL expiring soon, so it passes
`--check` (exit 0) and fails `--check --strict`
(exit 1). With a longer MVR window the stale-MVR
finding drops out:

```bash
python3 driver_qualification_doctor.py examples/drivers.csv --as-of 2026-11-18 --mvr-days 500
```

Captured output (the D-105 stale-MVR error drops out;
the rest of the output is identical to the default run):

```
Drivers: 22, findings: 22, errors: 20, warnings: 2
Ready to drive: 6 of 22 drivers
Expired CDL: 2, expired medical: 2, CDL expiring soon: 0, medical expiring soon: 2, stale MVR: 0, overdue review: 1, missing road test: 1, missing employer inquiry: 1, late employer inquiry: 1, dispatched while expired: 3
```

`--json` emits the summary and the findings as JSON, and
`--out` writes the report to a file. JSON for the
warnings-only file:

```json
{
  "drivers": 3,
  "findings": [
    {
      "driver": "D-401",
      "rule": "medical-expiring-soon",
      "severity": "warning",
      "message": "medical certificate expires on 2026-12-10, in 22.0 days"
    },
    {
      "driver": "D-402",
      "rule": "cdl-expiring-soon",
      "severity": "warning",
      "message": "CDL expires on 2026-12-05, in 17.0 days"
    },
    {
      "driver": "D-403",
      "rule": "medical-expiring-soon",
      "severity": "warning",
      "message": "medical certificate expires on 2026-11-25, in 7.0 days"
    }
  ],
  "errors": 0,
  "warnings": 3,
  "ready_to_drive": 3,
  "blocked": 0,
  "expired_cdl": 0,
  "expired_medical": 0,
  "cdl_expiring_soon": 1,
  "medical_expiring_soon": 2,
  "stale_mvr": 0,
  "overdue_review": 0,
  "missing_road_test": 0,
  "missing_employer_inquiry": 0,
  "late_employer_inquiry": 0,
  "dispatched_while_expired": 0,
  "per_driver": [
    {
      "driver": "D-401",
      "name": "Dan Cole",
      "errors": 0,
      "warnings": 1,
      "status": "READY"
    },
    {
      "driver": "D-402",
      "name": "Erin Fox",
      "errors": 0,
      "warnings": 1,
      "status": "READY"
    },
    {
      "driver": "D-403",
      "name": "Frank Hale",
      "errors": 0,
      "warnings": 1,
      "status": "READY"
    }
  ]
}
```

## Options

| Flag | Meaning |
| --- | --- |
| `--expiry-days` | A CDL or medical certificate expiring within this many days counts as expiring soon (default: 30) |
| `--mvr-days` | An MVR older than this many days counts as stale (default: 365) |
| `--as-of` | Date to compare timestamps against, for example 2026-11-18 (default: now) |
| `--json` | Emit JSON instead of text |
| `--check` | Exit 1 if any error is found |
| `--strict` | With --check, also exit 1 on warnings |
| `--out` | Write the report to a file |

## Edge cases

* A row with too many or too few fields is a malformed-row
  error and is skipped; the rest of the file is still
  audited. A malformed row is not a driver, so it never
  counts for or against the readiness count.
* A bad date is an error, and the row is still audited on
  the fields that did parse, so one bad value never hides
  the other problems on the driver. A driver with an
  unreadable expiry date is left out of the expiry checks,
  and a driver with an unreadable MVR date is left out of
  the staleness check.
* A CDL or medical certificate expiring exactly on the
  as-of date counts as expiring soon, not expired. An MVR
  exactly `--mvr-days` old passes, and an annual review
  exactly 365 days old passes.
* A previous-employer inquiry completed exactly 30 days
  after hire passes; an inquiry dated before the hire
  date also passes, since the inquiry may be done before
  the driver starts. With no hire date the window cannot
  be checked, so it is skipped.
* A driver id that appears twice blocks both drivers
  sharing it, since the id can no longer be trusted to
  identify one driver.
* A dispatched flag of `no` or an empty dispatched cell
  never triggers dispatched-while-expired, even when the
  CDL or medical certificate is expired; the expiry error
  still fires on its own.
* A blank line in the file is skipped silently.
* `--as-of` makes runs reproducible: without it, the
  future-timestamp and expiry checks compare against the
  current time.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

72 tests, all passing: timestamp and yes/no parsing,
header aliases and BOM handling, malformed rows, blank
lines, duplicate and missing driver ids, missing required
columns, missing DQ file items (CDL number, medical
certificate, MVR, annual review, road test, employer
inquiry), invalid dates and future hire dates, CDL and
medical expiry and expiring-soon boundaries, stale MVR
and overdue review boundaries, the 30 day employer
inquiry window including its boundaries, dispatched
while expired for CDL, medical, and both, summary counts
and readiness, the per-driver readiness table, text and
JSON output, `--out` file output, `--expiry-days` and
`--mvr-days` flags, and `--check` and `--strict` exit
codes. The same 72 tests pass under pytest.

## License

MIT. See [LICENSE](LICENSE).
