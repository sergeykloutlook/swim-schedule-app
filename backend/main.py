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

# Team to child mapping
TEAM_TO_CHILD = {
    "JUN2": "Nastya",
    "JUN 2": "Nastya",
    "JUNIOR 2": "Nastya",
    "JUN1 B": "Kseniya",
    "JUN1B": "Kseniya",
    "JUN 1 B": "Kseniya",
    "JUNIOR 1 BLACK": "Kseniya",
    "JUN1 R": "Liza",
    "JUN1R": "Liza",
    "JUN 1 R": "Liza",
    "JUNIOR 1 RED": "Liza",
}

# Location code to full address mapping
LOCATIONS = {
    "MICC": {
        "name": "Mercer Island Country Club",
        "address": "8700 SE 71st St, Mercer Island, WA 98040"
    },
    "MW": {
        "name": "Mary Wayte Swimming Pool",
        "address": "8815 SE 40th St, Mercer Island, WA 98040"
    },
    "MIBC": {
        "name": "Mercer Island Beach Club",
        "address": "8326 Avalon Dr, Mercer Island, WA 98040"
    },
    "PL": {
        "name": "Phantom Lake Bath & Tennis Club",
        "address": "15810 SE 24th St, Bellevue, WA 98008"
    },
}

# Microsoft Graph API configuration
CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8000/auth/callback")
SCOPES = ["User.Read", "Calendars.ReadWrite", "Mail.Send"]

# Store tokens in memory (use a database in production)
token_cache = {}


def get_msal_app():
    """Create MSAL confidential client application."""
    # Use 'common' to support both personal and organizational accounts
    # Use 'consumers' for personal accounts only, or TENANT_ID for org accounts only
    authority = "https://login.microsoftonline.com/common"
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=authority,
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


def normalize_text(text: str) -> str:
    """
    Clean up text with spacing issues from PDF extraction.
    E.g., "J U N 1 R" -> "JUN1R", "6 : 3 0" -> "6:30"
    """
    if not text:
        return ""
    # Remove all spaces to normalize, then we'll parse it
    return re.sub(r'\s+', '', text).strip()


def extract_schedule_from_pdf(pdf_path: Path) -> list:
    """
    Extract schedule events from a swimming practice PDF.
    Only extracts events for JUN2 (Nastya), JUN1 B (Kseniya), JUN1 R (Liza).
    """
    events = []

    with pdfplumber.open(pdf_path) as pdf:
        all_tables = []

        for page in pdf.pages:
            tables = page.extract_tables()
            if tables:
                all_tables.extend(tables)

        if all_tables:
            events = parse_swim_schedule_tables(all_tables)

    # Sort events by date and time
    def sort_key(event):
        date_str = event.get("date", "")
        time_str = event.get("time", "")

        # Parse date
        try:
            # Handle formats like "Feb 7, 2026" or "Jan 31, 2026"
            parsed_date = datetime.strptime(date_str, "%b %d, %Y")
        except:
            parsed_date = datetime.max

        # Parse start time from time string like "6:00 PM - 7:30 PM"
        start_hour = 0
        start_min = 0
        try:
            # Match pattern like "6:00 PM - 7:30 PM"
            time_match = re.match(r'(\d{1,2}):(\d{2})\s*(AM|PM)', time_str.upper())
            if time_match:
                start_hour = int(time_match.group(1))
                start_min = int(time_match.group(2))
                ampm = time_match.group(3)

                if ampm == "PM" and start_hour != 12:
                    start_hour += 12
                elif ampm == "AM" and start_hour == 12:
                    start_hour = 0
        except:
            pass

        return (parsed_date, start_hour, start_min)

    events.sort(key=sort_key)
    return events


