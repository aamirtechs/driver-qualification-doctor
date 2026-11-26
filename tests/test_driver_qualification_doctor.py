"""Tests for driver_qualification_doctor."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))

import driver_qualification_doctor as doctor

AS_OF = datetime(2026, 11, 18, tzinfo=timezone.utc)

HEADER = ("driver_id,driver_name,cdl_number,cdl_expiry,"
          "medical_expiry,mvr_date,annual_review_date,"
          "road_test_date,prev_employer_inquiry_date,hire_date,"
          "dispatched\n")


def write_csv(body, directory=None):
    """Write body to a temp CSV file and return its path."""
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False,
        dir=directory, encoding="utf-8")
    handle.write(body)
    handle.close()
    return handle.name


def row(driver_id="D-1", name="Test Driver", cdl="CDL-1001",
        cdl_expiry="2027-06-30", medical="2027-01-15",
        mvr="2026-06-01", review="2026-05-01",
        road_test="2024-03-01", inquiry="2026-02-01",
        hire="2026-01-15", dispatched="no"):
    """Build one CSV data row."""
    return ",".join((driver_id, name, cdl, cdl_expiry, medical,
                     mvr, review, road_test, inquiry, hire,
                     dispatched)) + "\n"


def run_cli(argv):
    """Run main with argv and capture stdout, return (code, text)."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = doctor.main(argv)
    return code, buffer.getvalue()


def parse_and_audit(body, **kwargs):
    """Parse body and audit it, return (drivers, findings)."""
    path = write_csv(HEADER + body)
    try:
        drivers, findings = doctor.parse_csv(path, AS_OF)
        findings.extend(doctor.audit(drivers, AS_OF, **kwargs))
        return drivers, findings
    finally:
        os.unlink(path)


def rules(findings):
    """Return the sorted rule names of a finding list."""
    return sorted(item.rule for item in findings)


def findings_for(findings, driver_id):
    """Return the findings for one driver id."""
    return [item for item in findings
            if item.driver == driver_id]


class TestParsing(unittest.TestCase):
    """Timestamp and yes/no parsing."""

    def test_parse_timestamp_iso(self):
        parsed = doctor.parse_timestamp("2026-11-17 10:00")
        self.assertEqual(parsed,
                         datetime(2026, 11, 17, 10, 0,
                                  tzinfo=timezone.utc))

    def test_parse_timestamp_zulu(self):
        parsed = doctor.parse_timestamp("2026-11-17T10:00:00Z")
        self.assertEqual(parsed,
                         datetime(2026, 11, 17, 10, 0,
                                  tzinfo=timezone.utc))

    def test_parse_timestamp_date_only(self):
        parsed = doctor.parse_timestamp("2026-11-17")
        self.assertEqual(parsed,
                         datetime(2026, 11, 17, tzinfo=timezone.utc))

    def test_parse_timestamp_day_month_year(self):
        parsed = doctor.parse_timestamp("17/11/2026")
        self.assertEqual(parsed,
                         datetime(2026, 11, 17, tzinfo=timezone.utc))

    def test_parse_timestamp_month_day_year(self):
        parsed = doctor.parse_timestamp("11/17/2026")
        self.assertEqual(parsed,
                         datetime(2026, 11, 17, tzinfo=timezone.utc))

    def test_parse_timestamp_bad(self):
        self.assertIsNone(doctor.parse_timestamp("not-a-date"))

    def test_parse_timestamp_empty(self):
        self.assertIsNone(doctor.parse_timestamp(""))
        self.assertIsNone(doctor.parse_timestamp(None))

    def test_parse_yes_no(self):
        self.assertIs(doctor.parse_yes_no("yes"), True)
        self.assertIs(doctor.parse_yes_no("on file"), True)
        self.assertIs(doctor.parse_yes_no("received"), True)
        self.assertIs(doctor.parse_yes_no("no"), False)
        self.assertIs(doctor.parse_yes_no("missing"), False)
        self.assertIsNone(doctor.parse_yes_no(""))
        self.assertIsNone(doctor.parse_yes_no("maybe"))
        self.assertIsNone(doctor.parse_yes_no(None))

    def test_finding_str(self):
        finding = doctor.Finding("D-1", "cdl-expired", "error",
                                 "CDL expired")
        self.assertEqual(str(finding),
                         "ERROR [cdl-expired] D-1: CDL expired")
        self.assertEqual(finding.as_dict(),
                         {"driver": "D-1", "rule": "cdl-expired",
                          "severity": "error",
                          "message": "CDL expired"})


