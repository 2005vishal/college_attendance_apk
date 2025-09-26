# schemas.py
from pydantic import BaseModel
from datetime import date
from typing import Optional

from pydantic.v1.schema import schema


# ----------------- Auth -----------------
class AdminLogin(BaseModel):
    userId: str
    password: str


# ----------------- Student -----------------

class StudentBase(BaseModel):
    roll: str
    name: str
    branch: str
    dob: date
    issue_valid: str
    pin: str
    photo: str   # ✅ now mandatory (no None, no default)

class StudentCreate(StudentBase):
    pass

class StudentResponse(StudentBase):
    class Config:
        orm_mode = True


# ----------------- Attendance -----------------
class AttendanceBase(BaseModel):
    roll: str
    date: date
    time: str
    status: str


class AttendanceOut(AttendanceBase):
    class Config:
        orm_mode = True



class MarkAttendance(BaseModel):
    roll: str
    date: date
    time: str

# -------------------- ATTENDANCE ANALYSIS --------------------
class AttendanceAnalysisOut(BaseModel):
    roll: str
    name: str
    attendance_percentage: float

# ----------------app relate schema------------------------------
class StudentLogin(BaseModel):
    roll: str
    pin: str

class ForgotPinRequest(BaseModel):
    roll: str
    dob: str  # YYYY-MM-DD
    new_pin: str

# ----------------- Student -----------------
class StudentProfileOut(BaseModel):
    roll: str
    name: str
    branch: str
    dob: date
    issue_valid: str
    photo: str
class AttendanceRecord(BaseModel):
    date: date
    time: str
    status: str

class AttendancePdfOut(BaseModel):
    class Config:
        orm_mode = True
