

"""

Employee Attendance & Analytics API - STARTER



Run: uvicorn app.main:app --reload --port 8000

Env: MONGO_URI, MONGO_DB

"""



import os

from datetime import datetime, timedelta, timezone

from typing import Optional



from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, Query

from pydantic import BaseModel

from pymongo import MongoClient



load_dotenv()



client = MongoClient(

    os.getenv("MONGO_URI", "mongodb://localhost:27017")

)

db = client[os.getenv("MONGO_DB", "attendance_db")]



IST = timezone(timedelta(hours=5, minutes=30))



app = FastAPI(

    title="Employee Attendance & Analytics API",

    version="2.0.0",

)



# ---------------------------------------------------------------------------
# MongoDB indexes
# ---------------------------------------------------------------------------

@app.on_event("startup")
def create_indexes():
    # Each employee code must be unique.
    db.employees.create_index(
        [("emp_code", 1)],
        unique=True,
        name="uq_employee_code"
    )

    # Support department filtering and employee listing.
    db.employees.create_index(
        [("department", 1), ("emp_code", 1)],
        name="ix_employee_department_code"
    )

    # An employee can have only one attendance record per date.
    db.attendance_logs.create_index(
        [("emp_code", 1), ("date", 1)],
        unique=True,
        name="uq_attendance_employee_date"
    )

    # Support attendance date filtering and sorting.
    db.attendance_logs.create_index(
        [("date", -1), ("emp_code", 1)],
        name="ix_attendance_date_employee"
    )

    # Support status-based attendance queries.
    db.attendance_logs.create_index(
        [("status", 1), ("date", -1)],
        name="ix_attendance_status_date"
    )





# ---------------------------------------------------------------------------

# Helpers

# ---------------------------------------------------------------------------




def compute_late_minutes(
    punch_in: datetime,
    shift_start: str,
) -> int:
    punch_in_ist = punch_in.astimezone(IST)
    h, m = map(int, shift_start.split(":"))

    start = punch_in_ist.replace(
        hour=h,
        minute=m,
        second=0,
        microsecond=0,
    )

    # If punch-in is before shift start, there is no lateness.
    if punch_in_ist <= start:
        return 0

    minutes = int(
        (punch_in_ist - start).total_seconds() // 60
    )

    # Lateness is counted only when it exceeds 10 minutes.
    return minutes if minutes > 10 else 0







from decimal import Decimal, ROUND_HALF_UP


def compute_work_hours(
    punch_in: datetime, punch_out: datetime
) -> float:
    seconds = Decimal(
        str((punch_out - punch_in).total_seconds())
    )
    hours = seconds / Decimal("3600")

    return float(
        hours.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )
    )







def compute_overtime(
    punch_out: datetime,
    shift_end: str,
    date_str: str,
    shift_start: str = "09:30",
) -> int:
    end_h, end_m = map(int, shift_end.split(":"))
    start_h, start_m = map(int, shift_start.split(":"))

    start_minutes = start_h * 60 + start_m
    end_minutes = end_h * 60 + end_m

    # Determine whether the shift crosses midnight.
    overnight = end_minutes <= start_minutes

    shift_end_date = datetime.fromisoformat(date_str).date()

    if overnight:
        shift_end_date += timedelta(days=1)

    shift_end_ist = datetime(
        shift_end_date.year,
        shift_end_date.month,
        shift_end_date.day,
        end_h,
        end_m,
        tzinfo=IST,
    )

    punch_out_ist = punch_out.astimezone(IST)
    minutes = int(
        (punch_out_ist - shift_end_ist).total_seconds() // 60
    )

    # Overtime counts only when it reaches 30 whole minutes.
    return minutes if minutes >= 30 else 0






def normalize_page(page: int, page_size: int) -> int:

    if page < 1:

        raise HTTPException(422, "page must be at least 1")



    if page_size < 1 or page_size > 100:

        raise HTTPException(

            422, "page_size must be between 1 and 100"

        )



    return (page - 1) * page_size





# ---------------------------------------------------------------------------

# Models

# ---------------------------------------------------------------------------



class EmployeeIn(BaseModel):

    emp_code: str

    name: str

    email: str

    department: str

    shift_start: str = "09:30"

    shift_end: str = "18:30"

    joined_on: str





class PunchInIn(BaseModel):

    emp_code: str

    punched_at: Optional[int] = None

    status: str = "PRESENT"





