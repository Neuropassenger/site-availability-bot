import requests
import sqlite3
import time
import telebot
from threading import Thread
import validators
from config import bot_token

bot = telebot.TeleBot(bot_token)

def init_db():
    conn = sqlite3.connect('sites.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS monitored_sites
                 (domain TEXT PRIMARY KEY, status TEXT, downtime_start REAL, chat_id INTEGER)''')
    conn.commit()
    conn.close()


def is_valid_domain(domain):
    """Check if the domain name is valid using the validators library."""
    return validators.domain(domain)

def pluralize(time_value, time_label):
    """Returns correctly pluralized label based on the time value."""
    if time_value == 1:
        return f"{int(time_value)} {time_label[:-1]}"  # Strip the 's' for singular
    else:
        return f"{int(time_value)} {time_label}"

def seconds_to_hms(seconds):
    """Convert seconds to hours, minutes, and seconds, with proper pluralization."""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(pluralize(hours, "hours"))
    if minutes:
        parts.append(pluralize(minutes, "minutes"))
    if seconds or not parts:  # always show seconds if no hours or minutes
        parts.append(pluralize(seconds, "seconds"))
    return " ".join(parts)

def check_site(domain):
    try:
        response = requests.get(f'http://{domain}', timeout=10)
        return "UP" if response.status_code == 200 else "DOWN"
    except requests.RequestException:
        return "DOWN"

def monitor_sites():
    conn = sqlite3.connect('sites.db')
    c = conn.cursor()
    c.execute('SELECT domain, chat_id FROM monitored_sites')
    domains = c.fetchall()
    for domain, chat_id in domains:
        status = check_site(domain)
        update_site_status(domain, status, chat_id, conn)
    conn.close()

def update_site_status(domain, status, chat_id, conn):
    c = conn.cursor()
    c.execute('SELECT status, downtime_start FROM monitored_sites WHERE domain=?', (domain,))
    row = c.fetchone()
    previous_status, downtime_start = row if row else (None, None)

    if previous_status != status:
        if status == "DOWN":
            downtime_start = time.time()
            message = f"⚠️ {domain} is DOWN"
        elif status == "UP" and downtime_start:
            downtime = int(time.time() - downtime_start)
            formatted_downtime = seconds_to_hms(downtime)
            message = f"✅ {domain} is UP again after {formatted_downtime}"
            downtime_start = None
        else:
            message = f"✅ {domain} is UP"

        bot.send_message(chat_id, message)
        c.execute('UPDATE monitored_sites SET status=?, downtime_start=? WHERE domain=?', (status, downtime_start, domain))
        conn.commit()

@bot.message_handler(content_types=['new_chat_members'])
def new_member(message):
    new_members = message.new_chat_members
    if any(member.id == bot.get_me().id for member in new_members):
        domain = message.chat.title.strip()
        if is_valid_domain(domain):
            conn = sqlite3.connect('sites.db')
            c = conn.cursor()
            c.execute('INSERT OR IGNORE INTO monitored_sites (domain, status, downtime_start, chat_id) VALUES (?, ?, ?, ?)',
                      (domain, 'UNKNOWN', None, message.chat.id))
            conn.commit()
            conn.close()
            bot.send_message(message.chat.id, f"Monitoring started for {domain}.")
        else:
            bot.send_message(message.chat.id, "Invalid domain name provided.")

def start_monitoring():
    while True:
        monitor_sites()
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    init_db()
    Thread(target=start_monitoring).start()
    bot.polling(none_stop=True)