def parse_schedule_line(line: str) -> Optional[dict]:
    """
    Parse a single schedule line like "JUN1 R 11-12:30P MICC" or "J U N 2 6 : 3 0 - 8 P M W"
    Returns dict with child, team, time, location or None if not relevant.
    """
    if not line:
        return None

    original = line
    original_upper = line.upper()

    # Skip OFF entries
    if "OFF" in original_upper:
        return None

    # Step 1: Remove ALL spaces to get a fully normalized string
    compact = re.sub(r'\s+', '', original_upper)

    # Step 2: Identify the team by looking for patterns
    child = None
    team = None
    team_end_pos = 0

    # Check for JUN1R or JUN1B first (more specific)
    if "JUN1R" in compact:
        child = "Liza"
        team = "JUN1 R"
        team_end_pos = compact.find("JUN1R") + 5
    elif "JUN1B" in compact:
        child = "Kseniya"
        team = "JUN1 B"
        team_end_pos = compact.find("JUN1B") + 5
    elif "JUN2" in compact:
        child = "Nastya"
        team = "JUN2"
        team_end_pos = compact.find("JUN2") + 4

    if not child:
        return None

    # Step 3: Extract the rest after the team name
    rest = compact[team_end_pos:]

    # Step 4: Extract time - pattern like "6-7:30P" or "11-12:30PM" or "6:30-8PM"
    # Format output with explicit AM/PM on BOTH start and end times
    time_str = ""
    time_match = re.search(r'(\d{1,2})(?::(\d{2}))?-(\d{1,2})(?::(\d{2}))?([AP]M?)?', rest)
    if time_match:
        start_hour = time_match.group(1)
        start_min = time_match.group(2) or "00"
        end_hour = time_match.group(3)
        end_min = time_match.group(4) or "00"
        ampm = time_match.group(5) or ""
        if ampm:
            if len(ampm) == 1:
                ampm = ampm + "M"
        # Validate start hour (should be 1-12 for 12-hour time)
        try:
            sh = int(start_hour)
            if sh >= 1 and sh <= 12 and ampm:
                # Format with explicit AM/PM on both: "6:00 PM - 7:30 PM"
                time_str = f"{start_hour}:{start_min} {ampm} - {end_hour}:{end_min} {ampm}"
        except:
            pass

    # Step 5: Extract location from the rest
    location_code = ""
    location_info = None
    # Check in order of length (longer codes first to avoid partial matches)
    for code in ["MICC", "MIBC", "MW", "PL"]:
        if code in rest:
            location_code = code
            location_info = LOCATIONS.get(code)
            break

    # Skip entries without both time AND location
    if not time_str or not location_code:
        return None

    # Build the title: "Liza @MICC 6:00 PM - 7:30 PM"
    title = f"{child} @{location_code} {time_str}"

    return {
        "child": child,
        "team": team,
        "time": time_str,
        "location_code": location_code,
        "location_name": location_info["name"] if location_info else "",
        "location_address": location_info["address"] if location_info else "",
        "title": title,
    }


def parse_swim_schedule_tables(tables: list) -> list:
    """Parse swim schedule from extracted tables."""
    events = []

    # Month names for parsing
    MONTHS = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
              "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]
    MONTH_ABBREV = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    for table in tables:
        if not table or len(table) < 3:
            continue

        # Extract the calendar month from the title (Row 0)
        calendar_month = None
        calendar_year = None
        if table[0] and table[0][0]:
            title = str(table[0][0]).upper()
            for i, month in enumerate(MONTHS):
                if month in title:
                    calendar_month = i + 1  # 1-12
                    break
            # Extract year
            year_match = re.search(r'20\d{2}', title)
            if year_match:
                calendar_year = int(year_match.group())

        if not calendar_month:
            calendar_month = 1  # Default to January
        if not calendar_year:
            calendar_year = 2026

        # Find the row with day names (header row)
        header_row_idx = -1
        for row_idx, row in enumerate(table):
            if row:
                row_text = ' '.join(str(c) for c in row if c).lower()
                if 'monday' in row_text or 'tuesday' in row_text:
                    header_row_idx = row_idx
                    break

        if header_row_idx < 0:
            continue

        # Collect ALL date rows and their dates
        # The calendar shows dates in multiple rows (each row is a week)
        all_date_info = {}  # Maps (row_idx, col_idx) to date string

        for row_idx in range(header_row_idx + 1, len(table)):
            row = table[row_idx]
            if not row:
                continue

            # Check if this row has date numbers (even rows typically have dates)
            dates_in_row = []
            for col_idx, cell in enumerate(row):
                if cell:
                    cell_str = str(cell).strip()
                    if re.match(r'^\d{1,2}$', cell_str):
                        date_num = int(cell_str)
                        if 1 <= date_num <= 31:
                            dates_in_row.append((col_idx, date_num))

            if len(dates_in_row) >= 3:
                # This is a date row
                # We ONLY want dates from the calendar month (shown in title)
                # Ignore any previous month dates that appear at start of calendar grid

                # Get days in the calendar month
                import calendar
                days_in_month = calendar.monthrange(calendar_year, calendar_month)[1]

                for col_idx, date_num in dates_in_row:
                    # Only include dates that are valid for the calendar month
                    # (1 to last day of month)
                    if 1 <= date_num <= days_in_month:
                        month_abbrev = MONTH_ABBREV[calendar_month - 1]
                        date_str = f"{month_abbrev} {date_num}, {calendar_year}"

                        # Store for both this row and the next row (data row)
                        all_date_info[(row_idx, col_idx)] = date_str
                        all_date_info[(row_idx + 1, col_idx)] = date_str
                    # Dates outside the month range (e.g., 26-31 in February) are ignored

        # Parse data rows (cells with team schedules)
        for row_idx in range(header_row_idx + 1, len(table)):
            row = table[row_idx]
            if not row:
                continue

            for col_idx, cell in enumerate(row):
                if not cell:
                    continue

                cell_str = str(cell).strip()
                if not cell_str:
                    continue

                # Skip if this is just a date number
                if re.match(r'^\d{1,2}$', cell_str):
                    continue

                # Each cell may contain multiple team schedules separated by newlines
                lines = cell_str.split('\n')

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Parse this line
                    parsed = parse_schedule_line(line)
                    if parsed:
                        # Add date - check current row and nearby columns
                        date_str = all_date_info.get((row_idx, col_idx), "")
                        if not date_str:
                            # Try the row above (date row)
                            date_str = all_date_info.get((row_idx - 1, col_idx), "")
                        parsed["date"] = date_str
                        events.append(parsed)

    return events