class TestHeaderAndRows(unittest.TestCase):
    """Header aliases, BOM, malformed rows, and ids."""

    def test_header_aliases(self):
        header = ("id,full_name,cdl,cdl_expiration,"
                  "medical_certificate_expiry,mvr,"
                  "review_date,road_test,employer_inquiry_date,"
                  "hired_date,is_dispatched\n")
        body = ("D-1,Test Driver,CDL-1001,2027-06-30,2027-01-15,"
                "2026-06-01,2026-05-01,2024-03-01,2026-02-01,"
                "2026-01-15,no\n")
        path = write_csv(header + body)
        try:
            drivers, findings = doctor.parse_csv(path, AS_OF)
        finally:
            os.unlink(path)
        self.assertEqual(len(drivers), 1)
        self.assertEqual(findings, [])

    def test_bom_header(self):
        path = write_csv("\ufeff" + HEADER + row())
        try:
            drivers, findings = doctor.parse_csv(path, AS_OF)
        finally:
            os.unlink(path)
        self.assertEqual(len(drivers), 1)
        self.assertEqual(findings, [])

    def test_extra_columns_ignored(self):
        header = HEADER.rstrip("\n") + ",notes\n"
        body = row().rstrip("\n") + ",hired through agency\n"
        path = write_csv(header + body)
        try:
            drivers, findings = doctor.parse_csv(path, AS_OF)
        finally:
            os.unlink(path)
        self.assertEqual(len(drivers), 1)
        self.assertEqual(findings, [])

    def test_missing_driver_id_column(self):
        header = HEADER.replace("driver_id,", "")
        path = write_csv(header + row().split(",", 1)[1])
        try:
            with self.assertRaises(ValueError):
                doctor.parse_csv(path, AS_OF)
        finally:
            os.unlink(path)

    def test_missing_cdl_expiry_column(self):
        header = HEADER.replace("cdl_expiry,", "")
        body = row().replace("2027-06-30,", "", 1)
        path = write_csv(header + body)
        try:
            with self.assertRaises(ValueError):
                doctor.parse_csv(path, AS_OF)
        finally:
            os.unlink(path)

    def test_missing_medical_expiry_column(self):
        header = HEADER.replace("medical_expiry,", "")
        body = row().replace("2027-01-15,", "", 1)
        path = write_csv(header + body)
        try:
            with self.assertRaises(ValueError):
                doctor.parse_csv(path, AS_OF)
        finally:
            os.unlink(path)

    def test_empty_file(self):
        path = write_csv("")
        try:
            with self.assertRaises(ValueError):
                doctor.parse_csv(path, AS_OF)
        finally:
            os.unlink(path)

    def test_missing_file(self):
        with self.assertRaises(ValueError):
            doctor.parse_csv("/nonexistent/drivers.csv", AS_OF)

    def test_malformed_row_skipped(self):
        body = row() + row(driver_id="D-2").rstrip("\n") + ",extra\n"
        drivers, findings = parse_and_audit(body)
        self.assertEqual(len(drivers), 1)
        self.assertEqual(rules(findings), ["malformed-row"])

    def test_blank_lines_skipped(self):
        body = row() + "\n" + row(driver_id="D-2")
        drivers, findings = parse_and_audit(body)
        self.assertEqual(len(drivers), 2)
        self.assertEqual(findings, [])

    def test_duplicate_driver_id(self):
        body = row() + row(name="Other Driver")
        drivers, findings = parse_and_audit(body)
        self.assertEqual(len(drivers), 2)
        self.assertEqual(rules(findings), ["duplicate-driver-id"])

    def test_missing_driver_id(self):
        body = row(driver_id="")
        drivers, findings = parse_and_audit(body)
        self.assertEqual(len(drivers), 1)
        self.assertEqual(rules(findings), ["missing-driver-id"])
        self.assertEqual(drivers[0]["id"], "row 2")

    def test_optional_columns_absent(self):
        header = ("driver_id,driver_name,cdl_number,cdl_expiry,"
                  "medical_expiry,hire_date,dispatched\n")
        body = ("D-1,Test Driver,CDL-1001,2027-06-30,2027-01-15,"
                "2026-01-15,no\n")
        path = write_csv(header + body)
        try:
            drivers, findings = doctor.parse_csv(path, AS_OF)
            findings.extend(doctor.audit(drivers, AS_OF))
        finally:
            os.unlink(path)
        self.assertEqual(findings, [])


