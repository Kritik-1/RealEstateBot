from typing import Optional, List
import os
import csv
import re
import smtplib
import json
from langchain.tools import tool
from twilio.rest import Client
import gspread
from oauth2client.service_account import ServiceAccountCredentials

@tool
def search_real_estate_listings(location: str, max_budget_lakhs: str, property_type: Optional[str] = None) -> str:
    """
    Searches a database for real estate listings based on location, maximum budget, and property type (e.g., '2BHK Apartment').
    """
    if not max_budget_lakhs or not any(char.isdigit() for char in max_budget_lakhs):
        return "I cannot search for properties without a budget. Please ask the user for their budget first."

    # Normalize budgets like "1.2cr", "1 cr", "120 l", "120 lakhs" to lakhs (int)
    try:
        text = max_budget_lakhs.strip().lower().replace(" ", "")
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
        if not match:
            raise ValueError("no number")
        number = float(match.group(1))
        # Decide unit
        is_crore_explicit = ("cr" in text) or ("crore" in text)
        is_lakh_explicit = ("lakh" in text) or ("lakhs" in text) or (re.search(r"\b(l|lac)s?\b", text) is not None)

        if is_crore_explicit:
            budget_int = int(round(number * 100))  # 1 cr = 100 lakhs
        elif not is_lakh_explicit and (number <= 10 or "." in text):
            # Heuristic: small numbers or decimals without explicit unit are usually in crores
            budget_int = int(round(number * 100))
        else:
            budget_int = int(round(number))  # assume already in lakhs
    except Exception:
        return "Error: The budget provided was not a valid number. Please ask for a budget like '80 lakhs' or '1.2 cr'."

    results = []
    try:
        with open('jaipur_properties.csv', mode='r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Check if location matches (tolerant to phrases like 'near jagatpura') and price within budget
                provided_loc = location.lower().strip()
                provided_loc = re.sub(r"\b(near|in|around|at)\b\s*", "", provided_loc)
                row_loc = row['location'].lower().strip()
                location_match = (
                    (provided_loc and provided_loc in row_loc) or
                    (row_loc and row_loc in provided_loc)
                )
                budget_match = int(row['price_lakhs']) <= budget_int
                # New: Check if property type matches, if provided (robust matching)
                type_match = True  # Default to True if no type is specified
                if property_type:
                    requested = property_type.lower()
                    row_type = row['property_type'].lower()
                    # Match on bhk count regardless of wording
                    req_bhk = re.search(r"(\d)\s*bhk", requested)
                    row_bhk = re.search(r"(\d)\s*bhk", row_type)
                    bhk_ok = True
                    if req_bhk and row_bhk:
                        bhk_ok = req_bhk.group(1) == row_bhk.group(1)
                    # Treat apartment/flat synonyms as equal
                    synonyms_ok = True
                    if "apartment" in requested or "flat" in requested:
                        synonyms_ok = ("apartment" in row_type) or ("flat" in row_type)
                    type_match = bhk_ok and synonyms_ok

                if location_match and budget_match and type_match:
                    results.append(
                        f"- Found: {row['property_type']} in {row['location']} for {row['price_lakhs']} Lakhs. Contact {row['contact_person']} at {row['contact_phone']}."
                    )

        if not results:
            return f"No properties found matching your criteria (Location: {location}, Budget: under {budget_int} Lakhs, Type: {property_type or 'Any'})."

        return "Here are the properties I found:\n" + "\n".join(results)
    except Exception as e:
        return f"An error occurred while searching: {e}"
    
@tool
def connect_lead_to_agent(chat_history: list) -> str:
    """
    Finds the customer's phone number from the chat history, emails the history to the agent,
    and then connects the customer to the agent via a phone call.
    """
    customer_phone_number = None

    # Flatten chat history whether it's a list of dicts ({role, content}) or plain strings
    try:
        parts: List[str] = []
        for item in chat_history:
            if isinstance(item, dict):
                content = item.get("content") or item.get("text") or ""
                parts.append(str(content))
            else:
                parts.append(str(item))
        history_text = " \n".join(parts)
    except Exception:
        history_text = str(chat_history)

    # Find Indian mobile numbers in various formats: +91 9XXXXXXXXX, 0 9XXXXXXXXX, 9XXXXXXXXX
    phone_match = re.search(r'(?:\+?91[\s-]*)?(?:0[\s-]*)?([6-9][0-9]{9})', history_text)

    if phone_match:
        ten_digits = phone_match.group(1)
        customer_phone_number = f"+91{ten_digits}"

    # Even if we do not find the customer's number, we will proceed to call the owner's number
    # as requested, so the owner can handle the lead manually.

    try:
        agent_email = os.environ.get('GMAIL_USER')
        # Use the flattened history for the email as well; if the caller passed a
        # single combined transcript line, prefer that for readability.
        formatted_history = history_text
        if isinstance(chat_history, list) and len(chat_history) == 1 and isinstance(chat_history[0], str):
            formatted_history = chat_history[0]

        # If we still haven't extracted a phone, try again on the formatted transcript
        if not customer_phone_number:
            retry_match = re.search(r'(?:\+?91[\s-]*)?(?:0[\s-]*)?([6-9][0-9]{9})', formatted_history)
            if retry_match:
                customer_phone_number = f"+91{retry_match.group(1)}"

        email_subject = "Incoming Lead Call & Chat History"
        safe_num = customer_phone_number if customer_phone_number else "not provided"
        safe_history = formatted_history if formatted_history.strip() else "No transcript captured."
        email_body = f"Connecting you with a new lead ({safe_num}).\n\nConversation:\n{safe_history}"

        sender_email = os.environ['GMAIL_USER']
        app_password = os.environ['GMAIL_APP_PASSWORD']
        message = f"Subject: {email_subject}\n\n{email_body}"
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, agent_email, message.encode('utf-8'))

        account_sid = os.environ['TWILIO_ACCOUNT_SID']
        auth_token = os.environ['TWILIO_AUTH_TOKEN']
        twilio_number = os.environ['TWILIO_PHONE_NUMBER']
        # All calls should go to the owner's number (verified on Twilio). If env not set, default to provided.
        owner_number = os.environ.get('MY_PHONE_NUMBER', '+918239794674')
        client = Client(account_sid, auth_token)

        # Place the call to the OWNER always
        call = client.calls.create(
            twiml='<Response><Say>New real estate lead from your Telegram assistant. Please check the chat for details and call them back.</Say></Response>',
            to=owner_number,
            from_=twilio_number
        )
        dest = owner_number
        return f"Successfully sent chat history and initiated a call to your number {dest}. Call SID: {call.sid}, status: {call.status}."
    except Exception as e:
        return f"An error occurred: {e}"

