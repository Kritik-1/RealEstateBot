import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Import our new tools
# Change this line

from tools import search_real_estate_listings, update_google_sheet, send_email_alert, connect_lead_to_agent
load_dotenv()

# 1. --- AGENT SETUP ---
# This prompt is much simpler because the model's tool-calling ability handles the complexity.
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a friendly and efficient real estate lead qualification assistant. Your goals are: \n1. Understand a client's needs (name, phone number, location, budget). \n2. Use the `search_real_estate_listings` tool to find properties. \n3. After providing listings, ask the user if they want to be connected to our lead agent on a call. If they agree, use the `connect_lead_to_agent` tool, passing the conversation history to it. \n4. Finally, offer to save the lead's details using your other tools."),
        MessagesPlaceholder(variable_name="chat_history"),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

# Define the tools the agent can use
tools = [search_real_estate_listings, update_google_sheet, send_email_alert, connect_lead_to_agent]

# Initialize the LLM - We need a model that is good at tool calling
# Initialize the LLM - We are now using Groq for fast, free inference
from langchain_groq import ChatGroq

llm = ChatGroq(model="llama3-8b-8192", temperature=0.5, groq_api_key=os.environ['GROQ_API_KEY'])
# Create the agent
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# Dictionary to store conversation history for each user
chat_histories = {}

# 2. --- TELEGRAM BOT SETUP ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_input = update.message.text

    # Get or create chat history for the user
    if user_id not in chat_histories:
        chat_histories[user_id] = []

    # Invoke the agent
    response = await agent_executor.ainvoke({ # Use ainvoke for async
        "input": user_input,
        "chat_history": chat_histories[user_id]
    })
    
    # Update chat history
    chat_histories[user_id].append({"role": "user", "content": user_input})
    chat_histories[user_id].append({"role": "assistant", "content": response['output']})

    # Send the agent's response back to the user
    await update.message.reply_text(response['output'])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    chat_histories[user_id] = [] # Reset history on /start
    await update.message.reply_text("Hey there! Thanks for reaching out to Jaipur Dream Homes. To best assist you, could I get your name please?")

def main():
    """Run the bot as a webhook application."""
    application = Application.builder().token(os.environ['TELEGRAM_BOT_TOKEN']).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # --- IMPORTANT ---
    # Make sure this URL exactly matches the one in your ngrok terminal!
    NGROK_URL = "https://e9fffb115b0d.ngrok-free.app" 
    
    # This print statement now runs BEFORE the server starts
    print(f"Starting bot... It will listen for messages on {NGROK_URL}")
    
    application.run_webhook(
        listen="0.0.0.0",
        port=8000,
        webhook_url=NGROK_URL
    )

if __name__ == "__main__":
    main()