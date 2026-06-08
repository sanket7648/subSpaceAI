# Automated Outreach Pipeline

An intelligent B2B lead generation and outreach automation pipeline that leverages multiple third-party APIs to identify, enrich, and contact decision-makers across target companies.

## 🎯 Project Overview

The **Automated Outreach Pipeline** is a sophisticated automation tool designed to help B2B businesses streamline their lead generation and outreach process. It integrates with multiple APIs to:

1. **Find lookalike companies** based on a seed domain using Ocean.io
2. **Discover decision-makers** at those companies using Prospeo
3. **Enrich lead profiles** with verified email addresses
4. **Send personalized outreach emails** via Brevo's email service

The pipeline includes built-in safety checkpoints, error handling, and comprehensive logging to ensure reliable execution.

---

## 🏗️ Architecture

### Three-Stage Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│              AUTOMATED OUTREACH PIPELINE                    │
└─────────────────────────────────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
    ┌───▼────┐       ┌───▼────┐       ┌───▼─────┐
    │ STAGE 1 │       │ STAGE 2 │       │ STAGE 3 │
    │ OCEAN   │       │ PROSPEO │       │ BREVO   │
    └───┬────┘       └───┬────┘       └───┬─────┘
        │                │                 │
    Find Similar    Search & Enrich    Send Emails
      Companies      Decision Makers    to Leads
```

### Stage 1: Ocean.io Integration
- **Purpose**: Finds companies similar to your seed domain
- **Output**: List of lookalike company domains
- **Rate Limit**: Handles API responses and timeouts
- **Error Handling**: Validates domain extraction

### Stage 2: Prospeo Integration
- **Part A - Search**: Identifies decision-makers (C-level, Directors, VPs)
- **Part B - Enrich**: Retrieves verified email addresses and LinkedIn profiles
- **Output**: Enriched lead profiles with contact information
- **Rate Limiting**: Respects 1 request/second limit
- **Retry Logic**: 3-attempt retry with exponential backoff

### Stage 3: Brevo Integration
- **Purpose**: Sends personalized outreach emails to verified leads
- **Features**: Custom email templates, sender customization
- **Output**: Email delivery confirmation
- **Safety Checkpoint**: Manual approval before sending emails

---

## 📦 Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | FastAPI | REST API development |
| **Server** | Uvicorn | ASGI server for FastAPI |
| **Database** | SQLAlchemy + PostgreSQL | Data persistence and ORM |
| **Database Driver** | psycopg2-binary | PostgreSQL connection |
| **HTTP Client** | httpx | Async HTTP requests |
| **Config Management** | pydantic-settings, python-dotenv | Environment variables |
| **Resilience** | tenacity | Retry logic and exponential backoff |

### Dependencies

```
fastapi              # Web framework
uvicorn              # ASGI server
sqlalchemy           # ORM
psycopg2-binary      # PostgreSQL adapter
httpx                # Async HTTP client
pydantic-settings    # Settings management
python-dotenv        # Environment loading
tenacity             # Retry decorator
```

---

## 📁 Project Structure

```
automated-outreach-pipeline/
├── cli.py                          # Main CLI entry point
├── requirements.txt                # Python dependencies
├── .env                            # Environment variables (not in repo)
├── README.md                       # This file
│
└── app/                            # Main application package
    ├── __init__.py
    ├── main.py                     # FastAPI app definition
    ├── database.py                 # Database configuration
    ├── models.py                   # SQLAlchemy ORM models
    ├── schemas.py                  # Pydantic schemas (currently empty)
    │
    └── services/                   # External API integrations
        ├── __init__.py
        ├── ocean_service.py        # Ocean.io API client
        ├── prospeo_service.py      # Prospeo API client
        └── brevo_service.py        # Brevo email service
