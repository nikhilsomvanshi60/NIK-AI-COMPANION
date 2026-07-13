
import logging
import os
import smtplib

from livekit.agents import function_tool
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import asyncio
    
       
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_email(email: str) -> bool:
    """ईमेल एड्रेस को वैलिडेट करें"""
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(pattern, email) is not None

@function_tool()
async def send_email(to_email: str, subject: str, message: str, cc_email: Optional[str] = None) -> str:
    """
    Sends emails via authenticated Gmail SMTP using GMAIL_ID and APP_PASS from system env.
    
    Args:
        to_email: Primary recipient
        subject: Email subject
        message: Body content
        cc_email: CC recipient (optional)
        
    Validation:
        - Strict email format validation
        - Requires GMAIL_ID/APP_PASS in system environment variables
        
    Returns:
        str: Delivery confirmation or error
    """
    try:
        print(f"📧 Sending email to: {to_email}")
        
        # System environment variables se directly le raha hai
        GMAIL_ID = os.environ.get("GMAIL_ID")
        APP_PASS = os.environ.get("APP_PASS")
        
        if not validate_email(to_email):
            return f"❌ अमान्य प्राप्तकर्ता ईमेल: {to_email}"
            
        if cc_email and not validate_email(cc_email):
            return f"❌ अमान्य CC ईमेल: {cc_email}"
            
        if not GMAIL_ID or not APP_PASS:
            return "❌ ईमेल credentials नहीं मिले। कृपया system environment variables में GMAIL_ID और APP_PASS सेट करें।"
            
        def send_email_sync():
            msg = MIMEMultipart()
            msg['From'] = GMAIL_ID
            msg['To'] = to_email
            msg['Subject'] = subject
            
            if cc_email:
                msg['Cc'] = cc_email
                
            msg.attach(MIMEText(message, 'plain'))
            
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(GMAIL_ID, APP_PASS)
                recipients = [to_email] + ([cc_email] if cc_email else [])
                server.sendmail(GMAIL_ID, recipients, msg.as_string())
                return recipients
        
        recipients = await asyncio.create_task(asyncio.to_thread(send_email_sync))
        return f"✅ ईमेल सफलतापूर्वक भेजा गया: {', '.join(recipients)}"
    except Exception as e:
        logger.error(f"ईमेल त्रुटि: {e}")
        return f"❌ ईमेल भेजने में त्रुटि: {str(e)}"