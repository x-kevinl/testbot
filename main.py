import os
import discord
from discord.ext import commands
import pytesseract
from PIL import Image
import google.generativeai as genai
import time

# Environment variables for tokens and keys
DISCORD_TOKEN = os.environ['DISCORD_TOKEN']
GOOGLE_API_KEYS = [
    os.environ['GOOGLE_API_KEY_1'],
    os.environ['GOOGLE_API_KEY_2']
]

# Index to track the current API key
api_key_index = 0

# Function to configure the Generative AI model with the next API key
def configure_next_api_key():
    global api_key_index
    api_key = GOOGLE_API_KEYS[api_key_index]
    genai.configure(api_key=api_key)
    api_key_index = (api_key_index + 1) % len(GOOGLE_API_KEYS)  # Cycle through keys

# Initialize the first API key
configure_next_api_key()

model = genai.GenerativeModel('gemini-1.5-pro')

# Allowed channel ID
ALLOWED_CHANNEL_ID = 1308681956451553360  # Replace with your actual channel ID

# Directory for storing user message history
if not os.path.exists("user_messages"):
    os.makedirs("user_messages")

# Rate limit settings
RATE_LIMIT_SECONDS = 10  # Set rate limit in seconds
user_last_message_time = {}

# Discord bot setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def send_in_chunks(channel, text):
    chunk_size = 1900
    chunks = [chunk + '.' if '' not in chunk else chunk for chunk in text.split('.')]
    current_chunk = ''
    for chunk in chunks:
        if len(current_chunk + chunk) <= chunk_size:
            current_chunk += chunk
        else:
            await channel.send(current_chunk.strip())
            current_chunk = chunk
    if current_chunk:
        await channel.send(current_chunk.strip())

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Restrict the bot to a specific channel
    if message.channel.id != ALLOWED_CHANNEL_ID:
        return

    # Rate limiting
    current_time = time.time()
    last_message_time = user_last_message_time.get(message.author.id, 0)
    if current_time - last_message_time < RATE_LIMIT_SECONDS:
        await message.reply(
            f"You're sending messages too quickly! Please wait {RATE_LIMIT_SECONDS - int(current_time - last_message_time)} seconds before trying again."
        )
        return
    user_last_message_time[message.author.id] = current_time

    # Track user messages and AI responses
    user_file = f"user_messages/{message.author.name}.txt"

    if not os.path.exists(user_file):
        with open(user_file, 'w') as f:
            f.write("")  # Create file if it doesn't exist

    # Read the existing conversation history
    with open(user_file, 'r') as f:
        history = f.read()

    # Append the user's new message to the history
    with open(user_file, 'a') as f:
        f.write(f"{message.author.name}: {message.content}\n")

    # Build the input for the AI
    q = (
        f"The following is a chat history between {message.author.name} and Gemini, "
        f"an AI assistant. Please continue the conversation naturally. "
        f"Gemini always refers to itself as 'Gemini'.\n\n"
        f"{history}\n{message.author.name}: {message.content}\nGemini:"
        f"When you respond, don't include the phrase 'Gemini:' in your response, and don't include but remember previous chat history in your message."
    )

    if len(message.attachments) > 0:
        for attachment in message.attachments:
            if attachment.filename.endswith(('.png')):
                image_path = os.path.join(os.getcwd(), attachment.filename)
                await attachment.save(image_path)
                extracted_text = pytesseract.image_to_string(Image.open(image_path))
                q += (
                    f"\n{message.author.name}: (sent an image)\n"
                    f"Gemini: The following text was extracted from the image:\n{extracted_text}\n\n"
                )
                os.remove(image_path)

    # Configure the next API key for the request
    configure_next_api_key()

    # Generate response from the AI
    response = model.generate_content(q)
    content = response._result.candidates[0].content.parts[0].text

    # Append the AI's response to the history
    with open(user_file, 'a') as f:
        f.write(f"Gemini: {content}\n")

    # Send the response directly to the user in chunks
    await message.reply(content[:2000])  # Discord limits replies to 2000 characters

    # Limit history to the last 100 lines
    with open(user_file, 'r') as f:
        lines = f.readlines()
    if len(lines) > 100:
        with open(user_file, 'w') as f:
            f.writelines(lines[-100:])

    # Process commands
    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)