```

---

## 🗄️ Database Schema

### PipelineRun
Tracks each execution of the pipeline with status and results.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Unique run identifier |
| `seed_domain` | String | Initial domain provided by user |
| `status` | String | Pipeline status: `started`, `completed`, `failed` |
| `companies` | Relationship | Associated Company records |

### Company
Represents companies discovered through Ocean.io lookalike search.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Unique company identifier |
| `run_id` | Integer (FK) | Reference to parent PipelineRun |
| `domain` | String | Company domain (e.g., hubspot.com) |
| `run` | Relationship | Parent PipelineRun |
| `leads` | Relationship | Associated Lead records |

### Lead
Represents decision-makers at target companies.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Unique lead identifier |
| `company_id` | Integer (FK) | Reference to Company |
| `name` | String | Full name of decision-maker |
| `linkedin_url` | String | LinkedIn profile URL (nullable) |
| `work_email` | String | Verified work email (nullable) |
| `email_sent` | Boolean | Whether outreach email was sent |
| `company` | Relationship | Parent Company |

---

## 🔧 Services & Integrations

### 1. Ocean Service (`app/services/ocean_service.py`)

**Function**: `get_lookalike_companies(seed_domain: str, limit: int = 5)`

Finds companies similar to your seed domain using Ocean.io's API.

**Parameters**:
- `seed_domain` (str): The reference company domain (e.g., "hubspot.com")
- `limit` (int): Number of lookalikes to return (default: 5)

**Returns**: List of domain strings

**Error Handling**:
- Validates API key presence
- Raises HTTPException on API errors
- Handles network timeouts (15 second limit)

**Example**:
```python
lookalikes = await get_lookalike_companies("hubspot.com", limit=5)
# Returns: ["intercom.com", "pipedrive.com", "zendesk.com", ...]
```

---

### 2. Prospeo Service (`app/services/prospeo_service.py`)

#### Function A: `search_decision_makers(domain: str)`

Searches for decision-makers at a specific company domain.

**Parameters**:
- `domain` (str): Company domain to search

**Returns**: List of person dictionaries with extracted person data

**Targeted Titles**: CEO, Founder, Director, VP, CTO, CMO

**Features**:
- 3-attempt retry with 2.5 second backoff on rate limit (429)
- Handles NO_RESULTS responses gracefully
- Extracts nested person objects for easier consumption
- 1.2 second delay between requests

**Example**:
```python
leads = await search_decision_makers("hubspot.com")
# Returns: [
#   {"id": "p123", "full_name": "Brian Halligan", "linkedin_url": "...", ...},
#   ...
# ]
```

---

#### Function B: `enrich_leads_bulk(leads_to_enrich: List[Dict])`

Enriches lead profiles with verified email addresses and additional data.

**Parameters**:
- `leads_to_enrich` (List[Dict]): List of lead objects to enrich

**Returns**: Dictionary with matched results

**Features**:
- Respects 1 request/second rate limit
- Verifies emails are genuine work addresses
- Handles retry logic for transient failures
- Extracts and validates email data from nested structures

**Example**:
```python
enriched = await enrich_leads_bulk([
    {"person_id": "p123"},
    {"linkedin_url": "https://linkedin.com/in/user"}
])
# Returns: {
#   "matched": [
#     {"person": {"email": {"email": "brian@hubspot.com"}, ...}},
#     ...
#   ]
# }
```

---

### 3. Brevo Service (`app/services/brevo_service.py`)

**Function**: `send_outreach_email(to_email: str, to_name: str, company_name: str)`

Sends a personalized outreach email via Brevo's SMTP API.

**Parameters**:
- `to_email` (str): Recipient's email address
- `to_name` (str): Recipient's first name
- `company_name` (str): Company domain for personalization

**Returns**: Boolean (success/failure)

**Features**:
- Personalized subject and HTML email template
- Customizable sender name and email
- Handles API errors and exceptions gracefully
- Returns 201/202 on success (Brevo API response codes)

**Email Template**:
```
Subject: Quick question about {company_name}

Hi {to_name},

I was researching {company_name} and noticed the great work your team is doing.

I am reaching out to see if you'd be open to connecting. 
I'd love to share how our platform can help streamline your processes.

Best regards,
{SENDER_NAME}
```

**Example**:
```python
success = await send_outreach_email(
    to_email="brian@hubspot.com",
    to_name="Brian",
    company_name="hubspot.com"
)
# Returns: True if successful
```

---

## 🖥️ CLI Usage

### Overview

The CLI (`cli.py`) is the main entry point for running the complete automated pipeline. It orchestrates all three stages with interactive prompts and safety checkpoints.

### Running the Pipeline

```bash
python cli.py
```

### Interactive Flow

**Step 1**: Enter seed domain
```
Enter the seed domain (e.g., hubspot.com): hubspot.com
```

**Step 2**: Pipeline discovers lookalikes
```
[Stage 1] Finding lookalike companies for hubspot.com...
  -> Found 5 domains: intercom.com, pipedrive.com, zendesk.com, ...
```

**Step 3**: Searches and enriches decision-makers
```
[Stage 2] Searching & Enriching Decision Makers (Prospeo)...
  -> Successfully enriched 23 leads.
  -> 18 leads have verified emails ready for outreach.
```

**Step 4**: Safety checkpoint with email list
```
==================================================
                SAFETY CHECKPOINT                 
==================================================
 - Brian Halligan (hubspot.com) -> brian@hubspot.com
 - Dharmesh Shah (hubspot.com) -> dharmesh@hubspot.com
 - Kyle Poyar (pipedrive.com) -> kyle@pipedrive.com
 ...
==================================================
```

**Step 5**: Manual approval before sending
```
Do you want to send outreach emails to these leads? (y/n): y
```

**Step 6**: Sends emails and completes
```
[Stage 3] Sending Outreach Emails via Brevo...
  -> Sending to brian@hubspot.com...
  Email successfully queued for brian@hubspot.com
  ...
