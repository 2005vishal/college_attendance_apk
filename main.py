from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query, Header,Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
import os
import cloudinary.uploader
from typing import Optional,List
from sqlalchemy import func

from database import Base, engine, SessionLocal
from models import Student, Attendance, Admin
from schemas import StudentCreate, StudentResponse, AttendanceOut, AdminLogin, MarkAttendance
from dotenv import load_dotenv
from auth import create_access_token, decode_access_token, verify_password, get_password_hash
from schemas import StudentLogin, StudentProfileOut, AttendanceRecord, ForgotPinRequest
from fastapi import APIRouter, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import RedirectResponse


# ----------------- Load environment variables -----------------
load_dotenv()

MARK_ABSENT_API_KEY = os.getenv("MARK_ABSENT_API_KEY")

# ----------------- Configure Cloudinary -----------------
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ----------------- Initialize FastAPI -----------------
app = FastAPI(title="College Admin Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- Dependency -----------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------- API Key Verification -----------------
def verify_api_key(api_key: str = Header(...)):
    if api_key != MARK_ABSENT_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ----------------- Auth APIs -----------------
@app.post("/auth/login")
def login(data: AdminLogin, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.user_id == data.userId.lower()).first()
    if not admin or not verify_password(data.password, admin.password_hash):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_access_token({"sub": admin.user_id})
    return {"token": token}

@app.post("/auth/verify-answers")
def verify_answers(userId: str = Form(...), answer1: str = Form(...), answer2: str = Form(...), db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.user_id == userId.lower()).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    if admin.answer1 != answer1 or admin.answer2 != answer2:
        raise HTTPException(status_code=400, detail="Wrong answers")
    return {"ok": True}

@app.post("/auth/reset-password")
def reset_password(userId: str = Form(...), newPassword: str = Form(...), db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.user_id == userId.lower()).first()
    if not admin:
        raise HTTPException(status_code=404, detail="Admin not found")
    admin.password_hash = get_password_hash(newPassword)
    db.commit()
    return {"ok": True}


# ----------------- Student APIs -----------------
@app.post("/students/", response_model=StudentResponse)
async def create_student(
    roll: str = Form(...),
    name: str = Form(...),
    branch: str = Form(...),
    dob: date = Form(...),
    issue_valid: str = Form(...),
    pin: str = Form(...),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    roll = roll.upper()
    name = " ".join(word.capitalize() for word in name.split())
    db_student = db.query(Student).filter(Student.roll == roll).first()
    if db_student:
        raise HTTPException(status_code=400, detail="Roll number already exists")
    if photo:
        upload_result = cloudinary.uploader.upload(photo.file, folder="students")
        photo_url = upload_result.get("secure_url")
        public_id = upload_result.get("public_id")
    else:
        photo_url = None
        public_id = None
    new_student = Student(
        roll=roll,
        name=name,
        branch=branch,
        dob=dob,
        issue_valid=issue_valid,
        pin=get_password_hash(pin),
        photo=photo_url,
        photo_public_id=public_id
    )
    db.add(new_student)
    db.commit()
    db.refresh(new_student)
    return new_student


@app.get("/students", response_model=list[StudentResponse])
def list_students(
    name: str = Query(None),
    branch: str = Query(None),
    dob: str = Query(None),
    roll: str = Query(None),
    lastYears: int = Query(None),
    page: int = 1,
    pageSize: int = 100,
    db: Session = Depends(get_db)
):
    q = db.query(Student)
    if name:
        q = q.filter(Student.name.ilike(f"%{name}%"))
    if branch:
        q = q.filter(Student.branch == branch)
    if dob:
        dob_dt = datetime.strptime(dob, "%Y-%m-%d").date()
        q = q.filter(Student.dob == dob_dt)
    if roll:
        q = q.filter(Student.roll == roll.upper())
    if lastYears:
        cutoff = date.today() - timedelta(days=365 * lastYears)
        q = q.filter(Student.issue_date >= cutoff)
    students = q.offset((page - 1) * pageSize).limit(pageSize).all()
    return students
# ---------------------------------get student detail--------------------
@app.get("/students/{roll}", response_model=StudentResponse)
def get_student(roll: str, db: Session = Depends(get_db)):
    s = db.query(Student).filter(Student.roll == roll.upper()).first()
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    return s
# --------------------update student detail-----------------
@app.put("/students/{roll}", response_model=StudentResponse)
def update_student(
    roll: str,
    name: Optional[str] = Form(None),
    dob: Optional[str] = Form(None),
    issue_valid: Optional[str] = Form(None),
    branch: Optional[str] = Form(None),
    pin: Optional[str] = Form(None),
    photo: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    s = db.query(Student).filter(Student.roll == roll.upper()).first()
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")

    # ---------------- Upload photo to Cloudinary ----------------
    if photo:
        # Delete old photo if exists
        if s.photo_public_id:
            try:
                cloudinary.uploader.destroy(s.photo_public_id)
            except Exception as e:
                print(f"Failed to delete old image: {e}")

        # Upload new photo
        upload_result = cloudinary.uploader.upload(photo.file, folder="students")
        s.photo = upload_result.get("secure_url")
        s.photo_public_id = upload_result.get("public_id")

    # ---------------- Update other fields ----------------
    if name is not None and name.strip() != "":
        s.name = " ".join(word.capitalize() for word in name.split())

    if dob is not None and dob.strip() != "":
        s.dob = datetime.strptime(dob, "%Y-%m-%d").date()

    if issue_valid is not None and issue_valid.strip() != "":
        s.issue_valid = issue_valid

    if branch is not None and branch.strip() != "":
        s.branch = branch

    if pin is not None and pin.strip() != "":
        if len(pin) != 4 or not pin.isdigit():
            raise HTTPException(status_code=400, detail="PIN must be exactly 4 digits")
        s.pin = get_password_hash(pin)

    db.commit()
    db.refresh(s)
    return s
#---------------------delete student--------------------------
@app.delete("/students/{roll}")
def delete_student(roll: str, db: Session = Depends(get_db)):
    s = db.query(Student).filter(Student.roll == roll.upper()).first()
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")

    if s.photo_public_id:
        try:
            cloudinary.uploader.destroy(s.photo_public_id)
        except Exception as e:
            print(f"Failed to delete image from Cloudinary: {e}")

    db.query(Attendance).filter(Attendance.roll == roll.upper()).delete(synchronize_session=False)
    db.delete(s)
    db.commit()
    return {"ok": True}


# ----------------- Attendance APIs -----------------
@app.post("/attendance/mark")
def mark_attendance(attendance_data: MarkAttendance, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.roll == attendance_data.roll).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    today = date.today()
    if attendance_data.date != today:
        raise HTTPException(status_code=400, detail="Invalid date")
    record = db.query(Attendance).filter(Attendance.roll == attendance_data.roll, Attendance.date == today).first()
    if record:
        return {"message": "Attendance already marked"}
    new_record = Attendance(roll=attendance_data.roll, date=today,time=attendance_data.time, status="Present")
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return {"message": "Attendance marked as Present"}

@app.get("/attendance", response_model=list[AttendanceOut])
def list_attendance(
    roll: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    issue_valid: Optional[str] = Query(None),  # e.g., "2023-24"
    orderBy: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    today = date.today()
    default_start = date(today.year - 1, today.month, 1)
    from_dt = datetime.strptime(from_date, "%Y-%m-%d").date() if from_date else default_start
    to_dt = datetime.strptime(to_date, "%Y-%m-%d").date() if to_date else today

    q = db.query(Attendance).join(Student)

    # Filter by roll if provided
    if roll:
        q = q.filter(Attendance.roll == roll.upper())

    # Filter by attendance status if provided
    if status:
        q = q.filter(Attendance.status.ilike(f"%{status}%"))

    # Filter by date range
    q = q.filter(Attendance.date >= from_dt, Attendance.date <= to_dt)

    # Filter by issue_valid if provided
    if issue_valid:
        try:
            start_filter, end_filter = map(int, issue_valid.split("-"))
            # Filter students whose issue_valid range overlaps with filter
            q = q.filter(
                Student.issue_valid.ilike(f"%{start_filter}-%")  # simple string match for your format
            )
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid issue_valid format")

    # Ordering
    if orderBy == "roll":
        q = q.order_by(Attendance.roll)
    elif orderBy == "date":
        q = q.order_by(Attendance.date)

    return q.all()
# -------------------------------attendance analysis------------------------
@app.get("/attendance/analysis")
def attendance_analysis(
        branch: Optional[str] = Query(None),
        issue_valid: Optional[str] = Query(None),  # e.g., "2023-27"
        roll: Optional[str] = Query(None),  # optional roll number filter
        from_date: str = Query(...),
        to_date: str = Query(...),
        total_working_days: int = Query(...),  # entered by teacher
        db: Session = Depends(get_db)
):
    # Parse dates
    start_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(to_date, "%Y-%m-%d").date()

    # Build query for students
    students_q = db.query(Student)
    if branch:
        students_q = students_q.filter(Student.branch == branch)
    if issue_valid:
        start_filter, end_filter = map(int, issue_valid.split("-"))
        students_q = students_q.filter(Student.issue_valid.ilike(f"{start_filter}-%"))
    if roll:
        students_q = students_q.filter(Student.roll == roll.upper())

    students = students_q.all()

    analysis = []
    for student in students:
        present_count = db.query(func.count(Attendance.id)).filter(
            Attendance.roll == student.roll,
            Attendance.date >= start_dt,
            Attendance.date <= end_dt,
            Attendance.status == "Present"
        ).scalar()

        percentage = round((present_count / total_working_days) * 100, 2) if total_working_days > 0 else 0
        analysis.append({
            "roll": student.roll,
            "name": student.name,
            "attendance_percentage": percentage
        })

    return analysis

# ----------------- Secure Scheduled Tasks APIs -----------------
@app.post("/tasks/mark-absent")
async def api_mark_absent_students(
    request: Request,
    mark_absent_api_key: str = Header(...),
    db: Session = Depends(get_db)
):

    verify_api_key(mark_absent_api_key)

    today = date.today()
    students = db.query(Student).all()
    for student in students:
        record = db.query(Attendance).filter(Attendance.roll == student.roll, Attendance.date == today).first()
        if not record:
            absent_record = Attendance(roll=student.roll, date=today, status="Absent")
            db.add(absent_record)
    db.commit()

    return {"message": "Absent students marked"}


@app.post("/tasks/delete-expired-students")
async def api_delete_expired_students(
        request: Request,
        mark_absent_api_key: str = Header(None),
        db: Session = Depends(get_db)
):
    # Verify API key
    verify_api_key(mark_absent_api_key)

    today = datetime.today()
    deleted_count = 0

    # Fetch students with valid issue_valid
    students = db.query(Student).filter(Student.issue_valid != None).all()

    for student in students:
        try:
            end_year_part = student.issue_valid.split("-")[1]
            end_year = int(end_year_part)
            if end_year < 100:
                end_year += 2000

            expire_date = datetime(end_year, 12, 31)

            if today > expire_date:
                # Delete student's attendance records
                db.query(Attendance).filter(Attendance.roll == student.roll).delete()
                # Delete student record
                db.delete(student)
                deleted_count += 1

        except Exception as e:
            print(f"Error deleting student {student.roll}: {e}")

    db.commit()

    return {"message": f"{deleted_count} expired students deleted"}


@app.post("/tasks/cleanup-old-attendance")
async def api_cleanup_old_attendance(
    request: Request,
    mark_absent_api_key: str = Header(None),
    db: Session = Depends(get_db)
):
    verify_api_key(mark_absent_api_key)

    today = datetime.today()
    cutoff_date = today - timedelta(days=365)
    deleted_count = db.query(Attendance).filter(Attendance.date < cutoff_date.date()).delete()
    db.commit()

    return {"message": f"{deleted_count} old attendance records deleted"}

# ----------------------------------------------------app relate feature --------------------------------
router = APIRouter(prefix="/apk", tags=["apk"])
security = HTTPBearer()

def get_current_student(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Extract and verify JWT from Authorization header (Bearer <token>).
    Returns the student's roll (sub) on success.
    """
    token = credentials.credentials
    # decode_access_token raises HTTPException on invalid/expired token
    payload = decode_access_token(token)
    roll = payload.get("sub")
    if not roll:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return roll

@router.post("/login")
def apk_login(data: StudentLogin, db: Session = Depends(get_db)):
    """
    Student login with JSON body { "roll": "...", "pin": "...." }
    Returns: { "token": "<jwt>", "token_type": "bearer" }
    """
    roll = data.roll.strip().upper()
    pin = data.pin.strip()

    student = db.query(Student).filter(Student.roll == roll).first()
    if not student:
        raise HTTPException(status_code=401, detail="Invalid roll or PIN")

    if not verify_password(pin, student.pin):
        raise HTTPException(status_code=401, detail="Invalid roll or PIN")

    token = create_access_token({"sub": student.roll})
    return {"token": token, "token_type": "bearer"}

@router.get("/profile", response_model=StudentProfileOut)
def apk_profile(roll: str = Depends(get_current_student), db: Session = Depends(get_db)):
    """
    Return the authenticated student's profile.
    Token must be set in Authorization header as Bearer <token>.
    """
    roll = roll.upper()
    student = db.query(Student).filter(Student.roll == roll).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    return StudentProfileOut(
        roll=student.roll,
        name=student.name,
        branch=student.branch,
        dob=student.dob,
        issue_valid=student.issue_valid,
        photo=student.photo or ""
    )

@router.get("/photo/{roll}")
def apk_photo(roll: str, db: Session = Depends(get_db)):
    """
    Redirect to stored Cloudinary photo URL (or return 404 if missing).
    """
    student = db.query(Student).filter(Student.roll == roll.upper()).first()
    if not student or not student.photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    # Return a redirect so clients get the Cloudinary URL
    return RedirectResponse(url=student.photo)

@router.get("/attendance", response_model=List[AttendanceRecord])
def apk_attendance(
    roll: str = Depends(get_current_student),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    status: Optional[str] = Query(None, description="Present/Absent"),
    sort_by: Optional[str] = Query("date", description="'date' or 'status' or 'time'"),
    sort_order: Optional[str] = Query("desc", description="'asc' or 'desc'"),
    db: Session = Depends(get_db)
):
    """
    Get attendance records for authenticated student.
    Defaults: last ~6 months if no dates provided.
    """
    # Parse default date range (last ~6 months)
    today = date.today()
    default_start = today - timedelta(days=180)

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else default_start
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    q = db.query(Attendance).filter(Attendance.roll == roll.upper(),
                                    Attendance.date >= start_dt,
                                    Attendance.date <= end_dt)

    if status:
        q = q.filter(Attendance.status.ilike(f"%{status}%"))

    # Ordering
    order = (sort_order or "desc").lower()
    if sort_by == "status":
        q = q.order_by(Attendance.status.asc() if order == "asc" else Attendance.status.desc())
    elif sort_by == "time":
        q = q.order_by(Attendance.time.asc() if order == "asc" else Attendance.time.desc())
    else:
        # default sort by date
        q = q.order_by(Attendance.date.asc() if order == "asc" else Attendance.date.desc())

    rows = q.all()

    # Convert to response schema
    results = []
    for r in rows:
        results.append(AttendanceRecord(
            date=r.date,
            time=r.time,
            status=r.status
        ))
    return results

@router.post("/forgot-pin")
def apk_forgot_pin(data: ForgotPinRequest = Body(...), db: Session = Depends(get_db)):
    """
    Reset PIN after verifying DOB.
    Body: { "roll": "...", "dob": "YYYY-MM-DD", "new_pin": "1234" }
    """
    roll = data.roll.strip().upper()
    dob_str = data.dob.strip()
    new_pin = data.new_pin.strip()

    student = db.query(Student).filter(Student.roll == roll).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Compare DOB strings safely (student.dob is a date)
    try:
        provided_dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid dob format, expected YYYY-MM-DD")

    if student.dob != provided_dob:
        raise HTTPException(status_code=401, detail="DOB does not match")

    # Validate new PIN
    if len(new_pin) != 4 or not new_pin.isdigit():
        raise HTTPException(status_code=400, detail="PIN must be exactly 4 digits")

    student.pin = get_password_hash(new_pin)
    db.commit()
    return {"message": "PIN reset successful"}

# Include router into your main app
# If you are editing main.py where `app` is defined, run:
app.include_router(router)
# ----------------- Root -----------------
@app.get("/")
def read_root():
    return {"message": "College Admin Backend running."}


# ----------------- Database Setup -----------------
Base.metadata.create_all(bind=engine)