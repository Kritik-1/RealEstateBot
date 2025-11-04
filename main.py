import os
import asyncio
import uvicorn
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

# --- AGENT SETUP (Using a Tool-Calling Agent with Groq) ---
# This prompt is much simpler, as the tool-calling logic is built into the model/agent.
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "You are a helpful and conversational real estate assistant for Jaipur. You must collect a user's name, phone, location, and budget before using any tools."),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("user", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

tools = [search_real_estate_listings, connect_lead_to_agent, update_google_sheet]

# NOTE: Using a more powerful model is highly recommended for tool calling.
# llama3-70b-8192 is better if available. We will try with the 8b model.
llm = ChatGroq(model="meta-llama/llama-4-maverick-17b-128e-instruct", temperature=0.2, groq_api_key=os.environ.get('GROQ_API_KEY'))

# Create the more reliable Tool-Calling Agent
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

chat_histories = {}


# --- TELEGRAM AND ASGI SERVER LOGIC ---
application = Application.builder().token(os.environ['TELEGRAM_BOT_TOKEN']).build()

async def handle_update(update_data):
    user_id = update_data.get('message', {}).get('from', {}).get('id')
    user_input = update_data.get('message', {}).get('text', '')
    if not user_id or not user_input: return
    
    if user_id not in chat_histories or user_input == '/start':
        chat_histories[user_id] = []
        if user_input == '/start':
            await application.bot.send_message(
                chat_id=user_id, 
                text=(
                    "Hi! I'm a real estate assistant for Jaipur. To get started, can you please tell me your name, "
                    "what you're looking for (e.g., 2BHK flat), your budget, and the location?"
                )
            )
            return
            
    # Add user message to history before the agent runs
    chat_histories[user_id].append({"role": "user", "content": user_input})
    
    try:
        response = await agent_executor.ainvoke({
            "input": user_input, 
            "chat_history": chat_histories[user_id]
        })
        output_message = response['output']
    except Exception as e:
        print(f"An error occurred in the agent executor: {e}")
        output_message = "I'm sorry, I encountered an error. Please try again."
    
    # Add assistant response to history after the agent runs
    chat_histories[user_id].append({"role": "assistant", "content": output_message})
    
    await application.bot.send_message(chat_id=user_id, text=output_message)

async def webhook(request: Request) -> PlainTextResponse:
    await handle_update(await request.json())
    return PlainTextResponse("OK")

# This is the main application object Uvicorn will run
app = Starlette(routes=[
    Route("/", endpoint=webhook, methods=["POST"]),
])

# This part runs once when Uvicorn starts the app
async def on_startup():
    await application.initialize()

app.add_event_handler("startup", on_startup)