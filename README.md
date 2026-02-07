# Swim Schedule App

A web application that parses swimming practice schedule PDFs and creates Outlook calendar events with meeting invites.

## Features

- Upload PDF files containing swimming practice schedules
- Automatic extraction of dates, times, and event details
- Microsoft Outlook integration via Graph API
- Send calendar invites to multiple attendees
- Clean, responsive web interface

## Tech Stack

- **Backend**: Python, FastAPI
- **PDF Parsing**: pdfplumber
- **Calendar Integration**: Microsoft Graph API
- **Frontend**: HTML, CSS, JavaScript

## Prerequisites

- Python 3.9+
- Microsoft Azure account (free tier works)

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/sergeykloutlook/swim-schedule-app.git
cd swim-schedule-app
```

### 2. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set Up Azure App Registration

To send calendar invites via Outlook, you need to register an app in Azure:

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** > **App registrations**
3. Click **New registration**
4. Fill in:
   - **Name**: `Swim Schedule App`
   - **Supported account types**: Select based on your needs:
     - "Accounts in this organizational directory only" for work/school accounts
     - "Accounts in any organizational directory and personal Microsoft accounts" for broader access
   - **Redirect URI**: Select "Web" and enter `http://localhost:8000/auth/callback`
5. Click **Register**

After registration:

1. Copy the **Application (client) ID** - this is your `AZURE_CLIENT_ID`
2. Copy the **Directory (tenant) ID** - this is your `AZURE_TENANT_ID`
3. Go to **Certificates & secrets** > **New client secret**
   - Add a description and expiration
   - Copy the secret **Value** (not the ID) - this is your `AZURE_CLIENT_SECRET`
4. Go to **API permissions** > **Add a permission**
   - Select **Microsoft Graph** > **Delegated permissions**
   - Add these permissions:
     - `Calendars.ReadWrite`
     - `Mail.Send`
   - Click **Add permissions**
5. If using organizational accounts, click **Grant admin consent** (requires admin privileges)

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` with your Azure credentials:

```
AZURE_CLIENT_ID=your-client-id-here
AZURE_CLIENT_SECRET=your-client-secret-here
AZURE_TENANT_ID=your-tenant-id-here
REDIRECT_URI=http://localhost:8000/auth/callback
```

### 5. Run the Application

```bash
python backend/main.py
```

Or with uvicorn directly:

```bash
uvicorn backend.main:app --reload
```

Open your browser to [http://localhost:8000](http://localhost:8000)

## Usage

1. **Connect to Outlook**: Click "Connect to Outlook" and sign in with your Microsoft account
2. **Upload PDF**: Drag and drop or click to upload your swimming schedule PDF
3. **Review Events**: Check the parsed events and select which ones to create
4. **Add Attendees**: Enter email addresses of people to invite
5. **Send Invites**: Click "Send Calendar Invites" to create events and send invitations

## Supported PDF Formats

The app attempts to parse:
- Tables with date, time, and activity columns
- Text-based schedules with recognizable date/time patterns
- Various date formats (MM/DD/YYYY, Month DD, YYYY, etc.)
- Time ranges (e.g., "4:00 PM - 5:30 PM")

For complex or image-based PDFs, you may need to manually edit the extracted events.

## Troubleshooting

### "Azure credentials not configured"
Make sure your `.env` file exists and contains valid credentials.

### "Authentication failed"
- Verify your Azure app registration settings
- Ensure the redirect URI matches exactly: `http://localhost:8000/auth/callback`
- Check that the required permissions are granted

### "Could not parse date/time"
The PDF format may not be recognized. Try a PDF with clearer table structure or standard date/time formats.

## License

MIT