# ---------------------------------------------------------------------------

# Health

# ---------------------------------------------------------------------------




@app.get("/health")
def health():
    try:
        db.command("ping")
        return {"status": "ok", "database": "connected"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable"
        )






# ---------------------------------------------------------------------------

# Employees

# ---------------------------------------------------------------------------



@app.post("/employees", status_code=201)

def create_employee(body: EmployeeIn):

    if db.employees.find_one({"emp_code": body.emp_code}):

        raise HTTPException(409, "emp_code already exists")



    doc = body.model_dump()

    doc["created_at"] = datetime.now(timezone.utc).replace(

        microsecond=0

    )



    db.employees.insert_one(doc)

    doc.pop("_id", None)



    return doc





@app.get("/employees")

def list_employees(

    department: Optional[str] = None,

    page: int = Query(1, ge=1),

    page_size: int = Query(20, ge=1, le=100),

):

    query = {}



    if department:

        query["department"] = department



    skip = normalize_page(page, page_size)

    total = db.employees.count_documents(query)



    items = list(

        db.employees.find(query, {"_id": 0})

        .sort("emp_code", 1)

        .skip(skip)

        .limit(page_size)

    )



    return {

        "items": items,

        "total": total,

        "page": page,

        "page_size": page_size,

    }





# ---------------------------------------------------------------------------

# Attendance: Punch in

# ---------------------------------------------------------------------------


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})

    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    if body.status not in {"PRESENT", "WFH", "ON_DUTY"}:
        raise HTTPException(status_code=422, detail="Invalid attendance status")

    if body.punched_at is None:
        ts = datetime.now(timezone.utc)
    else:
        if (
            isinstance(body.punched_at, bool)
            or not isinstance(body.punched_at, int)
            or not 100000000000 <= body.punched_at <= 4102444800000
        ):
            raise HTTPException(
                status_code=422,
                detail="Invalid punched_at timestamp",
            )

        ts = datetime.fromtimestamp(
            body.punched_at / 1000,
            tz=timezone.utc,
        )

    # Truncate the timestamp to whole seconds.
    ts = ts.replace(microsecond=0)

    # Determine the attendance date using Indian Standard Time.
    ist_ts = ts.astimezone(IST)
    date_str = ist_ts.date().isoformat()

    # Prevent duplicate attendance for the same employee and date.
    existing = db.attendance_logs.find_one(
        {
            "emp_code": body.emp_code,
            "date": date_str,
        }
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Already punched in for this date",
        )

    doc = {
        "emp_code": body.emp_code,
        "date": date_str,
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(
            ts, emp["shift_start"]
        ),
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }

    db.attendance_logs.insert_one(doc)

    # Return epoch milliseconds instead of datetime strings.
    doc.pop("_id", None)

    for field in ("punch_in", "punch_out"):
        value = doc.get(field)

        if value is not None:
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)

            doc[field] = int(value.timestamp() * 1000)

    return doc








# ---------------------------------------------------------------------------

# Attendance: List

# ---------------------------------------------------------------------------



@app.get("/attendance")

def list_attendance(

    emp_code: Optional[str] = None,

    date_from: Optional[str] = None,

    date_to: Optional[str] = None,

    status: Optional[str] = None,

    page: int = Query(1, ge=1),

    page_size: int = Query(20, ge=1, le=100),

):

    query = {}



    if emp_code:

        query["emp_code"] = emp_code



    if date_from or date_to:

        date_filter = {}



        if date_from:

            date_filter["$gte"] = date_from



        if date_to:

            date_filter["$lte"] = date_to



        query["date"] = date_filter



    if status:

        query["status"] = status



    skip = normalize_page(page, page_size)

    total = db.attendance_logs.count_documents(query)





    items = list(

        db.attendance_logs.find(query, {"_id": 0})

        .sort([("date", -1), ("emp_code", 1)])

        .skip(skip)

        .limit(page_size)

    )



    def to_epoch_ms(value):

        if value is None:

            return None

        if value.tzinfo is None:

            value = value.replace(tzinfo=timezone.utc)

        return int(value.timestamp() * 1000)



    for item in items:

        for field in ("punch_in", "punch_out"):

            item[field] = to_epoch_ms(item.get(field))



        for entry in item.get("history", []):

            entry["at"] = to_epoch_ms(entry["at"])





    return {

        "items": items,

        "total": total,

        "page": page,

        "page_size": page_size,

    }





