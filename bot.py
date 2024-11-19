import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import subprocess
import time
import os
import requests

# Bot Token and Owner ID define karein
API_TOKEN = '8156991393:AAErGESkJko3F_uMk-i4BJ1CtScdg7ENYOU'
OWNER_ID = 5443679321

# Bot Initialize karte hain
bot = telebot.TeleBot(API_TOKEN)
authorized_users = {OWNER_ID: float('inf')}  # Owner ID by default authorized hoga

# PDF aur Video links ko global define karen
pdf_links = []
video_links = []
selected_quality = None  # Quality selection store karne ke liye

# Helper function to check authorization
def is_authorized(user_id):
    return user_id in authorized_users and (authorized_users[user_id] > time.time())

# /start command
@bot.message_handler(commands=['start'])
def start_handler(message):
    user_id = message.from_user.id
    if not is_authorized(user_id):
        bot.reply_to(message, "Unauthorized Access!")
        return

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("TXT to VID", callback_data="txt_to_vid"))
    bot.send_message(message.chat.id, "Select an option:", reply_markup=markup)

# /addid command (owner only)
@bot.message_handler(commands=['addid'])
def addid_handler(message):
    user_id = message.from_user.id
    if user_id != OWNER_ID:
        bot.reply_to(message, "Unauthorized Access!")
        return

    msg = bot.reply_to(message, "Enter user ID for authorization:")
    bot.register_next_step_handler(msg, process_user_id)

def process_user_id(message):
    try:
        new_user_id = int(message.text)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("1 Month", callback_data=f"auth_{new_user_id}_1M"),
                   InlineKeyboardButton("2 Months", callback_data=f"auth_{new_user_id}_2M"),
                   InlineKeyboardButton("5 Months", callback_data=f"auth_{new_user_id}_5M"),
                   InlineKeyboardButton("1 Year", callback_data=f"auth_{new_user_id}_1Y"))
        bot.send_message(message.chat.id, "Select authorization duration:", reply_markup=markup)
    except ValueError:
        bot.reply_to(message, "Invalid ID format. Please enter a valid numeric ID.")

# Callback handler for authorizing users
@bot.callback_query_handler(func=lambda call: call.data.startswith("auth_"))
def authorize_user(call):
    _, user_id, duration = call.data.split("_")
    user_id = int(user_id)
    duration_map = {"1M": 30*24*60*60, "2M": 60*24*60*60, "5M": 150*24*60*60, "1Y": 365*24*60*60}
    authorized_users[user_id] = time.time() + duration_map[duration]
    bot.answer_callback_query(call.id, "User authorized successfully!")

# Callback handler for TXT to VID button
@bot.callback_query_handler(func=lambda call: call.data == "txt_to_vid")
def txt_to_vid(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    msg = bot.send_message(call.message.chat.id, "Upload the TXT file containing URLs.")
    bot.register_next_step_handler(msg, process_txt_file)

# Process TXT file upload
def process_txt_file(message):
    global pdf_links, video_links

    if not message.document:
        bot.reply_to(message, "Please upload a TXT file.")
        return
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)

    # Reset the lists
    pdf_links = []
    video_links = []

    for line in downloaded_file.decode().splitlines():
        line = line.strip()
        if "pdf" in line:
            pdf_links.append(line)
        else:
            video_links.append(line)

    send_dl_options(message.chat.id)

# Function to send download options
def send_dl_options(chat_id):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"DL Only PDF ({len(pdf_links)})", callback_data="dl_only_pdf"),
               InlineKeyboardButton(f"DL Only Video ({len(video_links)})", callback_data="dl_only_video"),
               InlineKeyboardButton("DL Both", callback_data="dl_both"))
    bot.send_message(chat_id, "Choose download option:", reply_markup=markup)

# Download handlers
@bot.callback_query_handler(func=lambda call: call.data.startswith("dl_"))
def handle_download(call):
    global pdf_links, video_links, selected_quality
    
    if call.data == "dl_only_pdf":
        download_files(call.message.chat.id, pdf_links)
    elif call.data == "dl_only_video":
        selected_quality = None  # Reset quality selection
        ask_quality(call.message.chat.id, video_links)
    elif call.data == "dl_both":
        selected_quality = None
        ask_quality(call.message.chat.id, video_links + pdf_links)

def ask_quality(chat_id, links):
    global video_links
    video_links = links  # Set the links to download after quality selection
    markup = InlineKeyboardMarkup()
    for quality in ["240", "360", "480", "720"]:
        markup.add(InlineKeyboardButton(quality, callback_data=f"quality_{quality}"))
    bot.send_message(chat_id, "Select video quality:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("quality_"))
def quality_selected(call):
    global selected_quality
    selected_quality = call.data.split("_")[1]
    bot.delete_message(call.message.chat.id, call.message.message_id)  # Delete quality message after selection
    bot.send_message(call.message.chat.id, f"Starting downloads with quality: {selected_quality}")
    download_files(call.message.chat.id, video_links, selected_quality)

# Downloading files with ffmpeg first, fallback to yt-dlp if ffmpeg fails
def download_files(chat_id, links, quality=None):
    for url in links:
        file_name = url.split("/")[-1].split(".")[0]
        if "pdf" in url:
            # PDF Download without modification
            pdf_path = f"{file_name}.pdf"
            bot.send_message(chat_id, f"Downloading PDF: {file_name}.pdf")
            pdf_content = requests.get(url).content
            with open(pdf_path, "wb") as pdf_file:
                pdf_file.write(pdf_content)
            bot.send_document(chat_id, open(pdf_path, 'rb'))
            os.remove(pdf_path)
            continue  # Skip to the next link

        # Video download logic with fallback
        download_url = f"https://muftukmall.kashurtek.site/{url.split('/')[-2]}/hls/{quality}/main.m3u8"
        video_path = f"{file_name}.mp4"

        # Try downloading with ffmpeg
        ffmpeg_command = f'ffmpeg -i "{download_url}" -c copy "{video_path}"'
        try:
            bot.send_message(chat_id, f"Attempting download with ffmpeg: {file_name}.mp4")
            subprocess.run(ffmpeg_command, shell=True, check=True)
            bot.send_document(chat_id, open(video_path, 'rb'))
            os.remove(video_path)
        except subprocess.CalledProcessError:
            # If ffmpeg fails, try with yt-dlp
            yt_dlp_command = f'yt-dlp "{download_url}" -o "{video_path}"'
            try:
                bot.send_message(chat_id, f"ffmpeg failed, attempting with yt-dlp: {file_name}.mp4")
                subprocess.run(yt_dlp_command, shell=True, check=True)
                bot.send_document(chat_id, open(video_path, 'rb'))
                os.remove(video_path)
            except subprocess.CalledProcessError:
                # If both fail, send error message
                bot.send_message(chat_id, f"Error: Could not download {file_name} with either ffmpeg or yt-dlp.")
        time.sleep(10)

# Bot Polling
bot.polling()