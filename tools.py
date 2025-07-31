import json
import re
from langchain.tools import tool
from twilio.rest import Client

# Add this new tool function to tools.py
@tool
def connect_lead_to_agent(chat_history: list) -> str:
    """
    Finds the customer's phone number from the chat history, emails the history to the agent,
    and then connects the customer to the agent via a phone call.
    - chat_history: The list of chat messages from the conversation.
    """
    # --- Part 1: Find the customer's phone number from the history ---
    customer_phone_number = None
    history_text = " ".join([str(msg) for msg in chat_history])

    # Regex to find a 10-digit Indian phone number
    match = re.search(r'\b(91|0)?[6-9][0-9]{9}\b', history_text)

    if match:
        # Format number to E.164 for Twilio (e.g., +919876543210)
        num_str = match.group(0)
        if len(num_str) == 10:
            customer_phone_number = f"+91{num_str}"
        elif len(num_str) == 11 and num_str.startswith('0'):
             customer_phone_number = f"+91{num_str[1:]}"
        elif len(num_str) == 12 and num_str.startswith('91'):
             customer_phone_number = f"+{num_str}"

    if not customer_phone_number:
        return "Error: Could not find the customer's phone number in the chat history. Please ask the user for their 10-digit phone number."

    # --- Part 2: Email and Call Logic (This part stays the same) ---
    try:
        # (The existing logic for emailing and calling goes here)
        agent_email = os.environ.get('GMAIL_USER')
        formatted_history = "\n".join([str(msg) for msg in chat_history])
        email_subject = "Incoming Lead Call & Chat History"
        email_body = f"Connecting you with a new lead ({customer_phone_number}).\n\nConversation:\n{formatted_history}"

        sender_email = os.environ['GMAIL_USER']
        app_password = os.environ['GMAIL_APP_PASSWORD']
        message = f"Subject: {email_subject}\n\n{email_body}"
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, agent_email, message.encode('utf-8'))

        account_sid = os.environ['TWILIO_ACCOUNT_SID']
        auth_token = os.environ['TWILIO_AUTH_TOKEN']
        twilio_number = os.environ['TWILIO_PHONE_NUMBER']
        agent_number = os.environ['MY_PHONE_NUMBER']
        client = Client(account_sid, auth_token)

        call = client.calls.create(
            twiml=f'<Response><Dial>{customer_phone_number}</Dial></Response>',
            to=agent_number,
            from_=twilio_number
        )
        return f"Successfully sent chat history and initiated a call to connect you with the lead at {customer_phone_number}."
    except Exception as e:
        return f"An error occurred: {e}"

import csv
from langchain.tools import tool

# Add this new tool function at the top of tools.py
@tool
def search_real_estate_listings(location: str, max_budget_lakhs: int) -> str:
    """
    Searches a CSV file for real estate listings based on location and maximum budget. 
    Returns a formatted string of matching properties.
    """
    results = []
    try:
        with open('jaipur_properties.csv', mode='r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Check if location matches and price is within budget
                if location.lower() in row['location'].lower() and int(row['price_lakhs']) <= max_budget_lakhs:
                    results.append(
                        f"- Found: {row['property_type']} in {row['location']} ({row['sqft']} sqft) for {row['price_lakhs']} Lakhs. "
                        f"Contact {row['contact_person']} at {row['contact_phone']}."
                    )
        
        if not results:
            return f"I'm sorry, I couldn't find any properties in {location} within your budget of {max_budget_lakhs} Lakhs."
        
        return "\n".join(results)
    except FileNotFoundError:
        return "Error: The property listings database could not be found."
    except Exception as e:
        return f"An error occurred while searching: {e}"


# ... keep your existing update_google_sheet and send_email_alert tools below ...
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import smtplib
import os
from langchain.tools import tool

# --- Google Sheet Tool ---
@tool
def update_google_sheet(name: str, phone: str, location: str, budget_lakhs: int, timeline: str, loan_preapproved: str, property_type: str) -> str:
    """
    Saves the collected lead information to a Google Sheet. Use this ONLY when you have ALL the required information.
    """
    lead_data = locals() # Creates a dictionary from the function arguments
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
        # This code reads the credentials from the environment variable on Render
        json_creds = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        dict_creds = json.loads(json_creds)
        creds = ServiceAccountCredentials.from_json_keyfile_name_dict(dict_creds, scope)
        client = gspread.authorize(creds)
        
        sheet = client.open("RealEstateLeads").worksheet("Leads")
        
        row_data = [
            lead_data.get('name', 'N/A'),
            lead_data.get('phone', 'N/A'),
            lead_data.get('location', 'N/A'),
            lead_data.get('budget_lakhs', 'N/A'),
            lead_data.get('timeline', 'N/A'),
            lead_data.get('loan_preapproved', 'N/A'),
            lead_data.get('property_type', 'N/A'),
        ]
        sheet.append_row(row_data)
        return "Successfully updated the Google Sheet."
    except Exception as e:
        print(f"Error updating Google Sheet: {e}")
        return f"Failed to update Google Sheet. Error: {e}"

# --- Email Alert Tool ---
@tool
def send_email_alert(name: str, phone: str, location: str, budget_lakhs: int, timeline: str, loan_preapproved: str, property_type: str) -> str:
    """
    Sends an email alert to the real estate agent with the new lead's details. Use this ONLY AFTER successfully saving to the Google Sheet.
    """
    lead_data = locals()
    try:
        # Your email sending logic here (it's the same as before)
        sender_email = os.environ['GMAIL_USER']
        app_password = os.environ['GMAIL_APP_PASSWORD']
        receiver_email = "realestate.agent@example.com" # CHANGE THIS

        subject = f"New Real Estate Lead: {lead_data.get('name', 'N/A')}"
        body = f"""A new lead has been qualified!\n\nName: {lead_data.get('name', 'N/A')}\nPhone: {lead_data.get('phone', 'N/A')}\nLocation: {lead_data.get('location', 'N/A')}\nBudget: {lead_data.get('budget_lakhs', 'N/A')} Lakhs\nTimeline: {lead_data.get('timeline', 'N/A')}\nPre-approved for Loan: {lead_data.get('loan_preapproved', 'N/A')}\nProperty Type: {lead_data.get('property_type', 'N/A')}"""
        message = f"Subject: {subject}\n\n{body}"

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, receiver_email, message)
        return "Successfully sent an email alert."
    except Exception as e:
        print(f"Error sending email: {e}")
        return f"Failed to send email alert. Error: {e}"