class TestMissingItems(unittest.TestCase):
    """Missing DQ file items."""

    def test_missing_cdl_number(self):
        drivers, findings = parse_and_audit(row(cdl=""))
        self.assertEqual(rules(findings), ["missing-cdl-number"])

    def test_missing_medical_certificate(self):
        drivers, findings = parse_and_audit(row(medical=""))
        self.assertEqual(rules(findings),
                         ["missing-medical-certificate"])

    def test_missing_mvr(self):
        drivers, findings = parse_and_audit(row(mvr=""))
        self.assertEqual(rules(findings), ["missing-mvr"])

    def test_missing_annual_review(self):
        drivers, findings = parse_and_audit(row(review=""))
        self.assertEqual(rules(findings), ["missing-annual-review"])

    def test_missing_road_test(self):
        drivers, findings = parse_and_audit(row(road_test=""))
        self.assertEqual(rules(findings), ["missing-road-test"])

    def test_missing_employer_inquiry(self):
        drivers, findings = parse_and_audit(row(inquiry=""))
        self.assertEqual(rules(findings),
                         ["missing-employer-inquiry"])

    def test_missing_items_do_not_cascade(self):
        drivers, findings = parse_and_audit(
            row(medical="", mvr="", review="", road_test="",
                inquiry=""))
        self.assertEqual(
            rules(findings),
            ["missing-annual-review", "missing-employer-inquiry",
             "missing-medical-certificate", "missing-mvr",
             "missing-road-test"])