# TODO: Implement the remaining assignment endpoints:

# POST  /attendance/punch-out

# PATCH /attendance/{emp_code}/{date}

# GET   /analytics/employees/{emp_code}/monthly

# GET   /analytics/departments/summary

# GET   /analytics/leaderboard/late

# GET   /analytics/departments/{department}/trend

# GET   /admin/explain/{endpoint}



# ---------------------------------------------------------------------------

# Attendance: Punch out

# ---------------------------------------------------------------------------



class PunchOutIn(BaseModel):

    emp_code: str

    punched_at: Optional[int] = None





@app.post("/attendance/punch-out")

def punch_out(body: PunchOutIn):

    emp = db.employees.find_one({"emp_code": body.emp_code})



    if emp is None:

        raise HTTPException(404, "Employee not found")



    # Use current UTC time when punched_at is omitted.

    if body.punched_at is None:

        ts = datetime.now(timezone.utc)

    else:

        if (

            isinstance(body.punched_at, bool)

            or not isinstance(body.punched_at, int)

            or not 100000000000 <= body.punched_at <= 4102444800000

        ):

            raise HTTPException(422, "Invalid punched_at timestamp")



        ts = datetime.fromtimestamp(

            body.punched_at / 1000,

            tz=timezone.utc,

        )



    # Truncate instants to whole seconds.

    ts = ts.replace(microsecond=0)



    # Find the latest punch-in at or before punch-out,

    # including records from the previous day for overnight shifts.

    record = db.attendance_logs.find_one(

        {

            "emp_code": body.emp_code,

            "punch_in": {"$ne": None, "$lte": ts},

        },

        sort=[("punch_in", -1)],

    )



    if record is None:

        raise HTTPException(404, "No punch-in found")



    punch_in_ts = record["punch_in"]



    # Ensure MongoDB's stored datetime is timezone-aware.

    if punch_in_ts.tzinfo is None:

        punch_in_ts = punch_in_ts.replace(tzinfo=timezone.utc)



    elapsed = (ts - punch_in_ts).total_seconds()



    if elapsed <= 0 or elapsed > 24 * 60 * 60:

        raise HTTPException(

            422,

            "Punch-out must be after punch-in and within 24 hours",

        )



    # Atomically update only if this record has not been punched out.

    work_hours = compute_work_hours(punch_in_ts, ts)



    # R3: Overtime is counted only when it reaches 30 whole minutes.

    h, m = map(int, emp["shift_end"].split(":"))

    shift_start_h, shift_start_m = map(int, emp["shift_start"].split(":"))



    start_minutes = shift_start_h * 60 + shift_start_m

    end_minutes = h * 60 + m

    overnight = end_minutes <= start_minutes



    shift_end_date = datetime.fromisoformat(record["date"]).date()

    punch_in_ist = punch_in_ts.astimezone(IST)



    if overnight and punch_in_ist.time() < datetime.min.replace(

        hour=h, minute=m

    ).time():

        shift_end_date += timedelta(days=1)



    shift_end_ts = datetime.combine(

        shift_end_date,

        datetime.min.replace(hour=h, minute=m).time(),

        tzinfo=IST,

    ).astimezone(timezone.utc)



    overtime_elapsed = int((ts - shift_end_ts).total_seconds() // 60)

    overtime_minutes = overtime_elapsed if overtime_elapsed >= 30 else 0



    half_day = work_hours < 4.50



    result = db.attendance_logs.update_one(

        {

            "_id": record["_id"],

            "punch_out": None,

        },

        {

            "$set": {

                "punch_out": ts,

                "work_hours": work_hours,

                "overtime_minutes": overtime_minutes,

                "half_day": half_day,

            }

        },

    )



    if result.modified_count != 1:

        raise HTTPException(409, "Record already punched out")



    updated = db.attendance_logs.find_one(

        {"_id": record["_id"]},

        {"_id": 0},

    )



    # Return instants as epoch milliseconds, as required by OpenAPI.

    for field in ("punch_in", "punch_out"):

        value = updated.get(field)

        if value is not None:

            if value.tzinfo is None:

                value = value.replace(tzinfo=timezone.utc)

            updated[field] = int(value.timestamp() * 1000)



    return updated



class AttendanceCorrectionIn(BaseModel):

    reason: str

    regularized_by: str

    status: Optional[str] = None

    punch_in: Optional[int] = None

    punch_out: Optional[int] = None





@app.patch("/attendance/{emp_code}/{date}")

def correct_attendance(emp_code: str, date: str, body: AttendanceCorrectionIn):

    from datetime import date as date_type



    # Validate the date in the URL.

    try:

        date_type.fromisoformat(date)

    except ValueError:

        raise HTTPException(422, "Invalid date; use YYYY-MM-DD")



    if not body.reason.strip() or not body.regularized_by.strip():

        raise HTTPException(422, "reason and regularized_by are required")



    emp = db.employees.find_one({"emp_code": emp_code})

    if emp is None:

        raise HTTPException(404, "Employee not found")



    record = db.attendance_logs.find_one(

        {"emp_code": emp_code, "date": date}

    )

    if record is None:

        raise HTTPException(404, "Attendance record not found")



    allowed_statuses = {"PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"}

    fields_set = body.model_fields_set



    new_status = body.status if "status" in fields_set else record["status"]

    if new_status not in allowed_statuses:

        raise HTTPException(422, "Invalid attendance status")



    if new_status in {"ABSENT", "LEAVE"}:

        if "punch_in" in fields_set or "punch_out" in fields_set:

            raise HTTPException(

                422, "Do not supply punch times for ABSENT or LEAVE"

            )

        new_in = None

        new_out = None

    else:

        old_in = record.get("punch_in")

        old_out = record.get("punch_out")



        def parse_timestamp(value):

            if value is None:

                return None

            if (

                isinstance(value, bool)

                or not isinstance(value, int)

                or not 100000000000 <= value <= 4102444800000

            ):

                raise HTTPException(422, "Invalid epoch-millisecond timestamp")

            return datetime.fromtimestamp(

                value / 1000, tz=timezone.utc

            ).replace(microsecond=0)



        new_in = (

            parse_timestamp(body.punch_in)

            if "punch_in" in fields_set

            else old_in

        )

        new_out = (

            parse_timestamp(body.punch_out)

            if "punch_out" in fields_set

            else old_out

        )



        if new_in is None:

            raise HTTPException(422, "Presence status requires punch_in")



        if new_in.tzinfo is None:

            new_in = new_in.replace(tzinfo=timezone.utc)



        # Attendance date is based on the punch-in's IST calendar date.

        if new_in.astimezone(IST).date().isoformat() != date:

            raise HTTPException(422, "punch_in does not match attendance date")



        if new_out is not None:

            if new_out.tzinfo is None:

                new_out = new_out.replace(tzinfo=timezone.utc)

            seconds = (new_out - new_in).total_seconds()

            if seconds <= 0 or seconds > 86400:

                raise HTTPException(

                    422, "punch_out must be after punch_in and within 24 hours"

                )



    def as_ms(value):

        if value is None:

            return None

        if value.tzinfo is None:

            value = value.replace(tzinfo=timezone.utc)

        return int(value.timestamp() * 1000)



    changes = {}



    for field, old_value, new_value in [

        ("status", record.get("status"), new_status),

        ("punch_in", record.get("punch_in"), new_in),

        ("punch_out", record.get("punch_out"), new_out),

    ]:

        old_display = as_ms(old_value) if field != "status" else old_value

        new_display = as_ms(new_value) if field != "status" else new_value

        if old_display != new_display:

            changes[field] = {"from": old_display, "to": new_display}



    if not changes:

        raise HTTPException(422, "Correction does not change the record")



    late_minutes = 0

    work_hours = None

    overtime_minutes = 0

    half_day = False



    if new_status not in {"ABSENT", "LEAVE"}:

        late_minutes = compute_late_minutes(new_in, emp["shift_start"])



        if new_out is not None:

            work_hours = compute_work_hours(new_in, new_out)

            half_day = work_hours < 4.50



            start_h, start_m = map(int, emp["shift_start"].split(":"))

            end_h, end_m = map(int, emp["shift_end"].split(":"))

            start_minutes = start_h * 60 + start_m

            end_minutes = end_h * 60 + end_m

            overnight = end_minutes <= start_minutes



            shift_end_date = date_type.fromisoformat(date)

            if overnight:

                shift_end_date += timedelta(days=1)



            shift_end_ist = datetime(

                shift_end_date.year,

                shift_end_date.month,

                shift_end_date.day,

                end_h,

                end_m,

                tzinfo=IST,

            )

            elapsed_minutes = int(

                (new_out - shift_end_ist.astimezone(timezone.utc))

                .total_seconds() // 60

            )

            overtime_minutes = (

                elapsed_minutes if elapsed_minutes >= 30 else 0

            )



    history_entry = {

        "at": datetime.now(timezone.utc).replace(microsecond=0),

        "by": body.regularized_by,

        "reason": body.reason,

        "changes": changes,

    }



    old_history = record.get("history", [])

    result = db.attendance_logs.update_one(

        {

            "_id": record["_id"],

            "history": old_history,

        },

        {

            "$set": {

                "status": new_status,

                "punch_in": new_in,

                "punch_out": new_out,

                "work_hours": work_hours,

                "late_minutes": late_minutes,

                "overtime_minutes": overtime_minutes,

                "half_day": half_day,

            },

            "$push": {"history": history_entry},

        },

    )



    if result.modified_count != 1:

        raise HTTPException(409, "Record changed concurrently; retry correction")



    updated = db.attendance_logs.find_one(

        {"_id": record["_id"]}, {"_id": 0}

    )



    for field in ("punch_in", "punch_out"):

        updated[field] = as_ms(updated.get(field))



    for entry in updated.get("history", []):

        entry["at"] = as_ms(entry["at"])



    return updated

# ---------------------------------------------------------------------------
# Monthly employee attendance analytics
# ---------------------------------------------------------------------------

@app.get("/analytics/employees/{emp_code}/monthly")
def monthly_employee_analytics(
    emp_code: str,
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
):
    from calendar import monthrange
    from datetime import date as date_type

    employee = db.employees.find_one({"emp_code": emp_code})

    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found"
        )

    month_start = date_type(year, month, 1).isoformat()
    month_end = date_type(
        year, month, monthrange(year, month)[1]
    ).isoformat()

    records = list(
        db.attendance_logs.find(
            {
                "emp_code": emp_code,
                "date": {
                    "$gte": month_start,
                    "$lte": month_end
                }
            },
            {"_id": 0}
        ).sort("date", 1)
    )

    present_statuses = {"PRESENT", "WFH", "ON_DUTY"}
    present_days = sum(
        1
        for record in records
        if record.get("status") in present_statuses
        and date_type.fromisoformat(record["date"]).weekday() < 5
    )

    return {
        "emp_code": emp_code,
        "name": employee["name"],
        "department": employee["department"],
        "year": year,
        "month": month,
        "total_records": len(records),
        "present_days": present_days,
        "records": records
    }

