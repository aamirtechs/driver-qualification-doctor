# Good first issues

Seeded issues for new contributors. File each one on GitHub with
the `good first issue` and `help wanted` labels.

## 1. Add a per-driver missing-items table

Title: Show the missing DQ file items as a table

Description: After the per-driver readiness table, print a
short table of the drivers with missing DQ file items
(missing CDL number, medical certificate, MVR, annual
review, road test, or employer inquiry), sorted by
missing-item count, most first (driver id, name, missing
items as a comma list), so a dispatcher can work the
chase list top-down without reading every finding.
Drivers with no missing items are left out.

Difficulty: Easy

Acceptance criteria: the table appears in text output with
the correct rows for the sample file (D-107 missing road
test, D-108 missing employer inquiry, D-110 missing CDL
number, D-111 missing medical certificate, D-112 missing
MVR, and D-113 missing annual review, one item each, in
file order), and the drivers with no missing items are
left out; JSON output is unchanged; a test checks the
table rows.

## 2. Add a configurable annual review window

Title: Make the annual review cycle configurable

Description: Add a --review-days flag that sets how many
days after the annual review date the review counts as
overdue. The default stays at 365, the annual cycle
under 49 CFR 391.25. The flag only affects the
annual-review-overdue rule, not the MVR staleness
check, which keeps --mvr-days.

Difficulty: Easy

Acceptance criteria: with --review-days 500 the sample
file no longer flags D-106 (413.0 days old) and the
finding count drops by 1; the default run is unchanged;
README documents the flag.

## 3. Report the worst driver in the summary

Title: Print the driver with the most errors

Description: Add one line to the text summary naming the
driver with the most errors (driver id, name, error
count), so a dispatcher can see the worst DQ file at a
glance. When every driver has zero errors, the line is
omitted. On a tie, name the first driver in file order.

Difficulty: Easy

Acceptance criteria: the line appears for the sample file
naming D-114 (Nate Shaw) at 3 errors; it is absent for
the clean file, where no driver has errors; JSON output
is unchanged; a test checks both cases.

## 4. Warn on drivers with no hire date

Title: Warn on drivers with no recorded hire date

Description: Add a `missing-hire-date` warning for a
driver whose hire_date cell is empty, so a file with no
start date can be chased. The check only runs when the
hire_date column is present in the export. The employer
inquiry window is still skipped when the hire date is
missing.

Difficulty: Easy

Acceptance criteria: a driver with an empty hire date
gets the warning and still passes --check; the sample
file is unchanged (every row has a hire date); a test
covers both cases.
