"""Driver qualification file audit CLI.

Reads a driver qualification file CSV export (from a
carrier spreadsheet, a TMS export, or a manual DQ file
checklist) and audits every driver against the 49 CFR
391.51 qualification file checklist: a missing DQ file
item, an expired CDL or medical certificate, a medical
certificate expiring soon, an MVR older than 12 months,
an overdue annual review, a missing road test
certificate, a previous-employer inquiry that is
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

Each problem is a finding with a driver id, a rule
name, a severity (error or warning), and a message.
Errors are missing DQ file items, expired CDL or
medical certificates, a stale MVR, an overdue annual
review, a late previous-employer inquiry, a driver
dispatched while expired, and data that cannot be
trusted; warnings are CDL or medical certificates
expiring soon. --check exits 1 when any error is
found, and --strict also fails on warnings.

Dates are parsed defensively. A bad date is reported
as a finding and the row is still audited on the fields
that did parse, so one bad row never crashes the run.

Zero dependencies, Python 3.9 or newer, standard library only.

Usage:
    python3 driver_qualification_doctor.py examples/drivers.csv
    python3 driver_qualification_doctor.py drivers.csv --json --check
    python3 driver_qualification_doctor.py drivers.csv --as-of 2026-11-18
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone

__version__ = "1.0.0"

DEFAULT_EXPIRY_DAYS = 30
DEFAULT_MVR_DAYS = 365
ANNUAL_REVIEW_DAYS = 365
EMPLOYER_INQUIRY_DAYS = 30

YES_VALUES = {"yes", "y", "true", "1", "received", "on file",
              "present", "filed", "dispatched", "active"}
NO_VALUES = {"no", "n", "false", "0", "not received", "missing",
             "not dispatched", "off duty"}

TIMESTAMP_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M",
    "%d/%m/%Y",
    "%m/%d/%Y",
)


class Finding:
    """One audit finding for one driver."""

    def __init__(self, driver, rule, severity, message):
        self.driver = driver
        self.rule = rule
        self.severity = severity
        self.message = message

    def as_dict(self):
        """Return the finding as a plain dict."""
        return {"driver": self.driver, "rule": self.rule,
                "severity": self.severity, "message": self.message}

    def __str__(self):
        return "%s [%s] %s: %s" % (self.severity.upper(), self.rule,
                                   self.driver, self.message)


def parse_timestamp(text):
    """Parse a timestamp string into an aware datetime, or None.

    Accepts ISO 8601 with or without a timezone (a trailing Z is
    handled), plus a few common export formats. A naive timestamp
    is read as UTC. Returns None for an empty string or a value
    that matches no known format, so callers can report it
    instead of crashing.
    """
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    candidate = text
    if candidate.endswith(("Z", "z")):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in TIMESTAMP_FORMATS:
            try:
                parsed = datetime.strptime(candidate, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_yes_no(text):
    """Parse a yes/no cell into True, False, or None.

    Returns None for an empty cell or a value that is neither
    a recognized yes nor a recognized no, so callers can fall
    back to a derived value instead of guessing.
    """
    if text is None:
        return None
    value = text.strip().lower()
    if not value:
        return None
    if value in YES_VALUES:
        return True
    if value in NO_VALUES:
        return False
    return None


def find_column(header, names):
    """Return the first of names present in header, or None."""
    for name in names:
        if name in header:
            return name
    return None


def parse_csv(path, as_of):
    """Parse a driver qualification file CSV export.

    Returns (drivers, findings). Each driver is a dict with
    the id, name, CDL number and expiry, medical certificate
    expiry, MVR date, annual review date, road test date,
    previous-employer inquiry date, hire date, and
    dispatched flag. Rows with the wrong number of fields
    are reported as malformed-row errors and skipped, never
    a crash. A UTF-8 BOM header is handled. Extra columns
    are ignored.
    """
    findings = []
    drivers = []
    try:
        handle = open(path, newline="", encoding="utf-8-sig")
    except OSError as exc:
        raise ValueError("cannot read %s: %s" % (path, exc))
    with handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            raise ValueError("%s is empty, no header row found" % path)
        except csv.Error as exc:
            raise ValueError("%s is not a readable CSV file: %s"
                             % (path, exc))
        header = [name.strip() for name in header]
        id_column = find_column(header, ("driver_id", "id", "driver"))
        if id_column is None:
            raise ValueError(
                "%s has no driver_id or id column (header is: %s)"
                % (path, ", ".join(header)))
        cdl_expiry_column = find_column(
            header, ("cdl_expiry", "cdl_expiration", "cdl_expires",
                     "cdl_expiry_date"))
        if cdl_expiry_column is None:
            raise ValueError(
                "%s has no cdl_expiry column "
                "(header is: %s)" % (path, ", ".join(header)))
        medical_column = find_column(
            header, ("medical_expiry", "medical_certificate_expiry",
                     "medical_expires", "med_cert_expiry",
                     "medical_certificate_expiration"))
        if medical_column is None:
            raise ValueError(
                "%s has no medical_expiry column "
                "(header is: %s)" % (path, ", ".join(header)))
        name_column = find_column(header, ("driver_name", "name",
                                           "full_name"))
        cdl_column = find_column(header, ("cdl_number", "cdl",
                                          "cdl_no", "license_number"))
        mvr_column = find_column(header, ("mvr_date", "mvr",
                                          "last_mvr_date",
                                          "mvr_inquiry_date"))
        review_column = find_column(
            header, ("annual_review_date", "review_date",
                     "last_annual_review", "annual_review"))
        road_test_column = find_column(
            header, ("road_test_date", "road_test",
                     "last_road_test", "road_test_certificate_date"))
        inquiry_column = find_column(
            header, ("prev_employer_inquiry_date",
                     "previous_employer_inquiry_date",
                     "employer_inquiry_date",
                     "prev_employer_inquiry"))
        hire_column = find_column(header, ("hire_date", "hired_date",
                                           "employment_date",
                                           "date_of_hire"))
        dispatched_column = find_column(
            header, ("dispatched", "is_dispatched",
                     "currently_dispatched", "on_dispatch"))
        seen_ids = set()
        for line_number, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) != len(header):
                findings.append(Finding(
                    "row %d" % line_number, "malformed-row", "error",
                    "row has %d fields but the header has %d, "
                    "so the row was skipped" % (len(row), len(header))))
                continue
            cells = dict(zip(header, (cell.strip() for cell in row)))
            driver_id = cells[id_column]
            if not driver_id:
                findings.append(Finding(
                    "row %d" % line_number, "missing-driver-id",
                    "error",
                    "row has no driver id, so the driver "
                    "cannot be matched to a DQ file"))
                driver_id = "row %d" % line_number
            if driver_id in seen_ids:
                findings.append(Finding(
                    driver_id, "duplicate-driver-id", "error",
                    "driver id appears more than once in the export"))
            else:
                seen_ids.add(driver_id)

            def parse_date(column, label):
                """Parse one date cell, reporting a bad date."""
                raw = cells[column] if column else ""
                if not raw:
                    return None, raw
                parsed = parse_timestamp(raw)
                if parsed is None:
                    findings.append(Finding(
                        driver_id, "invalid-date", "error",
                        "%s date %r is not a readable date"
                        % (label, raw)))
                return parsed, raw

            cdl_expiry, cdl_expiry_raw = parse_date(
                cdl_expiry_column, "CDL expiry")
            medical_expiry, medical_expiry_raw = parse_date(
                medical_column, "medical certificate expiry")
            mvr_date, _mvr_raw = parse_date(mvr_column, "MVR")
            review_date, _review_raw = parse_date(
                review_column, "annual review")
            road_test_date, _road_raw = parse_date(
                road_test_column, "road test")
            inquiry_date, _inquiry_raw = parse_date(
                inquiry_column, "previous-employer inquiry")
            hire_date, _hire_raw = parse_date(hire_column, "hire")
            if hire_date is not None and hire_date > as_of:
                findings.append(Finding(
                    driver_id, "future-timestamp", "error",
                    "hire date %s is after the as-of date %s"
                    % (hire_date.strftime("%Y-%m-%d %H:%M"),
                       as_of.strftime("%Y-%m-%d %H:%M"))))
            if cdl_column is not None and not cells[cdl_column]:
                findings.append(Finding(
                    driver_id, "missing-cdl-number", "error",
                    "driver has no CDL number recorded, so the "
                    "license cannot be checked"))
            if not medical_expiry_raw:
                findings.append(Finding(
                    driver_id, "missing-medical-certificate", "error",
                    "driver has no medical certificate expiry "
                    "recorded, so the DQ file has no medical "
                    "certificate"))
            if mvr_column is not None and not cells[mvr_column]:
                findings.append(Finding(
                    driver_id, "missing-mvr", "error",
                    "driver has no MVR date recorded, so the "
                    "annual MVR inquiry is missing from the "
                    "DQ file"))
            if review_column is not None and not cells[review_column]:
                findings.append(Finding(
                    driver_id, "missing-annual-review", "error",
                    "driver has no annual review date recorded, "
                    "so the annual review is missing from the "
                    "DQ file"))
            if road_test_column is not None and not cells[road_test_column]:
                findings.append(Finding(
                    driver_id, "missing-road-test", "error",
                    "driver has no road test date recorded, so "
                    "the road test certificate is missing from "
                    "the DQ file"))
            if inquiry_column is not None and not cells[inquiry_column]:
                findings.append(Finding(
                    driver_id, "missing-employer-inquiry", "error",
                    "driver has no previous-employer inquiry "
                    "date recorded, so the inquiry is missing "
                    "from the DQ file"))
            drivers.append({
                "id": driver_id,
                "name": (cells[name_column]
                         if name_column else ""),
                "cdl_number": (cells[cdl_column]
                               if cdl_column else ""),
                "has_cdl_column": cdl_column is not None,
                "cdl_expiry": cdl_expiry,
                "medical_expiry": medical_expiry,
                "mvr_date": mvr_date,
                "annual_review_date": review_date,
                "road_test_date": road_test_date,
                "inquiry_date": inquiry_date,
                "hire_date": hire_date,
                "dispatched": (parse_yes_no(cells[dispatched_column])
                               if dispatched_column else None),
                "line": line_number})
    return drivers, findings


def audit(drivers, as_of,
          expiry_days=DEFAULT_EXPIRY_DAYS,
          mvr_days=DEFAULT_MVR_DAYS):
    """Audit a parsed driver list and return a list of findings."""
    findings = []
    for driver in drivers:
        driver_id = driver["id"]
        cdl_expiry = driver["cdl_expiry"]
        cdl_expired = False
        if cdl_expiry is not None:
            age_days = (as_of - cdl_expiry).total_seconds() / 86400.0
            if cdl_expiry < as_of:
                cdl_expired = True
                findings.append(Finding(
                    driver_id, "cdl-expired", "error",
                    "CDL expired on %s, %.1f days ago"
                    % (cdl_expiry.strftime("%Y-%m-%d"), age_days)))
            elif age_days >= -expiry_days:
                findings.append(Finding(
                    driver_id, "cdl-expiring-soon", "warning",
                    "CDL expires on %s, in %.1f days"
                    % (cdl_expiry.strftime("%Y-%m-%d"),
                       abs(-age_days))))
        medical_expiry = driver["medical_expiry"]
        medical_expired = False
        if medical_expiry is not None:
            age_days = (as_of - medical_expiry).total_seconds() / 86400.0
            if medical_expiry < as_of:
                medical_expired = True
                findings.append(Finding(
                    driver_id, "medical-expired", "error",
                    "medical certificate expired on %s, %.1f days ago"
                    % (medical_expiry.strftime("%Y-%m-%d"), age_days)))
            elif age_days >= -expiry_days:
                findings.append(Finding(
                    driver_id, "medical-expiring-soon", "warning",
                    "medical certificate expires on %s, in %.1f days"
                    % (medical_expiry.strftime("%Y-%m-%d"),
                       abs(-age_days))))
        mvr_date = driver["mvr_date"]
        if mvr_date is not None:
            mvr_age = (as_of - mvr_date).total_seconds() / 86400.0
            if mvr_age > mvr_days:
                findings.append(Finding(
                    driver_id, "stale-mvr", "error",
                    "MVR is %.1f days old, older than the %d day "
                    "limit" % (mvr_age, mvr_days)))
        review_date = driver["annual_review_date"]
        if review_date is not None:
            review_age = (as_of - review_date).total_seconds() / 86400.0
            if review_age > ANNUAL_REVIEW_DAYS:
                findings.append(Finding(
                    driver_id, "annual-review-overdue", "error",
                    "annual review is %.1f days old, overdue past "
                    "the %d day annual cycle"
                    % (review_age, ANNUAL_REVIEW_DAYS)))
        inquiry_date = driver["inquiry_date"]
        hire_date = driver["hire_date"]
        if inquiry_date is not None and hire_date is not None:
            window = (inquiry_date - hire_date
                      ).total_seconds() / 86400.0
            if window > EMPLOYER_INQUIRY_DAYS:
                findings.append(Finding(
                    driver_id, "employer-inquiry-late", "error",
                    "previous-employer inquiry was completed "
                    "%.1f days after hire, past the %d day window"
                    % (window, EMPLOYER_INQUIRY_DAYS)))
        if driver["dispatched"] is True and (
                cdl_expired or medical_expired):
            expired_items = []
            if cdl_expired:
                expired_items.append("CDL")
            if medical_expired:
                expired_items.append("medical certificate")
            findings.append(Finding(
                driver_id, "dispatched-while-expired", "error",
                "driver is dispatched while the %s %s expired"
                % (" and ".join(expired_items),
                   "are" if len(expired_items) > 1 else "is")))
    return findings


def summarize(drivers, findings, as_of):
    """Return the summary counts for a driver list and findings."""
    errors = sum(1 for item in findings if item.severity == "error")
    warnings = sum(1 for item in findings
                   if item.severity == "warning")
    driver_ids = set(item["id"] for item in drivers)
    drivers_with_errors = set()
    for item in findings:
        if item.severity == "error" and item.driver in driver_ids:
            drivers_with_errors.add(item.driver)
    ready = sum(1 for item in drivers
                if item["id"] not in drivers_with_errors)

    def count_rule(rule):
        return sum(1 for item in findings if item.rule == rule)

    per_driver = []
    for driver in drivers:
        driver_errors = sum(
            1 for item in findings
            if item.severity == "error"
            and item.driver == driver["id"])
        driver_warnings = sum(
            1 for item in findings
            if item.severity == "warning"
            and item.driver == driver["id"])
        per_driver.append({
            "driver": driver["id"],
            "name": driver["name"],
            "errors": driver_errors,
            "warnings": driver_warnings,
            "status": "READY" if driver_errors == 0 else "NOT READY"})
    return {"drivers": len(drivers),
            "findings": len(findings),
            "errors": errors,
            "warnings": warnings,
            "ready_to_drive": ready,
            "blocked": len(drivers) - ready,
            "expired_cdl": count_rule("cdl-expired"),
            "expired_medical": count_rule("medical-expired"),
            "cdl_expiring_soon": count_rule("cdl-expiring-soon"),
            "medical_expiring_soon": count_rule(
                "medical-expiring-soon"),
            "stale_mvr": count_rule("stale-mvr"),
            "overdue_review": count_rule("annual-review-overdue"),
            "missing_road_test": count_rule("missing-road-test"),
            "missing_employer_inquiry": count_rule(
                "missing-employer-inquiry"),
            "late_employer_inquiry": count_rule(
                "employer-inquiry-late"),
            "dispatched_while_expired": count_rule(
                "dispatched-while-expired"),
            "per_driver": per_driver}


def render_text(drivers, findings, summary):
    """Render the text report."""
    lines = [str(item) for item in findings]
    lines.append("")
    lines.append("Drivers: %(drivers)d, findings: %(findings)d, "
                 "errors: %(errors)d, warnings: %(warnings)d"
                 % summary)
    lines.append("Ready to drive: %(ready_to_drive)d of "
                 "%(drivers)d drivers" % summary)
    lines.append("Expired CDL: %(expired_cdl)d, expired medical: "
                 "%(expired_medical)d, CDL expiring soon: "
                 "%(cdl_expiring_soon)d, medical expiring soon: "
                 "%(medical_expiring_soon)d, stale MVR: "
                 "%(stale_mvr)d, overdue review: %(overdue_review)d, "
                 "missing road test: %(missing_road_test)d, missing "
                 "employer inquiry: %(missing_employer_inquiry)d, "
                 "late employer inquiry: %(late_employer_inquiry)d, "
                 "dispatched while expired: "
                 "%(dispatched_while_expired)d" % summary)
    lines.append("")
    lines.append("Per-driver readiness:")
    for row in summary["per_driver"]:
        lines.append(
            "%s %s: %d errors, %d warnings, %s"
            % (row["driver"],
               ("(%s)" % row["name"]) if row["name"] else "",
               row["errors"], row["warnings"], row["status"]))
    if summary["findings"] == 0:
        lines.append("")
        lines.append("All drivers clean.")
    return "\n".join(lines) + "\n"


def render_json(drivers, findings, summary):
    """Render the JSON report."""
    report = dict(summary)
    report["findings"] = [item.as_dict() for item in findings]
    return json.dumps(report, indent=2) + "\n"


def build_parser():
    """Build the command line parser."""
    parser = argparse.ArgumentParser(
        prog="driver-qualification-doctor",
        description="Audit a driver qualification file CSV "
                    "export for missing DQ file items, expired "
                    "CDL or medical certificates, a stale MVR, "
                    "an overdue annual review, a missing road "
                    "test, and a late previous-employer inquiry.")
    parser.add_argument("csv_file", help="driver qualification "
                        "file CSV export to audit")
    parser.add_argument("--expiry-days", type=int,
                        default=DEFAULT_EXPIRY_DAYS,
                        help="a CDL or medical certificate expiring "
                        "within this many days counts as expiring "
                        "soon (default: %d)" % DEFAULT_EXPIRY_DAYS)
    parser.add_argument("--mvr-days", type=int,
                        default=DEFAULT_MVR_DAYS,
                        help="an MVR older than this many days "
                        "counts as stale "
                        "(default: %d)" % DEFAULT_MVR_DAYS)
    parser.add_argument("--as-of", default=None,
                        help="date to compare timestamps against, "
                        "for example 2026-11-18 (default: now)")
    parser.add_argument("--json", action="store_true",
                        help="emit JSON instead of text")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if any error is found")
    parser.add_argument("--strict", action="store_true",
                        help="with --check, also exit 1 on warnings")
    parser.add_argument("--out", default=None,
                        help="write the report to a file")
    return parser


def main(argv=None):
    """Run the CLI and return the exit code."""
    args = build_parser().parse_args(argv)
    if args.expiry_days < 0:
        print("error: --expiry-days must be at least 0",
              file=sys.stderr)
        return 2
    if args.mvr_days < 0:
        print("error: --mvr-days must be at least 0",
              file=sys.stderr)
        return 2
    if args.as_of is None:
        as_of = datetime.now(timezone.utc)
    else:
        as_of = parse_timestamp(args.as_of)
        if as_of is None:
            print("error: --as-of %r is not a readable date"
                  % args.as_of, file=sys.stderr)
            return 2
    try:
        drivers, findings = parse_csv(args.csv_file, as_of)
    except ValueError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    findings.extend(audit(drivers, as_of,
                          expiry_days=args.expiry_days,
                          mvr_days=args.mvr_days))
    summary = summarize(drivers, findings, as_of)
    if args.json:
        report = render_json(drivers, findings, summary)
    else:
        report = render_text(drivers, findings, summary)
    if args.out is not None:
        try:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(report)
        except OSError as exc:
            print("error: cannot write %s: %s" % (args.out, exc),
                  file=sys.stderr)
            return 2
    else:
        sys.stdout.write(report)
    if args.check:
        if summary["errors"] > 0:
            return 1
        if args.strict and summary["warnings"] > 0:
            return 1
    return 0


def main_entry():
    """Console script entry point."""
    sys.exit(main())


if __name__ == "__main__":
    main_entry()
