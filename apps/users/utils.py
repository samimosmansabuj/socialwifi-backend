from django.core.mail import EmailMessage

def send_otp_email(otp, recipient_email):
    email = EmailMessage(
        subject="Your OTP Code for HelpMeSpeak",
        body=f"""
        <html>
            <body>
                <p>Hello,</p>
                <p>Your OTP code is: <strong>{otp}</strong></p>
                <p>Please use this code to verify your account. If you did not request this, please ignore this email.</p>
                <br>
                <p>Thank you,<br>HelpMeSpeak Team</p>
            </body>
        </html>
        """,
        from_email="no-reply@helpmespeak.app",
        to=[recipient_email],
    )
    email.content_subtype = "html"  # Set the email content type to HTML
    email.send()