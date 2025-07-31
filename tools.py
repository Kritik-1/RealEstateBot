import csv
import os
import smtplib
import re
from langchain.tools import tool
from twilio.rest import Client

@tool
def search_real_estate_listings(location: str, max_budget_lakhs: str) -> str:
    """
    Searches a database for real estate listings based on a specific location in Jaipur and a maximum budget.
    """
    # This new block cleans up the budget input
    try:
        # Extracts numbers from the budget string (e.g., "80 lakhs" -> 80)
        budget_int = int(re.search(r'\d+', max_budget_lakhs).group())
    except (ValueError, AttributeError):
        return "Error: The budget provided was not a valid number. Please ask the user for a budget like '80 lakhs'."

    results = []
    try:
        with open('jaipur_properties.csv', mode='r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Use the cleaned integer budget for comparison
                if location.lower() in row['location'].lower() and int(row['price_lakhs']) <= budget_int:
                    results.append(
                        f"- Found: {row['property_type']} in {row['location']} for {row['price_lakhs']} Lakhs. Contact {row['contact_person']} at {row['contact_phone']}."
                    )

        if not results:
            return f"No properties found in {location} within the budget of {budget_int} Lakhs."

        return "\n".join(results)
    except FileNotFoundError:
        return "Error: The property listings database could not be found."
    except Exception as e:
        return f"An error occurred while searching: {e}"

@tool
def connect_lead_to_agent(chat_history: list) -> str:
    """
    Connects a customer to the agent via a phone call. It first finds the customer's phone number from the chat history,
    sends an email with the history to the agent, and then initiates the call. Use this only when the user agrees to be connected.
    """
    # (The rest of your connect_lead_to_agent function code remains the same as before)
    # ...
    # This is a placeholder for the rest of your function logic which is already correct.
    # Make sure your full function code is here.
    # For brevity, I'm omitting the full code block you already have. If you need it again, let me know.
    # The key is just the new docstring above.
    # --- Part 1: Find the customer's phone number from the history ---
    customer_phone_number = None
    history_text = " ".join([str(msg) for msg in chat_history])
    match = re.search(r'\b(91|0)?[6-9][0-9]{9}\b', history_text)
    if match:
        num_str = match.group(0)
        if len(num_str) == 10: customer_phone_number = f"+91{num_str}"
        elif len(num_str) == 11 and num_str.startswith('0'): customer_phone_number = f"+91{num_str[1:]}"
        elif len(num_str) == 12 and num_str.startswith('91'): customer_phone_number = f"+{num_str}"
    if not customer_phone_number:
        return "Error: Could not find the customer's phone number. Please ask for it."

    # --- Part 2: Email and Call Logic ---
    try:
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
        call = client.calls.create(twiml=f'<Response><Dial>{customer_phone_number}</Dial></Response>',to=agent_number,from_=twilio_number)
        return f"Successfully sent chat history and initiated a call to connect you with the lead at {customer_phone_number}."
    except Exception as e:
        return f"An error occurred: {e}"

# ... Your other tools like update_google_sheet can remain as they are ...