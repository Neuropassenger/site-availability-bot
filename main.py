import requests
import sqlite3
import time
import telebot
from threading import Thread

API_TOKEN = '7099691746:AAGNOT4EJ3qaZf7YDL_EB47pwmd2bsPS4bc'
bot = telebot.TeleBot(API_TOKEN)

def init_db():
    conn = sqlite3.connect('sites.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS monitored_sites
                 (domain TEXT PRIMARY KEY, status TEXT, downtime_start REAL, chat_id INTEGER)''')
    conn.commit()
    conn.close()

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
            message = f"✅ {domain} is UP again after {downtime} seconds of downtime"
            downtime_start = None
        else:
            message = f"✅ {domain} is UP"

        bot.send_message(chat_id, message)
        c.execute('UPDATE monitored_sites SET status=?, downtime_start=? WHERE domain=?', (status, downtime_start, domain))
        conn.commit()

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Welcome! To start monitoring a website, add this bot to a group with the website domain as the group title or send the domain directly to this bot.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    domain = message.text.strip()
    if domain:  # You should implement a more robust domain validation here
        conn = sqlite3.connect('sites.db')
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO monitored_sites (domain, status, downtime_start, chat_id) VALUES (?, ?, ?, ?)',
                  (domain, 'UNKNOWN', None, message.chat.id))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"Monitoring started for {domain}.")

def start_monitoring():
    while True:
        monitor_sites()
        time.sleep(60)  # Check every minute

if __name__ == "__main__":
    init_db()
    Thread(target=start_monitoring).start()
    bot.polling(none_stop=True)
