import os
import json
import re
import base64
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
import anthropic
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

# Reverse mapping: child name to canonical team code
CHILD_TO_TEAM = {
    "Nastya": "JUN2",
    "Kseniya": "JUN1 B",
    "Liza": "JUN1 R",
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

# Anthropic API configuration
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

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
    """Parse uploaded PDF using Claude LLM and extract schedule information."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file")

    if not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="Anthropic API key not configured. Please set ANTHROPIC_API_KEY in .env file."
        )

    try:
        pdf_bytes = await file.read()
        events = parse_pdf_with_llm(pdf_bytes)
        return {"success": True, "events": events}

    except anthropic.APIError as e:
        raise HTTPException(status_code=500, detail=f"Claude API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing PDF: {str(e)}")


def parse_pdf_with_llm(pdf_bytes: bytes) -> list:
    """Send PDF to Claude API for parsing, return flat event list."""
    # Read LLM instructions
    instructions_path = BASE_DIR / "llm_instructions.md"
    with open(instructions_path, "r") as f:
        llm_prompt = f.read()

    # Encode PDF as base64
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    # Call Claude API
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": llm_prompt,
                    },
                ],
            }
        ],
    )

    # Extract JSON from response
    response_text = message.content[0].text.strip()

    # Strip markdown code fences if present
    if response_text.startswith("```"):
        response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)

    grouped_data = json.loads(response_text)

    # Convert date-grouped format to flat event list
    events = []
    for date_str, children in grouped_data.items():
        for child_name, details in children.items():
            location_code = details.get("location_code", "")
            location_info = LOCATIONS.get(location_code)
            time_str = details.get("time", "")
            has_dl = details.get("dl", False)

            title = f"{child_name} @{location_code} {time_str}"
            if has_dl:
                title += " DL"

            events.append({
                "child": child_name,
                "team": CHILD_TO_TEAM.get(child_name, ""),
                "date": date_str,
                "time": time_str,
                "location_code": location_code,
                "location_name": location_info["name"] if location_info else "",
                "location_address": location_info["address"] if location_info else "",
                "title": title,
                "dl": has_dl,
            })

    # Sort by date then child name
    def sort_key(event):
        try:
            parsed_date = datetime.strptime(event["date"], "%b %d, %Y")
        except ValueError:
            parsed_date = datetime.max
        return (parsed_date, event["child"])

    events.sort(key=sort_key)
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

            # Determine categories based on recipient/sender
            # For ikhapova@outlook.com: use child name (Liza, Nastya, Ksyusha)
            # For sergeykl@outlook.com: use location-based (Swimming - MW, etc.)
            child_name = event.get("child", "")
            location_code = event.get("location_code", "")

            categories = []
            if "ikhapova@outlook.com" in attendees:
                # Use child name as category
                if child_name == "Liza":
                    categories = ["Liza"]
                elif child_name == "Nastya":
                    categories = ["Nastya"]
                elif child_name == "Kseniya":
                    categories = ["Ksyusha"]
            else:
                # Default: use location-based categories (for sergeykl@outlook.com)
                if location_code in ["PL", "MICC", "MIBC", "MW"]:
                    categories = [f"Swimming - {location_code}"]
                else:
                    categories = ["Swimming"]

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
                "categories": categories,
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

        # Add commute buffer: 45 min before start, no buffer after end
        start_time = practice_start - timedelta(minutes=45)
        end_time = practice_end
    else:
        # Default to 9 AM - 10 AM if no time found
        start_time = datetime.combine(parsed_date, datetime.min.time().replace(hour=9))
        end_time = start_time + timedelta(hours=1)

    return start_time, end_time


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