@tool
def update_google_sheet(name: str, phone: str, location: str, budget_lakhs: int, timeline: str, loan_preapproved: str, property_type: str) -> str:
    """Saves the collected lead information to a Google Sheet. Use this ONLY when you have ALL the required information."""
    lead_data = locals()
    try:
        scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open("RealEstateLeads").worksheet("Leads")
        row_data = [lead_data.get(k, 'N/A') for k in ['name', 'phone', 'location', 'budget_lakhs', 'timeline', 'loan_preapproved', 'property_type']]
        sheet.append_row(row_data)
        return "Successfully updated the Google Sheet."
    except Exception as e:
        return f"Failed to update Google Sheet. Error: {e}"

@tool
def enrich_listing_details(listing_summary: str) -> str:
    """Takes a short listing summary (e.g., a single '- Found:' line) and returns a professional, enriched description with plausible amenities, nearby landmarks, connectivity, and lifestyle notes. This is templated content; do not invent prices or contacts beyond what is provided in the summary."""
    try:
        base = listing_summary.strip()
        if not base:
            return "I need a listing summary line to enrich."
        extras = (
            "Amenities: Clubhouse, gym, landscaped gardens, children's play area, 24x7 security, power backup.\n"
            "Connectivity: Quick access to major roads, daily convenience stores, schools, and hospitals within a 2–5 km radius.\n"
            "Lifestyle: Well-ventilated home with ample natural light; ideal for families seeking a peaceful yet central neighborhood."
        )
        return f"{base}\n\n{extras}"
    except Exception as e:
        return f"Could not enrich details: {e}"