✅ Pipeline Complete! Successfully sent 18 emails.
```

### CLI Features

- **Input Validation**: Validates domain input
- **Database Persistence**: Creates PipelineRun record for tracking
- **Error Handling**: Catches and logs exceptions with meaningful messages
- **Safety Checkpoint**: Manual approval before sending emails
- **Status Tracking**: Updates pipeline run status (running → completed/failed)
- **Graceful Exit**: Supports cancellation at checkpoint
- **Environment Loading**: Automatically loads `.env` file if available

### Possible Exit States

| Status | Meaning |
|--------|---------|
| `running` | Pipeline in progress |
| `completed_emails_sent` | Successfully sent all emails |
| `stopped_at_checkpoint` | User declined email sending |
| `failed: [error]` | Pipeline encountered an error |

---

## 🌐 FastAPI Endpoints

### GET `/test-prospeo/`

Debug endpoint for testing Prospeo API with different parameter names.

**Query Parameters**:
- `domain` (str, optional): Domain to test (default: "hubspot.com")

**Purpose**: Helps troubleshoot API integration issues

**Response**: Array of test results showing different payload formats

**Example**:
```bash
curl "http://localhost:8000/test-prospeo/?domain=hubspot.com"
```

---

## 🔐 Environment Variables

Create a `.env` file in the project root with the following variables:

```env
# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/outreach_pipeline

# Ocean.io API
OCEAN_API_KEY=your_ocean_api_key_here

# Prospeo API
PROSPEO_API_KEY=your_prospeo_api_key_here

# Brevo Email Service
BREVO_API_KEY=your_brevo_api_key_here
SENDER_EMAIL=your_email@example.com
SENDER_NAME=Your Name
```

### Getting API Keys

1. **Ocean.io**: https://ocean.io - Sign up and generate API token
2. **Prospeo**: https://prospeo.io - Sign up and get API key
3. **Brevo**: https://www.brevo.com - Create account and generate SMTP key
4. **PostgreSQL**: Set up local or cloud PostgreSQL instance

---

## 📋 Installation & Setup

### Prerequisites

- Python 3.8+
- PostgreSQL database
- API keys for Ocean.io, Prospeo, and Brevo

### Step 1: Clone Repository

```bash
cd automated-outreach-pipeline
```

### Step 2: Create Virtual Environment

```bash
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment

Create `.env` file with all required credentials (see Environment Variables section above).

### Step 5: Initialize Database

```bash
python -c "from app.database import engine; from app import models; models.Base.metadata.create_all(bind=engine)"
```

### Step 6: Run CLI or API

**To run the CLI**:
```bash
python cli.py
```

**To run the FastAPI server**:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then navigate to `http://localhost:8000/docs` for interactive API documentation.

---

## 🚀 Usage Examples

### Example 1: Basic CLI Run

```bash
$ python cli.py

==================================================
      Skanjo AI Outreach Pipeline - CLI          
==================================================

Enter the seed domain (e.g., hubspot.com): hubspot.com

[Stage 1] Finding lookalike companies for hubspot.com...
  -> Found 5 domains: intercom.com, pipedrive.com, zendesk.com, freshsales.com, zoho.com

[Stage 2] Searching & Enriching Decision Makers (Prospeo)...
  Found 8 decision makers at intercom.com
  Found 6 decision makers at pipedrive.com
  Found 7 decision makers at zendesk.com
  Found 5 decision makers at freshsales.com
  Found 4 decision makers at zoho.com
  -> Successfully enriched 30 leads.
  -> 28 leads have verified emails ready for outreach.

==================================================
                SAFETY CHECKPOINT                 
==================================================
 - Eoghan Casey (intercom.com) -> eoghan@intercom.io
 - Helen Morrow (pipedrive.com) -> helen@pipedrive.com
 - Jelle Houtzager (zendesk.com) -> jelle@zendesk.com
 ...
==================================================

Do you want to send outreach emails to these leads? (y/n): y

[Stage 3] Sending Outreach Emails via Brevo...
  -> Sending to eoghan@intercom.io...
  Email successfully queued for eoghan@intercom.io
  ...

✅ Pipeline Complete! Successfully sent 28 emails.
```

### Example 2: Stopping at Checkpoint

```bash
Do you want to send outreach emails to these leads? (y/n): n

🛑 Emails cancelled. Pipeline safely stopped at checkpoint.
```

### Example 3: Using FastAPI

```python
# Start the server
# uvicorn app.main:app --reload

# Test the Prospeo endpoint
import httpx

async with httpx.AsyncClient() as client:
    response = await client.get("http://localhost:8000/test-prospeo/?domain=hubspot.com")
    results = response.json()
    for test in results:
        print(f"Test {test['test']}: Status {test['status']}")
```

