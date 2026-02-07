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
    Clean up text that may have spacing issues from PDF extraction.
    Removes extra spaces between characters while preserving word boundaries.
    """
    if not text:
        return ""
    # Remove spaces between single characters (e.g., "J U N 2" -> "JUN2")
    # But preserve normal word spacing
    cleaned = re.sub(r'(?<=[A-Za-z0-9])\s+(?=[A-Za-z0-9])', '', text)
    # Also handle common patterns
    cleaned = re.sub(r'\s+', ' ', cleaned)  # Multiple spaces to single
    return cleaned.strip()


def extract_schedule_from_pdf(pdf_path: Path) -> list:
    """
    Extract schedule events from a swimming practice PDF.
    Only extracts events for JUN2 (Nastya), JUN1 B (Kseniya), JUN1 R (Liza).
    """
    events = []

    with pdfplumber.open(pdf_path) as pdf:
        all_tables = []

        for page in pdf.pages:
            # Extract tables from each page
            tables = page.extract_tables()
            if tables:
                all_tables.extend(tables)

        # Parse the schedule tables
        if all_tables:
            events = parse_swim_schedule_tables(all_tables)

    return events


def find_team_in_text(text: str) -> Optional[tuple]:
    """
    Find which team (and child) is mentioned in the text.
    Returns (child_name, team_pattern) or None.
    """
    if not text:
        return None

    text_upper = text.upper()
    text_normalized = normalize_text(text_upper)

    # Check for each team pattern
    # JUN2 -> Nastya
    if "JUN2" in text_normalized or "JUN 2" in text_upper or "JUNIOR 2" in text_upper:
        # Make sure it's not JUN1
        if "JUN1" not in text_normalized:
            return ("Nastya", "JUN2")

    # JUN1 B / JUN1B -> Kseniya (Junior 1 Black)
    if ("JUN1" in text_normalized or "JUN 1" in text_upper) and ("B" in text_upper or "BLACK" in text_upper):
        if "R" not in text_upper.replace("JUNIOR", "").replace("JR", "") or "BLACK" in text_upper:
            return ("Kseniya", "JUN1 B")

    # JUN1 R / JUN1R -> Liza (Junior 1 Red)
    if ("JUN1" in text_normalized or "JUN 1" in text_upper) and ("R" in text_upper or "RED" in text_upper):
        if "B" not in text_upper.replace("JUNIOR", "").replace("JR", "") or "RED" in text_upper:
            return ("Liza", "JUN1 R")

    return None


def find_location_in_text(text: str) -> Optional[dict]:
    """Find location code in text and return location info."""
    if not text:
        return None

    text_upper = text.upper()
    text_normalized = normalize_text(text_upper)

    for code, info in LOCATIONS.items():
        if code in text_normalized or code in text_upper:
            return {"code": code, **info}

    return None


def extract_time_from_text(text: str) -> Optional[str]:
    """Extract time range from text."""
    if not text:
        return None

    # Normalize the text first
    normalized = normalize_text(text)

    # Look for time patterns like "6:30-8PM" or "6:30 - 8:00 PM"
    patterns = [
        r'(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}(?::\d{2})?)\s*(AM|PM|am|pm)?',
        r'(\d{1,2})\s*[-–—]\s*(\d{1,2}(?::\d{2})?)\s*(AM|PM|am|pm)',
        r'(\d{1,2}:\d{2})\s*(AM|PM|am|pm)?',
    ]

    for pattern in patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            return match.group(0).strip()

    return None


def parse_swim_schedule_tables(tables: list) -> list:
    """Parse swim schedule from extracted tables."""
    events = []

    # Days of the week patterns for detecting date headers
    day_patterns = {
        "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday",
        "thu": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"
    }

    for table in tables:
        if not table or len(table) < 2:
            continue

        # Find the header row with days/dates
        header_row_idx = -1
        date_columns = {}  # Maps column index to date string

        for row_idx, row in enumerate(table):
            if not row:
                continue

            found_days = 0
            for col_idx, cell in enumerate(row):
                if cell:
                    cell_str = str(cell).strip().lower()
                    for day_abbr, day_full in day_patterns.items():
                        if day_abbr in cell_str:
                            date_columns[col_idx] = str(cell).strip()
                            found_days += 1
                            break

            # If we found multiple days in this row, it's the header
            if found_days >= 2:
                header_row_idx = row_idx
                break

        if header_row_idx < 0:
            continue

        # Parse data rows after header
        for row in table[header_row_idx + 1:]:
            if not row:
                continue

            for col_idx, cell in enumerate(row):
                if not cell:
                    continue

                cell_str = str(cell).strip()
                cell_normalized = normalize_text(cell_str)

                # Skip empty or OFF cells
                if not cell_str or cell_normalized.upper() == "OFF" or cell_str.upper() == "OFF":
                    continue

                # Check if this cell contains a team we care about
                team_info = find_team_in_text(cell_str)
                if not team_info:
                    continue

                child_name, team_name = team_info

                # Extract location
                location_info = find_location_in_text(cell_str)
                location_code = location_info["code"] if location_info else ""
                location_name = location_info["name"] if location_info else ""
                location_address = location_info["address"] if location_info else ""

                # Extract time
                time_str = extract_time_from_text(cell_str)
                if not time_str:
                    time_str = ""

                # Get date from column header
                date_str = date_columns.get(col_idx, "")

                # Build the title: "Liza @MICC 5:00 - 6:00 pm"
                loc_display = f"@{location_code}" if location_code else "@TBD"
                time_display = time_str if time_str else "TBD"
                title = f"{child_name} {loc_display} {time_display}"

                events.append({
                    "child": child_name,
                    "team": team_name,
                    "time": time_str,
                    "date": date_str,
                    "location_code": location_code,
                    "location_name": location_name,
                    "location_address": location_address,
                    "title": title,
                })

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
