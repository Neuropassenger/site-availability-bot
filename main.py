import requests
import sqlite3
import time
import telebot
from threading import Thread
import validators
import logging
from config import bot_token

bot = telebot.TeleBot(bot_token)
telebot.logger.setLevel(logging.INFO)

def init_db():
    conn = sqlite3.connect('sites.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS monitored_sites (
            domain TEXT PRIMARY KEY,
            status TEXT,
            downtime_start REAL,
            chat_id INTEGER,
            down_notification_sent BOOLEAN DEFAULT FALSE
        )
    ''')
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
    # Retrieve the current status, the start time of the downtime, and notification sent status
    c.execute('SELECT status, downtime_start, down_notification_sent FROM monitored_sites WHERE domain=?', (domain,))
    row = c.fetchone()
    previous_status, downtime_start, down_notification_sent = row if row else (None, None, False)

    if previous_status != status:
        if status == "DOWN":
            # If downtime start is not recorded, set it when first detected as DOWN
            if not downtime_start:
                downtime_start = time.time()
                c.execute('UPDATE monitored_sites SET downtime_start=?, down_notification_sent=FALSE WHERE domain=?', (downtime_start, domain))
                conn.commit()
        elif status == "UP":
            if downtime_start:
                downtime = time.time() - downtime_start
                # Send a message if the site was DOWN for more than 10 minutes
                if downtime >= 600 and down_notification_sent:
                    formatted_downtime = seconds_to_hms(downtime)
                    message = f"✅ {domain} is UP again after {formatted_downtime} of downtime."
                    bot.send_message(chat_id, message)
                # Reset the downtime start and notification sent flag after the site becomes available
                c.execute('UPDATE monitored_sites SET downtime_start=NULL, down_notification_sent=FALSE WHERE domain=?', (domain,))
                conn.commit()

    else:
        if status == "DOWN" and downtime_start:
            downtime = time.time() - downtime_start
            if downtime >= 600 and not down_notification_sent:
                # Send a notification if no notification has been sent yet after 10 minutes of downtime
                message = f"⚠️ {domain} has been DOWN for more than 10 minutes."
                bot.send_message(chat_id, message)
                # Update the notification sent flag to prevent repeated messages
                c.execute('UPDATE monitored_sites SET down_notification_sent=TRUE WHERE domain=?', (domain,))
                conn.commit()

    # Always update the status regardless of the condition above
    c.execute('UPDATE monitored_sites SET status=? WHERE domain=?', (status, domain))
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
    bot.polling(non_stop=True)
