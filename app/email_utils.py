"""Email utilities for handling different email configurations."""

from os import getenv
from flask import current_app
from flask_mail import Mail, Message


class EmailConfig:
    """Configuration for different email types."""
    
    def __init__(self, email_type: str):
        self.email_type = email_type
        self._setup_config()
    
    def _setup_config(self):
        """Setup email configuration based on type."""
        base_username = getenv("SMTP_USER")
        base_password = getenv("SMTP_PASS")
        if self.email_type == "contact":
            self.username = base_username
            self.password = base_password
            self.sender = base_username
        elif self.email_type == "newsletter":
            self.username = base_username
            self.password = base_password
            self.sender = getenv("MAIL_NEWSLETTER")
        elif self.email_type == "notification":
            self.username = base_username
            self.password = base_password
            self.sender = getenv("MAIL_NOTIFICATIONS")
        else:
            raise ValueError(f"Unknown email type: {self.email_type}")
    
    def get_mail_instance(self):
        """Get a configured Mail instance for this email type."""
        mail = Mail()
        mail.server = getenv("MAIL_SERVER")
        mail.port = int(getenv("MAIL_PORT"))
        mail.use_tls = True
        mail.username = self.username
        mail.password = self.password
        mail.default_sender = self.sender
        
        return mail


def send_email_with_config(email_type: str, subject: str, recipients: list, 
                          text_body: str = None, html_body: str = None, 
                          reply_to: str = None) -> bool:
    """
    Send email using the appropriate configuration for the email type.
    
    Args:
        email_type: Type of email ('contact', 'newsletter', 'notification')
        subject: Email subject
        recipients: List of recipient email addresses
        text_body: Plain text body
        html_body: HTML body
        reply_to: Reply-to email address
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        config = EmailConfig(email_type)
        
        temp_config = {
            "MAIL_SERVER": getenv("MAIL_SERVER"),
            "MAIL_PORT": int(getenv("MAIL_PORT")),
            "MAIL_USE_TLS": True,
            "MAIL_USERNAME": config.username,
            "MAIL_PASSWORD": config.password,
            "MAIL_DEFAULT_SENDER": config.sender,
        }
        
        original_config = {}
        for key, value in temp_config.items():
            original_config[key] = current_app.config.get(key)
            current_app.config[key] = value
        
        msg = Message(
            subject=subject,
            recipients=recipients,
            reply_to=reply_to,
            sender=config.sender
        )
        
        if text_body:
            msg.body = text_body
        if html_body:
            msg.html = html_body
            
        current_app.mail.send(msg)
        
        for key, value in original_config.items():
            if value is not None:
                current_app.config[key] = value
            else:
                current_app.config.pop(key, None)
        
        return True
        
    except Exception as e:
        current_app.logger.error(f"Failed to send {email_type} email: {str(e)}")
        return False
