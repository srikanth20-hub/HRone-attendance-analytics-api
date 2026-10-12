# REVIEW.md

List every defect found in the starter `app/main.py`, including helpers and endpoints.

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | `compute_late_minutes()` | Verify the handling of shift start times and the 10-minute grace period against the business rules. | Test punches before shift start, exactly at shift start, and 10 and 11 minutes late. | Apply the documented lateness rule and test the boundary cases. |
| 2 | `compute_work_hours()` | Verify elapsed-time calculation and rounding behaviour. | Test short shifts, fractional hours, and timestamps with seconds. | Use the required rounding method and validate elapsed time. |
| 3 | `compute_overtime()` | Verify overtime calculation for overnight shifts and the required minimum overtime threshold. | Test a normal shift, an overnight shift, and punches just below and above the threshold. | Calculate the correct shift-end instant and apply the specified threshold. |
| 4 | Employee input validation | Verify validation of employee codes, email addresses, shift times, and joining dates. | Submit malformed times, invalid dates, and missing or invalid values. | Add validation according to the API contract. |
| 5 | `normalize_page()` and list endpoints | Verify pagination boundaries and maximum page size. | Test page 0, page size 0, and page size above 100. | Return HTTP 422 for invalid pagination values. |
| 6 | Employee creation | Verify duplicate employee-code handling. | Create the same employee code twice. | Enforce uniqueness and return HTTP 409 for duplicates. |
| 7 | Attendance punch-in | Verify employee existence, valid statuses, and attendance-day calculation. | Test an unknown employee, invalid status, and a punch around midnight. | Apply the contract's validation and attendance-day rules. |
| 8 | Attendance punch-in concurrency | Verify that simultaneous punch-ins cannot create duplicate daily records. | Send parallel punch-in requests for the same employee and date. | Use a unique compound index and handle duplicate-key conflicts. |
| 9 | Attendance punch-out | Verify missing records, invalid timestamps, and repeated punch-outs. | Test an unknown employee, punch-out before punch-in, and two concurrent punch-outs. | Validate timestamps and update only a record that has not already been punched out. |
| 10 | Attendance correction | Verify that corrections recalculate derived fields and preserve audit history. | Correct a record and inspect its calculated fields and history. | Recalculate affected values and append an audit entry atomically. |
| 11 | Attendance correction concurrency | Verify that concurrent corrections do not silently overwrite history. | Submit two corrections against the same record concurrently. | Use an atomic conditional update and return a conflict when the record has changed. |
| 12 | Monthly employee analytics | Verify aggregation boundaries and missing-employee behaviour. | Test an unknown employee, a month with no records, and records on month boundaries. | Match the documented response and aggregation rules. |
| 13 | Department summary | Verify department headcount, employees without logs, and joining-date rules. | Test a department containing employees with no attendance logs and a mid-month joiner. | Calculate headcount and attendance metrics according to the contract. |
| 14 | Late-arrival leaderboard | Verify ranking ties and the limit parameter. | Test tied lateness values, including a tie at the requested limit. | Use ranking semantics that preserve ties and sort tied employees by employee code. |
| 15 | Department trend | Verify missing-day filling, date bounds, sorting, and moving-average calculation. | Test a range containing weekdays, weekends, and days without records. | Fill every calendar day, sort by date, and calculate the required moving average in MongoDB. |
| 16 | Admin explain endpoint | Verify supported endpoint names and index usage. | Request each supported explain target and inspect execution statistics. | Build the explain query using the same filters, sort, and pagination as the corresponding endpoint. |
| 17 | Database indexes | Verify index creation and support for list and analytics queries. | Start the application and inspect explain output for index scans and collection scans. | Create the required indexes idempotently at startup. |

## Checked and not considered defects

- The health endpoint successfully checks MongoDB connectivity and returns an error response when MongoDB is unavailable.
- Pagination validation rejects invalid page numbers and page sizes outside the permitted range.
- The API uses employee codes to identify employees rather than exposing MongoDB internal IDs.
- The final findings must be checked against the original starter code, the actual fixes, and test results before submission.
