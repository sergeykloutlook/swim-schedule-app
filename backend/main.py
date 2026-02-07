import os
import json
import re
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from dotenv import load_dotenv
import pdfplumber
import msal
import requests

load_dotenv()

app = FastAPI(title="Swim Schedule App")

# Mount static files and templates
BASE_DIR = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "frontend" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "frontend" / "templates")

# Microsoft Graph API configuration
CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/callback")
SCOPES = ["Calendars.ReadWrite", "Mail.Send"]

# Store tokens in memory (use a database in production)
token_cache = {}


def get_msal_app():
    """Create MSAL confidential client application."""
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        client_credential=CLIENT_SECRET,
    )


@app.get("/")
async def home(request: Request):
    """Render the main page."""
    is_authenticated = "access_token" in token_cache
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "is_authenticated": is_authenticated}
    )


@app.get("/auth/login")
async def login():
    """Initiate Microsoft OAuth2 login flow."""
    if not CLIENT_ID or not CLIENT_SECRET or not TENANT_ID:
        raise HTTPException(
            status_code=500,
            detail="Azure credentials not configured. Please set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, and AZURE_TENANT_ID in .env file."
        )

    msal_app = get_msal_app()
    auth_url = msal_app.get_authorization_request_url(
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    return RedirectResponse(auth_url)


@app.get("/auth/callback")
async def auth_callback(code: str):
    """Handle OAuth2 callback from Microsoft."""
    msal_app = get_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

    if "access_token" in result:
        token_cache["access_token"] = result["access_token"]
        token_cache["refresh_token"] = result.get("refresh_token")
        return RedirectResponse("/")
    else:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {result.get('error_description', 'Unknown error')}")


@app.get("/auth/logout")
async def logout():
    """Clear authentication tokens."""
    token_cache.clear()
    return RedirectResponse("/")


@app.post("/api/parse-pdf")
async def parse_pdf(file: UploadFile = File(...)):
    """Parse uploaded PDF and extract schedule information."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file")

    # Save uploaded file temporarily
    temp_path = BASE_DIR / "temp_upload.pdf"
    try:
        content = await file.read()
        with open(temp_path, "wb") as f:
            f.write(content)

        # Extract schedule from PDF
        events = extract_schedule_from_pdf(temp_path)

        return {"success": True, "events": events}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing PDF: {str(e)}")

    finally:
        if temp_path.exists():
            temp_path.unlink()


def extract_schedule_from_pdf(pdf_path: Path) -> list:
    """
    Extract schedule events from a swimming practice PDF.

    Attempts to parse tables first, then falls back to text extraction
    with pattern matching for dates, times, and activities.
    """
    events = []

    with pdfplumber.open(pdf_path) as pdf:
        all_text = ""
        all_tables = []

        for page in pdf.pages:
            # Try to extract tables
            tables = page.extract_tables()
            if tables:
                all_tables.extend(tables)

            # Also extract raw text
            text = page.extract_text()
            if text:
                all_text += text + "\n"

        # First, try to parse structured tables
        if all_tables:
            events = parse_tables(all_tables)

        # If no events found from tables, try text parsing
        if not events:
            events = parse_text(all_text)

    return events


def parse_tables(tables: list) -> list:
    """Parse schedule from extracted tables."""
    events = []

    # Common header patterns
    date_headers = ["date", "day", "mon", "tue", "wed", "thu", "fri", "sat", "sun", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    time_headers = ["time", "start", "end", "hours", "am", "pm"]

    for table in tables:
        if not table or len(table) < 2:
            continue

        # Try to identify header row
        header_row = table[0] if table[0] else []
        header_row = [str(h).lower().strip() if h else "" for h in header_row]

        # Find column indices
        date_col = None
        time_col = None
        activity_col = None

        for i, header in enumerate(header_row):
            if any(dh in header for dh in date_headers):
                date_col = i
            elif any(th in header for th in time_headers):
                time_col = i
            elif header and date_col is not None:
                activity_col = i

        # Parse data rows
        for row in table[1:]:
            if not row:
                continue

            event = extract_event_from_row(row, date_col, time_col, activity_col)
            if event:
                events.append(event)

    return events


def extract_event_from_row(row: list, date_col: int, time_col: int, activity_col: int) -> Optional[dict]:
    """Extract a single event from a table row."""
    try:
        date_str = str(row[date_col]) if date_col is not None and date_col < len(row) else ""
        time_str = str(row[time_col]) if time_col is not None and time_col < len(row) else ""
        activity = str(row[activity_col]) if activity_col is not None and activity_col < len(row) else ""

        if not activity:
            # Try to get activity from any non-empty cell
            for i, cell in enumerate(row):
                if cell and i not in [date_col, time_col]:
                    activity = str(cell)
                    break

        if date_str or time_str:
            return {
                "title": activity or "Swimming Practice",
                "date": date_str,
                "time": time_str,
                "raw": " | ".join(str(c) for c in row if c)
            }
    except (IndexError, TypeError):
        pass

    return None


def parse_text(text: str) -> list:
    """Parse schedule from raw text using pattern matching."""
    events = []

    # Date patterns
    date_patterns = [
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",  # MM/DD/YYYY or MM-DD-YYYY
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{0,4})",  # Month DD, YYYY
        r"((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2})",  # Day, Month DD
    ]

    # Time patterns
    time_patterns = [
        r"(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)\s*[-–—to]+\s*(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)",  # Time range
        r"(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)",  # Single time
    ]

    lines = text.split("\n")
    current_date = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check for date in line
        for pattern in date_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                current_date = match.group(1)
                break

        # Check for time in line
        for pattern in time_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                time_str = match.group(0)

                # Extract activity (text before or after the time)
                activity = re.sub(pattern, "", line, flags=re.IGNORECASE).strip()
                activity = re.sub(r"^\W+|\W+$", "", activity)  # Clean up

                if not activity:
                    activity = "Swimming Practice"

                events.append({
                    "title": activity,
                    "date": current_date or "",
                    "time": time_str,
                    "raw": line
                })
                break

    return events


@app.post("/api/send-invites")
async def send_invites(request: Request):
    """Create calendar events and send invites via Microsoft Graph API."""
    if "access_token" not in token_cache:
        raise HTTPException(status_code=401, detail="Not authenticated. Please login with Microsoft first.")

    data = await request.json()
    events = data.get("events", [])
    attendees = data.get("attendees", [])  # List of email addresses

    if not events:
        raise HTTPException(status_code=400, detail="No events to create")

    if not attendees:
        raise HTTPException(status_code=400, detail="No attendees specified")

    access_token = token_cache["access_token"]
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    results = []

    for event in events:
        try:
            # Parse date and time
            start_datetime, end_datetime = parse_event_datetime(event)

            if not start_datetime:
                results.append({
                    "event": event["title"],
                    "success": False,
                    "error": "Could not parse date/time"
                })
                continue

            # Create calendar event
            calendar_event = {
                "subject": event["title"],
                "start": {
                    "dateTime": start_datetime.isoformat(),
                    "timeZone": "America/Los_Angeles"  # Adjust as needed
                },
                "end": {
                    "dateTime": end_datetime.isoformat(),
                    "timeZone": "America/Los_Angeles"
                },
                "attendees": [
                    {
                        "emailAddress": {"address": email},
                        "type": "required"
                    }
                    for email in attendees
                ],
                "isOnlineMeeting": False,
                "body": {
                    "contentType": "HTML",
                    "content": f"<p>Swimming practice: {event['title']}</p><p>Automatically created by Swim Schedule App</p>"
                }
            }

            # Send to Microsoft Graph API
            response = requests.post(
                "https://graph.microsoft.com/v1.0/me/events",
                headers=headers,
                json=calendar_event
            )

            if response.status_code in [200, 201]:
                results.append({
                    "event": event["title"],
                    "success": True,
                    "id": response.json().get("id")
                })
            else:
                results.append({
                    "event": event["title"],
                    "success": False,
                    "error": response.json().get("error", {}).get("message", "Unknown error")
                })

        except Exception as e:
            results.append({
                "event": event.get("title", "Unknown"),
                "success": False,
                "error": str(e)
            })

    successful = sum(1 for r in results if r["success"])
    return {
        "success": True,
        "message": f"Created {successful} of {len(events)} events",
        "results": results
    }


def parse_event_datetime(event: dict) -> tuple:
    """Parse date and time from event data into datetime objects."""
    date_str = event.get("date", "")
    time_str = event.get("time", "")

    # Common date formats to try
    date_formats = [
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%m/%d/%y",
        "%m-%d-%y",
        "%B %d, %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%b %d %Y",
        "%d %B %Y",
        "%d %b %Y",
    ]

    parsed_date = None

    # Clean up date string
    date_str = re.sub(r"(st|nd|rd|th)", "", date_str, flags=re.IGNORECASE)
    date_str = date_str.strip(" ,")

    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt).date()
            break
        except ValueError:
            continue

    if not parsed_date:
        # Try to extract just the date parts
        match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-]?(\d{2,4})?", date_str)
        if match:
            month, day = int(match.group(1)), int(match.group(2))
            year = int(match.group(3)) if match.group(3) else datetime.now().year
            if year < 100:
                year += 2000
            try:
                parsed_date = datetime(year, month, day).date()
            except ValueError:
                pass

    if not parsed_date:
        # Default to today if no date found
        parsed_date = datetime.now().date()

    # Parse time
    start_time = None
    end_time = None

    # Look for time range
    time_range_match = re.search(
        r"(\d{1,2}):?(\d{2})?\s*(AM|PM|am|pm)?\s*[-–—to]+\s*(\d{1,2}):?(\d{2})?\s*(AM|PM|am|pm)?",
        time_str
    )

    if time_range_match:
        start_hour = int(time_range_match.group(1))
        start_min = int(time_range_match.group(2) or 0)
        start_ampm = time_range_match.group(3)

        end_hour = int(time_range_match.group(4))
        end_min = int(time_range_match.group(5) or 0)
        end_ampm = time_range_match.group(6) or start_ampm

        # Adjust for AM/PM
        if start_ampm and start_ampm.upper() == "PM" and start_hour != 12:
            start_hour += 12
        elif start_ampm and start_ampm.upper() == "AM" and start_hour == 12:
            start_hour = 0

        if end_ampm and end_ampm.upper() == "PM" and end_hour != 12:
            end_hour += 12
        elif end_ampm and end_ampm.upper() == "AM" and end_hour == 12:
            end_hour = 0

        start_time = datetime.combine(parsed_date, datetime.min.time().replace(hour=start_hour, minute=start_min))
        end_time = datetime.combine(parsed_date, datetime.min.time().replace(hour=end_hour, minute=end_min))
    else:
        # Look for single time
        single_time_match = re.search(r"(\d{1,2}):?(\d{2})?\s*(AM|PM|am|pm)?", time_str)
        if single_time_match:
            hour = int(single_time_match.group(1))
            minute = int(single_time_match.group(2) or 0)
            ampm = single_time_match.group(3)

            if ampm and ampm.upper() == "PM" and hour != 12:
                hour += 12
            elif ampm and ampm.upper() == "AM" and hour == 12:
                hour = 0

            start_time = datetime.combine(parsed_date, datetime.min.time().replace(hour=hour, minute=minute))
            end_time = start_time + timedelta(hours=1)  # Default 1 hour duration
        else:
            # Default to 9 AM if no time found
            start_time = datetime.combine(parsed_date, datetime.min.time().replace(hour=9))
            end_time = start_time + timedelta(hours=1)

    return start_time, end_time


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