# ---------------------------------------------------------------------------
# Department summary analytics
# ---------------------------------------------------------------------------

@app.get("/analytics/departments/summary")
def department_summary(
    date_from: str = Query(..., description="Start date: YYYY-MM-DD"),
    date_to: str = Query(..., description="End date: YYYY-MM-DD"),
):
    from datetime import date as date_type

    try:
        start_date = date_type.fromisoformat(date_from)
        end_date = date_type.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Dates must use YYYY-MM-DD format"
        )

    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="date_from must not be after date_to"
        )

    pipeline = [
        {
            "$match": {
                "date": {
                    "$gte": date_from,
                    "$lte": date_to
                }
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "records": {"$push": "$$ROOT"}
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "employee"
            }
        },
        {"$unwind": "$employee"},
        {
            "$unwind": "$records"
        },
        {
            "$group": {
                "_id": "$employee.department",
                "total_records": {"$sum": 1},
                "present_records": {
                    "$sum": {
                        "$cond": [
                            {
                                "$in": [
                                    "$records.status",
                                    ["PRESENT", "WFH", "ON_DUTY"]
                                ]
                            },
                            1,
                            0
                        ]
                    }
                },
                "late_minutes": {
                    "$sum": {"$ifNull": ["$records.late_minutes", 0]}
                },
                "overtime_minutes": {
                    "$sum": {"$ifNull": ["$records.overtime_minutes", 0]}
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "department": "$_id",
                "total_records": 1,
                "present_records": 1,
                "late_minutes": 1,
                "overtime_minutes": 1
            }
        },
        {"$sort": {"department": 1}}
    ]

    results = list(db.attendance_logs.aggregate(pipeline))

    return {
        "date_from": date_from,
        "date_to": date_to,
        "departments": results
    }

# ---------------------------------------------------------------------------
# Late arrival leaderboard
# ---------------------------------------------------------------------------

@app.get("/analytics/leaderboard/late")
def late_leaderboard(
    date_from: str = Query(..., description="Start date: YYYY-MM-DD"),
    date_to: str = Query(..., description="End date: YYYY-MM-DD"),
    limit: int = Query(10, ge=1, le=100),
):
    from datetime import date as date_type

    try:
        start_date = date_type.fromisoformat(date_from)
        end_date = date_type.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Dates must use YYYY-MM-DD format"
        )

    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="date_from must not be after date_to"
        )

    pipeline = [
        {
            "$match": {
                "date": {
                    "$gte": date_from,
                    "$lte": date_to
                }
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "total_late_minutes": {
                    "$sum": {"$ifNull": ["$late_minutes", 0]}
                },
                "late_days": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$late_minutes", 0]},
                            1,
                            0
                        ]
                    }
                }
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "employee"
            }
        },
        {"$unwind": "$employee"},
        {
            "$project": {
                "_id": 0,
                "emp_code": "$_id",
                "name": "$employee.name",
                "department": "$employee.department",
                "total_late_minutes": 1,
                "late_days": 1
            }
        },
        {
            "$sort": {
                "total_late_minutes": -1,
                "emp_code": 1
            }
        },
        {"$limit": limit}
    ]

    results = list(db.attendance_logs.aggregate(pipeline))

    return {
        "date_from": date_from,
        "date_to": date_to,
        "items": results
    }