---

## 🔍 How It Works (Detailed Flow)

### 1. User Input & Initialization
- CLI prompts user for seed domain
- Creates database record for pipeline run
- Ensures database tables exist

### 2. Stage 1: Ocean.io Lookalike Discovery
- Sends seed domain to Ocean.io API
- Receives up to 5 similar companies
- Stores companies in database

### 3. Stage 2: Prospeo Lead Generation
- For each lookalike company:
  - **Search Phase**: Finds decision-makers by title
  - **Extraction**: Extracts person objects from API response
  - **Enrichment Phase**: Retrieves verified emails for each person
  - **Parsing**: Handles nested email objects and data formats
  - **Validation**: Only keeps leads with verified email addresses
- Stores all enriched leads in database

### 4. Safety Checkpoint
- Displays all leads with email addresses
- Prompts user for approval
- Allows user to cancel before sending emails

### 5. Stage 3: Brevo Email Outreach (Conditional)
- Only executes if user approves
- Sends personalized email to each lead
- Tracks email delivery status
- Updates pipeline run status to "completed_emails_sent"

### 6. Cleanup & Logging
- Closes database connection
- Handles exceptions and logs failures
- Updates final pipeline status

---

## ⚠️ Error Handling & Resilience

### Retry Logic
- **Prospeo**: 3 attempts with exponential backoff on rate limits
- **Rate Limiting**: Respects 1.2-2.5 second delays between requests
- **Timeouts**: 15-20 second timeouts on HTTP requests

### Validation
- Checks for required API keys before execution
- Validates extracted data structures
- Handles nested and malformed API responses
- Gracefully handles empty result sets

### Safety Features
- Manual checkpoint before sending emails
- Database transaction management
- Exception handling with meaningful error messages
- Status tracking for debugging

---

## 📊 Data Flow Diagram

```
User Input (Domain)
        │
        ▼
    CLI Entry
        │
        ▼
Create PipelineRun
        │
        ▼
┌──────────────────────────┐
│   STAGE 1: Ocean.io      │
│  Find Lookalikes         │
└──────────────────────────┘
        │
        ▼
    Store Companies
        │
        ▼
┌──────────────────────────┐
│  STAGE 2: Prospeo        │
│  Search & Enrich         │
└──────────────────────────┘
        │
        ▼
    Store Leads
        │
        ▼
    Display List
        │
        ▼
    User Approves?
        │
   ┌────┴────┐
   │ No      │ Yes
   │         │
   ▼         ▼
Stop    ┌──────────────────────────┐
        │  STAGE 3: Brevo          │
        │  Send Emails             │
        └──────────────────────────┘
                │
                ▼
        Mark Emails Sent
                │
                ▼
        Update Status
                │
                ▼
            Complete
```

---

## 🐛 Troubleshooting

### Issue: `OCEAN_API_KEY not set`
**Solution**: Check `.env` file has `OCEAN_API_KEY` and it's correctly formatted

### Issue: `No lookalikes found. Pipeline stopped.`
**Solution**: Verify seed domain is valid and has lookalikes in Ocean.io database

### Issue: `Rate limited at {domain}, retrying...`
**Solution**: Normal behavior - pipeline automatically retries after 2.5 seconds

### Issue: Database connection error
**Solution**: Verify `DATABASE_URL` in `.env` points to running PostgreSQL instance

### Issue: Emails not arriving
**Solution**: Check BREVO_API_KEY is valid and SENDER_EMAIL matches verified sender in Brevo

---

## 📝 Logging & Monitoring

The CLI provides console output showing:
- Pipeline stage progress
- Number of results at each stage
- Lead information before sending
- Email delivery confirmations
- Error messages with context
- Final completion status

All pipeline runs are logged to the database for auditing and analytics.

---

## 🔄 Future Enhancements

Potential improvements for future versions:
- [ ] Batch processing for multiple seed domains
- [ ] Email tracking and open rates integration
- [ ] Lead filtering by company size, industry, funding
- [ ] A/B testing for email content
- [ ] Webhook integrations with CRM systems
- [ ] Dashboard for pipeline analytics
- [ ] Advanced scheduling and automation

---

## 📄 License

Not specified - add your license information here.

---

## 👥 Author & Support

Created as part of Skanjo AI Outreach Platform.

For issues or questions, refer to API documentation at `http://localhost:8000/docs` when server is running.

---

## ✅ Checklist Before Running

- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] `.env` file created with all required API keys
- [ ] PostgreSQL database set up and running
- [ ] `DATABASE_URL` environment variable configured
- [ ] Ocean.io, Prospeo, and Brevo API keys obtained
- [ ] Sender email verified in Brevo
- [ ] Virtual environment activated
- [ ] Can connect to database successfully

---

**Last Updated**: June 2026