class TestDatesAndExpiry(unittest.TestCase):
    """Invalid dates, future dates, expiry, and staleness."""

    def test_invalid_date_reported_row_still_audited(self):
        drivers, findings = parse_and_audit(
            row(medical="not-a-date", cdl_expiry="2026-10-01"))
        self.assertEqual(
            rules(findings), ["cdl-expired", "invalid-date"])

    def test_future_hire_date(self):
        drivers, findings = parse_and_audit(row(hire="2026-12-05"))
        self.assertEqual(rules(findings), ["future-timestamp"])

    def test_cdl_expired(self):
        drivers, findings = parse_and_audit(
            row(cdl_expiry="2026-10-01"))
        self.assertEqual(rules(findings), ["cdl-expired"])
        self.assertIn("48.0 days ago", findings[0].message)

    def test_medical_expired(self):
        drivers, findings = parse_and_audit(
            row(medical="2026-09-15"))
        self.assertEqual(rules(findings), ["medical-expired"])
        self.assertIn("64.0 days ago", findings[0].message)

    def test_cdl_expiring_soon(self):
        drivers, findings = parse_and_audit(
            row(cdl_expiry="2026-12-05"))
        self.assertEqual(rules(findings), ["cdl-expiring-soon"])
        self.assertIn("in 17.0 days", findings[0].message)

    def test_medical_expiring_soon(self):
        drivers, findings = parse_and_audit(
            row(medical="2026-12-10"))
        self.assertEqual(rules(findings),
                         ["medical-expiring-soon"])

    def test_expiry_on_as_of_counts_as_soon_not_expired(self):
        drivers, findings = parse_and_audit(
            row(cdl_expiry="2026-11-18", medical="2026-11-18"))
        self.assertEqual(
            rules(findings),
            ["cdl-expiring-soon", "medical-expiring-soon"])

    def test_expiry_just_outside_window(self):
        drivers, findings = parse_and_audit(
            row(cdl_expiry="2026-12-19", medical="2026-12-19"))
        self.assertEqual(findings, [])

    def test_expiry_days_flag(self):
        drivers, findings = parse_and_audit(
            row(cdl_expiry="2026-12-19"), expiry_days=31)
        self.assertEqual(rules(findings), ["cdl-expiring-soon"])

    def test_stale_mvr(self):
        drivers, findings = parse_and_audit(row(mvr="2025-09-01"))
        self.assertEqual(rules(findings), ["stale-mvr"])
        self.assertIn("443.0 days old", findings[0].message)

    def test_mvr_exactly_at_limit_passes(self):
        drivers, findings = parse_and_audit(row(mvr="2025-11-18"))
        self.assertEqual(findings, [])

    def test_mvr_one_day_over_limit_fails(self):
        drivers, findings = parse_and_audit(row(mvr="2025-11-17"))
        self.assertEqual(rules(findings), ["stale-mvr"])

    def test_mvr_days_flag(self):
        drivers, findings = parse_and_audit(row(mvr="2025-09-01"),
                                            mvr_days=500)
        self.assertEqual(findings, [])

    def test_annual_review_overdue(self):
        drivers, findings = parse_and_audit(
            row(review="2025-10-01"))
        self.assertEqual(rules(findings), ["annual-review-overdue"])
        self.assertIn("413.0 days old", findings[0].message)

    def test_annual_review_exactly_at_limit_passes(self):
        drivers, findings = parse_and_audit(
            row(review="2025-11-18"))
        self.assertEqual(findings, [])

    def test_annual_review_one_day_over_limit_fails(self):
        drivers, findings = parse_and_audit(
            row(review="2025-11-17"))
        self.assertEqual(rules(findings), ["annual-review-overdue"])


class TestEmployerInquiry(unittest.TestCase):
    """The 30 day previous-employer inquiry window."""

    def test_inquiry_late(self):
        drivers, findings = parse_and_audit(
            row(hire="2026-01-10", inquiry="2026-03-15"))
        self.assertEqual(rules(findings), ["employer-inquiry-late"])
        self.assertIn("64.0 days after hire", findings[0].message)

    def test_inquiry_exactly_30_days_passes(self):
        drivers, findings = parse_and_audit(
            row(hire="2026-01-01", inquiry="2026-01-31"))
        self.assertEqual(findings, [])

    def test_inquiry_31_days_fails(self):
        drivers, findings = parse_and_audit(
            row(hire="2026-01-01", inquiry="2026-02-01"))
        self.assertEqual(rules(findings), ["employer-inquiry-late"])

    def test_inquiry_before_hire_passes(self):
        drivers, findings = parse_and_audit(
            row(hire="2026-02-01", inquiry="2026-01-15"))
        self.assertEqual(findings, [])

    def test_inquiry_window_skipped_without_hire_date(self):
        drivers, findings = parse_and_audit(
            row(hire="", inquiry="2026-03-15"))
        self.assertEqual(findings, [])