# ---------------------------------------------------------------------------
# Department attendance trend
# ---------------------------------------------------------------------------

@app.get("/analytics/departments/{department}/trend")

def department_attendance_trend(
    department: str,
    date_from: str = Query(..., description="Start date: YYYY-MM-DD"),
    date_to: str = Query(..., description="End date: YYYY-MM-DD"),
):
    from datetime import date as date_type

    try:
        start_date = date_type.fromisoformat(date_from)
        end_date = date_type.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Dates must use YYYY-MM-DD format",
        )

    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="date_from must not be after date_to",
        )

    pipeline = [
        {
            "$lookup": {
                "from": "employees",
                "localField": "emp_code",
                "foreignField": "emp_code",
                "as": "employee",
            }
        },
        {"$unwind": "$employee"},
        {
            "$match": {
                "employee.department": department,
                "date": {"$gte": date_from, "$lte": date_to},
            }
        },
        {
            "$group": {
                "_id": "$date",
                "total_records": {"$sum": 1},
                "present_records": {
                    "$sum": {
                        "$cond": [
                            {
                                "$in": [
                                    "$status",
                                    ["PRESENT", "WFH", "ON_DUTY"],
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
            }
        },
        {"$sort": {"_id": 1}},
        
        {
            "$set": {
                "_date_value": {
                    "$dateFromString": {
                        "dateString": "$_id",
                        "format": "%Y-%m-%d",
                    }
                }
            }
        },
        {
            "$densify": {
                "field": "_date_value",
                "range": {
                    "step": 1,
                    "unit": "day",
                    "bounds": [
                        datetime.combine(start_date, datetime.min.time()),
    datetime.combine(
        end_date + timedelta(days=1),
        datetime.min.time(),
    ),
                    ],
                },
            }
        },

        {
            "$set": {
                "total_records": {"$ifNull": ["$total_records", 0]},
                "present_records": {"$ifNull": ["$present_records", 0]},
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"_date_value": 1},
                "output": {
                    "moving_average_7_days": {
                        "$avg": "$present_records",
                        "window": {"documents": [-6, 0]},
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$_date_value"
                        
                    }
                },
                "total_records": 1,
                "present_records": 1,
                "moving_average_7_days": {
                    "$round": ["$moving_average_7_days", 2]
                },
            }
        },
        {"$sort": {"date": 1}},
    ]

    try:
        results = list(db.attendance_logs.aggregate(pipeline))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Trend aggregation failed: {str(exc)}",
        )

    return {
        "department": department,
        "date_from": date_from,
        "date_to": date_to,
        "trend": results,
    }


# ---------------------------------------------------------------------------
# Admin query execution explain
# ---------------------------------------------------------------------------

@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: str,
    emp_code: Optional[str] = None,
    department: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    year: Optional[int] = Query(None, ge=2000, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    limit: int = Query(10, ge=1, le=100),
):
    from calendar import monthrange
    from datetime import date as date_type

    try:
        # 1. Attendance list: same filters and pagination as /attendance.
        if endpoint == "attendance_list":
            query = {}

            if emp_code:
                query["emp_code"] = emp_code

            if status:
                query["status"] = status

            if date_from or date_to:
                date_filter = {}
                if date_from:
                    date_type.fromisoformat(date_from)
                    date_filter["$gte"] = date_from
                if date_to:
                    date_type.fromisoformat(date_to)
                    date_filter["$lte"] = date_to
                query["date"] = date_filter

            skip = normalize_page(page, page_size)

            explanation = db.command(
                "explain",
                {
                    "find": "attendance_logs",
                    "filter": query,
                    "sort": {"date": -1, "emp_code": 1},
                    "skip": skip,
                    "limit": page_size,
                },
                verbosity="executionStats",
            )

        # 2. Employee monthly attendance.
        elif endpoint == "employee_monthly":
            if not emp_code or year is None or month is None:
                raise HTTPException(
                    status_code=422,
                    detail="Provide emp_code, year and month",
                )

            month_start = date_type(year, month, 1).isoformat()
            month_end = date_type(
                year, month, monthrange(year, month)[1]
            ).isoformat()

            explanation = db.command(
                "explain",
                {
                    "find": "attendance_logs",
                    "filter": {
                        "emp_code": emp_code,
                        "date": {
                            "$gte": month_start,
                            "$lte": month_end,
                        },
                    },
                    "sort": {"date": 1},
                },
                verbosity="executionStats",
            )

        # Shared date validation for the remaining analytics.
        elif endpoint in {
            "department_summary",
            "late_leaderboard",
            "department_trend",
        }:
            if not date_from or not date_to:
                raise HTTPException(
                    status_code=422,
                    detail="Provide date_from and date_to",
                )

            start_date = date_type.fromisoformat(date_from)
            end_date = date_type.fromisoformat(date_to)

            if start_date > end_date:
                raise HTTPException(
                    status_code=422,
                    detail="date_from must not be after date_to",
                )

            # 3. Department summary.
            if endpoint == "department_summary":
                pipeline = [
                    {
                        "$match": {
                            "date": {
                                "$gte": date_from,
                                "$lte": date_to,
                            }
                        }
                    },
                    {
                        "$group": {
                            "_id": "$emp_code",
                            "records": {"$push": "$$ROOT"},
                        }
                    },
                    {
                        "$lookup": {
                            "from": "employees",
                            "localField": "_id",
                            "foreignField": "emp_code",
                            "as": "employee",
                        }
                    },
                    {"$unwind": "$employee"},
                    {"$unwind": "$records"},
                    {
                        "$group": {
                            "_id": "$employee.department",
                            "total_records": {"$sum": 1},
                            "present_records": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$in": [
                                                "$records.status",
                                                [
                                                    "PRESENT",
                                                    "WFH",
                                                    "ON_DUTY",
                                                ],
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "late_minutes": {
                                "$sum": {
                                    "$ifNull": [
                                        "$records.late_minutes", 0
                                    ]
                                }
                            },
                            "overtime_minutes": {
                                "$sum": {
                                    "$ifNull": [
                                        "$records.overtime_minutes", 0
                                    ]
                                }
                            },
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "department": "$_id",
                            "total_records": 1,
                            "present_records": 1,
                            "late_minutes": 1,
                            "overtime_minutes": 1,
                        }
                    },
                    {"$sort": {"department": 1}},
                ]

                explanation = db.command(
                    "explain",
                    {
                        "aggregate": "attendance_logs",
                        "pipeline": pipeline,
                        "cursor": {},
                    },
                    verbosity="executionStats",
                )

            # 4. Late-arrival leaderboard.
            elif endpoint == "late_leaderboard":
                pipeline = [
                    {
                        "$match": {
                            "date": {
                                "$gte": date_from,
                                "$lte": date_to,
                            }
                        }
                    },
                    {
                        "$group": {
                            "_id": "$emp_code",
                            "total_late_minutes": {
                                "$sum": {
                                    "$ifNull": ["$late_minutes", 0]
                                }
                            },
                            "late_days": {
                                "$sum": {
                                    "$cond": [
                                        {"$gt": ["$late_minutes", 0]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    },
                    {
                        "$lookup": {
                            "from": "employees",
                            "localField": "_id",
                            "foreignField": "emp_code",
                            "as": "employee",
                        }
                    },
                    {"$unwind": "$employee"},
                    {
                        "$project": {
                            "_id": 0,
                            "emp_code": "$_id",
                            "name": "$employee.name",
                            "department": "$employee.department",
                            "total_late_minutes": 1,
                            "late_days": 1,
                        }
                    },
                    {
                        "$sort": {
                            "total_late_minutes": -1,
                            "emp_code": 1,
                        }
                    },
                    {"$limit": limit},
                ]

                explanation = db.command(
                    "explain",
                    {
                        "aggregate": "attendance_logs",
                        "pipeline": pipeline,
                        "cursor": {},
                    },
                    verbosity="executionStats",
                )

            # 5. Department attendance trend.
            else:
                if not department:
                    raise HTTPException(
                        status_code=422,
                        detail="Provide department",
                    )

                pipeline = [
                    {
                        "$lookup": {
                            "from": "employees",
                            "localField": "emp_code",
                            "foreignField": "emp_code",
                            "as": "employee",
                        }
                    },
                    {"$unwind": "$employee"},
                    {
                        "$match": {
                            "employee.department": department,
                            "date": {
                                "$gte": date_from,
                                "$lte": date_to,
                            },
                        }
                    },
                    {
                        "$group": {
                            "_id": "$date",
                            "total_records": {"$sum": 1},
                            "present_records": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$in": [
                                                "$status",
                                                [
                                                    "PRESENT",
                                                    "WFH",
                                                    "ON_DUTY",
                                                ],
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                        }
                    },
                    {"$sort": {"_id": 1}},
                    {
                        "$set": {
                            "_date_value": {
                                "$dateFromString": {
                                    "dateString": "$_id",
                                    "format": "%Y-%m-%d",
                                }
                            }
                        }
                    },
                    {
                        "$densify": {
                            "field": "_date_value",
                            "range": {
                                "step": 1,
                                "unit": "day",
                                "bounds": [
                                    datetime.combine(
                                        start_date, datetime.min.time()
                                    ),
                                    datetime.combine(
                                        end_date + timedelta(days=1),
                                        datetime.min.time(),
                                    ),
                                ],
                            },
                        }
                    },
                    {
                        "$set": {
                            "total_records": {
                                "$ifNull": ["$total_records", 0]
                            },
                            "present_records": {
                                "$ifNull": ["$present_records", 0]
                            },
                        }
                    },
                    {
                        "$setWindowFields": {
                            "sortBy": {"_date_value": 1},
                            "output": {
                                "moving_average_7_days": {
                                    "$avg": "$present_records",
                                    "window": {"documents": [-6, 0]},
                                }
                            },
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "date": {
                                "$dateToString": {
                                    "format": "%Y-%m-%d",
                                    "date": "$_date_value",
                                }
                            },
                            "total_records": 1,
                            "present_records": 1,
                            "moving_average_7_days": {
                                "$round": ["$moving_average_7_days", 2]
                            },
                        }
                    },
                    {"$sort": {"date": 1}},
                ]

                explanation = db.command(
                    "explain",
                    {
                        "aggregate": "attendance_logs",
                        "pipeline": pipeline,
                        "cursor": {},
                    },
                    verbosity="executionStats",
                )

        # Preserve the two names supported by your original function.
        elif endpoint == "employees":
            explanation = db.command(
                "explain",
                {
                    "find": "employees",
                    "filter": {},
                    "sort": {"emp_code": 1},
                },
                verbosity="executionStats",
            )

        elif endpoint == "attendance":
            explanation = db.command(
                "explain",
                {
                    "find": "attendance_logs",
                    "filter": {},
                    "sort": {"date": -1, "emp_code": 1},
                },
                verbosity="executionStats",
            )

        else:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Unsupported endpoint. Use attendance_list, "
                    "employee_monthly, department_summary, "
                    "late_leaderboard, department_trend, "
                    "employees or attendance."
                ),
            )

    except HTTPException:
        raise
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid query parameter: {str(exc)}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not explain query: {str(exc)}",
        )

    
    if "stages" in explanation:
        stages = explanation.get("stages", [])
        cursor_stage = next(
            (stage.get("$cursor", {}) for stage in stages if "$cursor" in stage),
            {},
        )

        execution_stats = cursor_stage.get("executionStats", {})
        query_planner = explanation
    else:
        execution_stats = explanation.get("executionStats", {})
        query_planner = explanation.get("queryPlanner", {})

    return {
        "endpoint": endpoint,
        "executionStats": execution_stats,
        "queryPlanner": query_planner,
    }
