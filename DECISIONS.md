# DECISIONS.md

### 1. Indexes

I created a unique index on `employees.emp_code` to prevent duplicate employee codes. I also created a compound index on employee department and employee code to support department filtering and sorting. For attendance, I created a unique compound index on `emp_code` and `date` to guarantee at most one daily record per employee. Additional indexes on date and employee code, and on status and date, support attendance listing and analytics. I would evaluate each index against actual query plans because unnecessary indexes increase write costs.

### 2. Punch-in race

When two identical punch-in requests arrive together, both may initially check the database. The unique compound index is the final protection against duplicate records. One request can create the record and return HTTP 201; the competing request should receive HTTP 409 when MongoDB rejects its duplicate insert.

### 3. Ties

The leaderboard should preserve equal ranks for employees with the same late-minute total. If a tie reaches the requested limit, tied employees should remain included, ordered by employee code. The next rank should be skipped, as required by the assignment.

### 4. Headcount

The department summary must start from employees and join their attendance records, rather than starting only from attendance logs. This allows eligible employees with zero logs to be included in headcount.

### 5. Scaling

For 100 times more data, I would inspect execution plans, benchmark queries, optimise indexes, and consider partitioning or archiving older attendance records if measurements justified it.

### 6. Department trend

The department trend is calculated using MongoDB aggregation rather than calculating results in Python. Missing calendar dates are filled so the response includes one row per day in the requested range, including weekends and days without attendance records. The seven-day moving average uses the current day and up to the previous six days in the returned date sequence.