class TestDispatchedWhileExpired(unittest.TestCase):
    """Drivers dispatched while an item is expired."""

    def test_dispatched_with_expired_cdl(self):
        drivers, findings = parse_and_audit(
            row(cdl_expiry="2026-10-01", dispatched="yes"))
        self.assertEqual(
            rules(findings),
            ["cdl-expired", "dispatched-while-expired"])
        self.assertIn("the CDL is expired",
                      findings[1].message)

    def test_dispatched_with_expired_medical(self):
        drivers, findings = parse_and_audit(
            row(medical="2026-09-15", dispatched="yes"))
        self.assertEqual(
            rules(findings),
            ["dispatched-while-expired", "medical-expired"])

    def test_dispatched_with_both_expired(self):
        drivers, findings = parse_and_audit(
            row(cdl_expiry="2026-09-01", medical="2026-08-15",
                dispatched="yes"))
        self.assertEqual(
            rules(findings),
            ["cdl-expired", "dispatched-while-expired",
             "medical-expired"])
        dispatched = [item for item in findings
                      if item.rule == "dispatched-while-expired"][0]
        self.assertIn("CDL and medical certificate are expired",
                      dispatched.message)

    def test_not_dispatched_with_expired_cdl(self):
        drivers, findings = parse_and_audit(
            row(cdl_expiry="2026-10-01", dispatched="no"))
        self.assertEqual(rules(findings), ["cdl-expired"])

    def test_dispatched_clean_driver_passes(self):
        drivers, findings = parse_and_audit(row(dispatched="yes"))
        self.assertEqual(findings, [])

    def test_dispatched_with_expiring_soon_only(self):
        drivers, findings = parse_and_audit(
            row(medical="2026-12-10", dispatched="yes"))
        self.assertEqual(rules(findings), ["medical-expiring-soon"])


class TestSummaryAndOutput(unittest.TestCase):
    """Summary counts, readiness table, text and JSON output."""

    def test_summary_counts_and_readiness(self):
        body = (row()
                + row(driver_id="D-2", cdl_expiry="2026-10-01",
                      dispatched="yes")
                + row(driver_id="D-3", medical="2026-12-10"))
        drivers, findings = parse_and_audit(body)
        summary = doctor.summarize(drivers, findings, AS_OF)
        self.assertEqual(summary["drivers"], 3)
        self.assertEqual(summary["findings"], 3)
        self.assertEqual(summary["errors"], 2)
        self.assertEqual(summary["warnings"], 1)
        self.assertEqual(summary["ready_to_drive"], 2)
        self.assertEqual(summary["blocked"], 1)
        self.assertEqual(summary["expired_cdl"], 1)
        self.assertEqual(summary["dispatched_while_expired"], 1)
        self.assertEqual(summary["medical_expiring_soon"], 1)
        self.assertEqual(len(summary["per_driver"]), 3)
        self.assertEqual(summary["per_driver"][0]["status"], "READY")
        self.assertEqual(summary["per_driver"][1]["status"],
                         "NOT READY")
        self.assertEqual(summary["per_driver"][1]["errors"], 2)

    def test_duplicate_id_blocks_both_rows(self):
        body = row() + row(name="Other Driver")
        drivers, findings = parse_and_audit(body)
        summary = doctor.summarize(drivers, findings, AS_OF)
        self.assertEqual(summary["ready_to_drive"], 0)
        self.assertEqual(summary["blocked"], 2)

    def test_text_output(self):
        path = write_csv(HEADER + row(driver_id="D-2",
                                       cdl_expiry="2026-10-01",
                                       dispatched="yes"))
        try:
            code, text = run_cli([path, "--as-of", "2026-11-18"])
        finally:
            os.unlink(path)
        self.assertEqual(code, 0)
        self.assertIn("ERROR [cdl-expired] D-2", text)
        self.assertIn("Drivers: 1, findings: 2, errors: 2, "
                      "warnings: 0", text)
        self.assertIn("Ready to drive: 0 of 1 drivers", text)
        self.assertIn("D-2 (Test Driver): 2 errors, 0 warnings, "
                      "NOT READY", text)

    def test_json_output(self):
        path = write_csv(HEADER + row(medical="2026-12-10"))
        try:
            code, text = run_cli([path, "--as-of", "2026-11-18",
                                  "--json"])
        finally:
            os.unlink(path)
        self.assertEqual(code, 0)
        report = json.loads(text)
        self.assertEqual(report["drivers"], 1)
        self.assertEqual(report["warnings"], 1)
        self.assertEqual(report["findings"][0]["rule"],
                         "medical-expiring-soon")
        self.assertEqual(report["per_driver"][0]["status"], "READY")

    def test_out_writes_file(self):
        path = write_csv(HEADER + row())
        out_path = path + ".out"
        try:
            code, text = run_cli([path, "--as-of", "2026-11-18",
                                  "--out", out_path])
            self.assertEqual(code, 0)
            self.assertEqual(text, "")
            with open(out_path, encoding="utf-8") as handle:
                saved = handle.read()
            self.assertIn("All drivers clean.", saved)
        finally:
            os.unlink(path)
            if os.path.exists(out_path):
                os.unlink(out_path)

    def test_clean_file_message(self):
        path = write_csv(HEADER + row())
        try:
            code, text = run_cli([path, "--as-of", "2026-11-18"])
        finally:
            os.unlink(path)
        self.assertEqual(code, 0)
        self.assertIn("All drivers clean.", text)


