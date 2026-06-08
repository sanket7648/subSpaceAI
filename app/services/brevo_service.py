import os
import httpx

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
# Make sure to add these to your .env file!
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "your_email@example.com") 
SENDER_NAME = os.getenv("SENDER_NAME", "Your Name")

async def send_outreach_email(to_email: str, to_name: str, company_name: str) -> bool:
    """
    Fires the transactional email via Brevo's API.
    """
    if not BREVO_API_KEY:
        print("  BREVO_API_KEY is not set!")
        return False
        
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    
    # ---------------------------------------------------------
    # YOUR EMAIL COPY
    # Feel free to change the subject and HTML content below!
    # ---------------------------------------------------------
    subject = f"Quick question about {company_name}"
    
    html_content = f"""
    <p>Hi {to_name},</p>
    <p>I was researching {company_name} and noticed the great work your team is doing.</p>
    <p>I am reaching out to see if you'd be open to connecting. I'd love to share how our platform can help streamline your processes.</p>
    <p>Best regards,<br>{SENDER_NAME}</p>
    """
    
    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html_content
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            
            # Brevo returns 201 Created or 202 Accepted on success
            if response.status_code in [201, 202]: 
                print(f"  Email successfully queued for {to_email}")
                return True
            else:
                print(f"  Brevo API Error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"  Exception sending email to {to_email}: {str(e)}")
            return False