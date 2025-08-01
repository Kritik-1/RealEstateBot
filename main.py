import os
import asyncio
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from telegram import Update
from telegram.ext import Application
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

# Import your tools
from tools import search_real_estate_listings, connect_lead_to_agent, update_google_sheet

load_dotenv()

# --- AGENT SETUP ---
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", """You are a real estate assistant. Your primary goal is to help users find properties from a database.
        **Rules:**
        1. First, you must collect the user's requirements: name, phone number, location, and budget.
        2. Once you have the location and budget, you MUST use the `search_real_estate_listings` tool. Do not answer from memory or invent properties.
        3. After providing the real listings from the tool, ask the user if they want to be connected to an agent using the `connect_lead_to_agent` tool.
        4. Finally, you can offer to save their details using the `update_google_sheet` tool."""),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)
tools = [search_real_estate_listings, connect_lead_to_agent, update_google_sheet]
llm = ChatGroq(model="llama3-8b-8192", temperature=0.2, groq_api_key=os.environ.get('GROQ_API_KEY'))
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
chat_histories = {}


# --- TELEGRAM AND WEB SERVER LOGIC ---
async def handle_telegram_update(update_data):
    """Processes a single update from Telegram."""
    user_id = update_data.get('message', {}).get('from', {}).get('id')
    user_input = update_data.get('message', {}).get('text', '')

    if not user_id or not user_input:
        return

    if user_id not in chat_histories or user_input == '/start':
        chat_histories[user_id] = []
        await application.bot.send_message(chat_id=user_id, text="Hi! I'm a real estate assistant. How can I help you find a property in Jaipur today?")
        return

    response = await agent_executor.ainvoke({
        "input": user_input,
        "chat_history": chat_histories[user_id]
    })

    chat_histories[user_id].append({"role": "user", "content": user_input})
    chat_histories[user_id].append({"role": "assistant", "content": response['output']})

    await application.bot.send_message(chat_id=user_id, text=response['output'])

async def webhook(request: Request) -> PlainTextResponse:
    """Endpoint that receives messages from Telegram."""
    await handle_telegram_update(await request.json())
    return PlainTextResponse("OK")

# The Telegram Application object
application = Application.builder().token(os.environ['TELEGRAM_BOT_TOKEN']).build()

# The Starlette ASGI app
app = Starlette(routes=[
    Route("/", endpoint=webhook, methods=["POST"]),
])