class TestExitCodes(unittest.TestCase):
    """--check, --strict, and bad input exit codes."""

    def test_check_fails_on_errors(self):
        path = write_csv(HEADER
                         + row(cdl_expiry="2026-10-01"))
        try:
            code, _text = run_cli([path, "--as-of", "2026-11-18",
                                   "--check"])
        finally:
            os.unlink(path)
        self.assertEqual(code, 1)

    def test_check_passes_on_warnings_only(self):
        path = write_csv(HEADER + row(medical="2026-12-10"))
        try:
            code, _text = run_cli([path, "--as-of", "2026-11-18",
                                   "--check"])
        finally:
            os.unlink(path)
        self.assertEqual(code, 0)

    def test_strict_fails_on_warnings(self):
        path = write_csv(HEADER + row(medical="2026-12-10"))
        try:
            code, _text = run_cli([path, "--as-of", "2026-11-18",
                                   "--check", "--strict"])
        finally:
            os.unlink(path)
        self.assertEqual(code, 1)

    def test_strict_without_check_passes(self):
        path = write_csv(HEADER + row(medical="2026-12-10"))
        try:
            code, _text = run_cli([path, "--as-of", "2026-11-18",
                                   "--strict"])
        finally:
            os.unlink(path)
        self.assertEqual(code, 0)

    def test_check_passes_on_clean_file(self):
        path = write_csv(HEADER + row())
        try:
            code, _text = run_cli([path, "--as-of", "2026-11-18",
                                   "--check"])
        finally:
            os.unlink(path)
        self.assertEqual(code, 0)

    def test_bad_as_of(self):
        path = write_csv(HEADER + row())
        try:
            code, _text = run_cli([path, "--as-of", "not-a-date"])
        finally:
            os.unlink(path)
        self.assertEqual(code, 2)

    def test_negative_expiry_days(self):
        path = write_csv(HEADER + row())
        try:
            code, _text = run_cli([path, "--expiry-days", "-1"])
        finally:
            os.unlink(path)
        self.assertEqual(code, 2)

    def test_negative_mvr_days(self):
        path = write_csv(HEADER + row())
        try:
            code, _text = run_cli([path, "--mvr-days", "-1"])
        finally:
            os.unlink(path)
        self.assertEqual(code, 2)

    def test_missing_file_exits_2(self):
        code, _text = run_cli(["/nonexistent/drivers.csv"])
        self.assertEqual(code, 2)

    def test_version(self):
        self.assertEqual(doctor.__version__, "1.0.0")


if __name__ == "__main__":
    unittest.main()
