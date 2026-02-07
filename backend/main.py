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

    # First, normalize the entire line by removing spaces within character sequences
    # but preserving the structure
    # "J U N 2 6 : 3 0 - 8 P M W" -> "JUN2 6:30-8PM MW"

    # Step 1: Fix spacing around colons and dashes for time
    normalized = re.sub(r'(\d)\s*:\s*(\d)', r'\1:\2', original)  # "6 : 30" -> "6:30"
    normalized = re.sub(r'(\d)\s*-\s*(\d)', r'\1-\2', normalized)  # "6 - 8" -> "6-8"

    # Step 2: Fix letter spacing (but carefully preserve meaningful spaces)
    # Remove spaces between consecutive single letters
    normalized = re.sub(r'(?<=[A-Z])\s+(?=[A-Z](?:\s|$|[^A-Za-z]))', '', normalized.upper())
    # Also handle patterns like "J U N 2" -> "JUN2"
    normalized = re.sub(r'([A-Z])\s+([A-Z])\s+([A-Z])\s*(\d)', r'\1\2\3\4', normalized)

    # Step 3: Clean up remaining issues
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    # Determine which child/team
    child = None
    team = None

    if "JUN2" in normalized and "JUN1" not in normalized:
        child = "Nastya"
        team = "JUN2"
    elif "JUN1R" in normalized or "JUN1 R" in normalized:
        if "JUN1B" not in normalized and "JUN1 B" not in normalized:
            child = "Liza"
            team = "JUN1 R"
    elif "JUN1B" in normalized or "JUN1 B" in normalized:
        if "JUN1R" not in normalized and "JUN1 R" not in normalized:
            child = "Kseniya"
            team = "JUN1 B"

    if not child:
        return None

    # Extract time from the normalized line
    # Pattern: time like "11-12:30P" or "6:30-8PM" or "5-6P"
    time_str = ""
    time_match = re.search(r'(\d{1,2}(?::\d{2})?)-(\d{1,2}(?::\d{2})?)\s*([AP]M?)?', normalized)
    if time_match:
        start = time_match.group(1)
        end = time_match.group(2)
        ampm = time_match.group(3) or ""
        if ampm:
            if len(ampm) == 1:
                ampm = ampm + "M"
        # Validate start hour (should be 1-12 for 12-hour time)
        try:
            start_hour = int(start.split(':')[0])
            if start_hour >= 1 and start_hour <= 12:
                time_str = f"{start}-{end}{ampm}"
        except:
            pass

    # Extract location
    location_code = ""
    location_info = None
    for code, info in LOCATIONS.items():
        if code in normalized:
            location_code = code
            location_info = info
            break

    # Skip entries without both time AND location
    if not time_str or not location_code:
        return None

    # Build the title: "Liza @MICC 11-12:30PM"
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

    # Map column indices to dates based on the date row
    # The PDF has dates in rows like: ['29', 'NO MW', '30', 'NO MW', ...]

    for table in tables:
        if not table or len(table) < 3:
            continue

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

        # Find date row (the row with numbers like 29, 30, 31, 1, 2, 3, 4)
        date_row_idx = -1
        date_columns = {}  # Maps column index to date info

        for row_idx in range(header_row_idx + 1, min(header_row_idx + 3, len(table))):
            row = table[row_idx]
            if not row:
                continue

            # Check if this row has date numbers
            date_count = 0
            for col_idx, cell in enumerate(row):
                if cell:
                    cell_str = str(cell).strip()
                    # Check if it's a date number (1-31)
                    if re.match(r'^\d{1,2}$', cell_str):
                        date_num = int(cell_str)
                        if 1 <= date_num <= 31:
                            date_columns[col_idx] = f"Jan {date_num}"
                            date_count += 1

            if date_count >= 3:
                date_row_idx = row_idx
                break

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

                # Each cell may contain multiple team schedules separated by newlines
                lines = cell_str.split('\n')

                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Parse this line
                    parsed = parse_schedule_line(line)
                    if parsed:
                        # Add date from the date row
                        date_str = date_columns.get(col_idx, "")
                        parsed["date"] = date_str
                        events.append(parsed)

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