@app.get("/api/test-calendar")
async def test_calendar():
    """Test if we can access the user's calendar."""
    if "access_token" not in token_cache:
        raise HTTPException(status_code=401, detail="Not authenticated.")

    access_token = token_cache["access_token"]
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # Try to get user info first
    user_response = requests.get(
        "https://graph.microsoft.com/v1.0/me",
        headers=headers
    )

    # Try to list calendars
    cal_response = requests.get(
        "https://graph.microsoft.com/v1.0/me/calendars",
        headers=headers
    )

    return {
        "user": user_response.json() if user_response.ok else {"error": user_response.json()},
        "calendars": cal_response.json() if cal_response.ok else {"error": cal_response.json()}
    }


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

    # Allow creating events without attendees for testing
    # if not attendees:
    #     raise HTTPException(status_code=400, detail="No attendees specified")

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

            # Get location info
            location_name = event.get("location_name", "")
            location_address = event.get("location_address", "")
            full_location = f"{location_name}, {location_address}" if location_name and location_address else location_name or location_address or ""

            # Create calendar event
            calendar_event = {
                "subject": event["title"],
                "location": {
                    "displayName": full_location
                },
                "start": {
                    "dateTime": start_datetime.isoformat(),
                    "timeZone": "America/Los_Angeles"
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
                    "content": f"<p>Swimming practice: {event['title']}</p><p>Location: {full_location}</p><p>Automatically created by Swim Schedule App</p>"
                }
            }

            # Send to Microsoft Graph API
            response = requests.post(
                "https://graph.microsoft.com/v1.0/me/events",
                headers=headers,
                json=calendar_event
            )

            # Debug logging
            print(f"Event: {event['title']}")
            print(f"Date sent: {event.get('date')} -> Start: {start_datetime}, End: {end_datetime}")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text[:500] if response.text else 'No response'}")

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

    # Parse time - format is "6:00 PM - 7:30 PM" with explicit AM/PM on both
    start_time = None
    end_time = None

    # Match format: "6:00 PM - 7:30 PM" or "11:00 AM - 12:30 PM"
    time_range_match = re.match(
        r"(\d{1,2}):(\d{2})\s*(AM|PM)\s*-\s*(\d{1,2}):(\d{2})\s*(AM|PM)",
        time_str.upper().strip()
    )

    if time_range_match:
        start_hour = int(time_range_match.group(1))
        start_min = int(time_range_match.group(2))
        start_ampm = time_range_match.group(3)
        end_hour = int(time_range_match.group(4))
        end_min = int(time_range_match.group(5))
        end_ampm = time_range_match.group(6)

        # Convert to 24-hour format
        if start_ampm == "PM" and start_hour != 12:
            start_hour += 12
        elif start_ampm == "AM" and start_hour == 12:
            start_hour = 0

        if end_ampm == "PM" and end_hour != 12:
            end_hour += 12
        elif end_ampm == "AM" and end_hour == 12:
            end_hour = 0

        practice_start = datetime.combine(parsed_date, datetime.min.time().replace(hour=start_hour, minute=start_min))
        practice_end = datetime.combine(parsed_date, datetime.min.time().replace(hour=end_hour, minute=end_min))

        # Add commute buffer: 45 min before start, 30 min after end
        start_time = practice_start - timedelta(minutes=45)
        end_time = practice_end + timedelta(minutes=30)
    else:
        # Default to 9 AM - 10 AM if no time found
        start_time = datetime.combine(parsed_date, datetime.min.time().replace(hour=9))
        end_time = start_time + timedelta(hours=1)

    return start_time, end_time


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
