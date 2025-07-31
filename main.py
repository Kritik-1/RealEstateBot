import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import json

# Import your tools
from tools import search_real_estate_listings, connect_lead_to_agent # Add other tools if needed

load_dotenv()

# 1. --- AGENT SETUP ---
# This prompt is much simpler. The model's native tool-calling ability handles the complexity.
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a helpful real estate assistant. First, collect necessary information like location and budget. Then, use the search tool to find properties. After presenting the options, you can offer to connect the user with the agent."),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

# Define the tools the agent can use
tools = [search_real_estate_listings, connect_lead_to_agent]

# Initialize the LLM
llm = ChatGroq(model="llama3-8b-8192", temperature=0.2, groq_api_key=os.environ.get('GROQ_API_KEY'))

# Create the more reliable Tool-Calling Agent
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
    response = await agent_executor.ainvoke({
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
    await update.message.reply_text("Hi! I'm a real estate assistant. How can I help you find a property in Jaipur today?")

def main():
    """Run the bot as a webhook application."""
    port = int(os.environ.get('PORT', 8000))
    application = Application.builder().token(os.environ['TELEGRAM_BOT_TOKEN']).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    webhook_url = os.environ.get("RENDER_EXTERNAL_URL", "https://your-default-render-url.onrender.com")
    
    print(f"Starting bot... Listening on port {port}. Webhook should be set to {webhook_url}")
    
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=webhook_url
    )

if __name__ == "__main__":
    main()