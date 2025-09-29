# schemas.py
from pydantic import BaseModel
from datetime import date
from typing import Optional

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
    photo: str   # ✅ mandatory
    device_id: Optional[str] = None  # ✅ new field for device binding

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

# -------------------- Attendance Analysis --------------------
class AttendanceAnalysisOut(BaseModel):
    roll: str
    name: str
    attendance_percentage: float

# ----------------- App Related Schemas -----------------
class StudentLogin(BaseModel):
    roll: str
    pin: str
    device_id: Optional[str] = None  # ✅ included for first device login

class ForgotPinRequest(BaseModel):
    roll: str
    dob: str  # YYYY-MM-DD
    new_pin: str

# ----------------- Student Profile -----------------
class StudentProfileOut(BaseModel):
    roll: str
    name: str
    branch: str
    dob: date
    issue_valid: str
    photo: str
    device_id: Optional[str] = None  # ✅ include device info in profile

# ----------------- Attendance Record -----------------
class AttendanceRecord(BaseModel):
    date: date
    time: str
    status: str

class AttendancePdfOut(BaseModel):
    class Config:
        orm_mode = True


# ---------------- Admin Reset Device ----------------
class ResetDeviceRequest(BaseModel):
    roll: str

