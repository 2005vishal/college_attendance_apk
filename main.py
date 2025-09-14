import os
from datetime import datetime, timedelta
from typing import List

from urllib.parse import urlparse
import psycopg2
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
from auth import create_access_token, verify_password, get_password_hash,verify_jwt_token
from fastapi import Query
from typing import Optional

load_dotenv()

# =================== DB CONFIG ===================
DB_URL = os.getenv("DATABASE_URL")

JWT_SECRET = os.getenv("JWT_SECRET", "53b60c5b707b8de38f0a5a244c88c37147140c2bcdfb889a4d9e5f89962dff1d")
JWT_EXP_MINUTES = int(os.getenv("JWT_EXP_MINUTES", 60))

# =================== FASTAPI APP ===================
app = FastAPI(
    title="Student Attendance API",
    swagger_ui_parameters={"persistAuthorization": True}
)

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =================== MODELS ===================
class LoginRequest(BaseModel):
    roll: str
    pin: str

class StudentProfile(BaseModel):
    roll: str
    name: str
    branch: str
    dob: str
    issue_valid: str
    photo: str   # will now be URL instead of base64

class AttendanceRecord(BaseModel):
    date: str
    status: str

# =================== DB CONNECTION ===================
def get_connection():
    try:
        return psycopg2.connect(DB_URL, sslmode="require")
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

# =================== SECURITY ===================
security = HTTPBearer()

def get_current_roll(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = verify_jwt_token(token)
    return payload["sub"]


# =================== API ENDPOINTS ===================
@app.post("/api/login")
def login(req: LoginRequest):
    roll = req.roll.strip()
    pin = req.pin.strip()

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT roll, pin FROM Students WHERE TRIM(roll)=%s", (roll,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid roll or PIN")

    stored_hashed_pin = row[1]

    if not verify_password(pin, stored_hashed_pin):
        raise HTTPException(status_code=401, detail="Invalid roll or PIN")

    token = create_access_token({"sub": roll})
    return {"token": token}


# ✅ PROFILE ENDPOINT
@app.get("/api/profile", response_model=StudentProfile)
def get_profile(roll: str = Depends(get_current_roll)):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT roll, name, branch, dob, issue_valid, photo FROM Students WHERE roll=%s",
            (roll,)
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Student not found")

    return StudentProfile(
        roll=str(row[0]),
        name=str(row[1]),
        branch=str(row[2]),
        dob=str(row[3]),
        issue_valid=str(row[4]),
        photo=str(row[5])
    )


# ✅ Serve photo by roll
@app.get("/api/photo/{roll}")
def get_student_photo(roll: str):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT photo FROM Students WHERE roll=%s", (roll,))
        row = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Photo not found")

    # row[0] is Cloudinary URL
    return RedirectResponse(url=row[0])


# ✅ Attendance Endpoint


@app.get("/api/attendance", response_model=List[AttendanceRecord])
def get_attendance(
    roll: str = Depends(get_current_roll),
    start_date: Optional[str] = Query(None, description="Start date in YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date in YYYY-MM-DD"),
    status: Optional[str] = Query(None, description="Filter by status (Present/Absent)"),
    sort_by: Optional[str] = Query("date", description="Sort by 'date' or 'status'"),
    sort_order: Optional[str] = Query("desc", description="Sort order 'asc' or 'desc'")
):
    from datetime import datetime, timedelta

    # Default start date = 1st day of month, 6 months ago
    today = datetime.utcnow().date()
    six_months_ago = today.replace(day=1) - timedelta(days=1)
    six_months_ago = six_months_ago.replace(day=1)

    try:
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else six_months_ago
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else today
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    conn = get_connection()
    cursor = conn.cursor()
    try:
        query = "SELECT date, status FROM Attendance WHERE roll=%s AND date BETWEEN %s AND %s"
        params = [roll, start_date_obj, end_date_obj]

        # Filter by status if provided
        if status:
            query += " AND status=%s"
            params.append(status)

        # Add sorting
        if sort_by not in ["date", "status"]:
            sort_by = "date"
        order = "ASC" if sort_order.lower() == "asc" else "DESC"
        query += f" ORDER BY {sort_by} {order}"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    records = [
        {"date": row[0].strftime("%Y-%m-%d"), "status": row[1]}
        for row in rows
    ]
    return records


# ✅ Forgot PIN
from fastapi import Body, HTTPException
from auth import get_password_hash  # Import the hashing function

@app.post("/api/forgot-pin")
def forgot_pin(data: dict = Body(...)):
    roll = data.get("roll")
    dob = data.get("dob")  # expected format: YYYY-MM-DD
    new_pin = data.get("new_pin")

    if not roll or not dob or not new_pin:
        raise HTTPException(status_code=400, detail="Missing fields")

    conn = get_connection()
    cursor = conn.cursor()
    try:
        # Check if student exists and DOB matches
        cursor.execute("SELECT dob FROM Students WHERE roll=%s", (roll,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Student not found")

        db_dob = str(row[0])
        if db_dob != dob:
            raise HTTPException(status_code=401, detail="DOB does not match")

        # Hash the new PIN before storing it
        hashed_pin = get_password_hash(new_pin)

        # Update the student’s PIN with the hashed version
        cursor.execute("UPDATE Students SET pin=%s WHERE roll=%s", (hashed_pin, roll))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

    return {"message": "PIN reset successful"}

