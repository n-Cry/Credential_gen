"""
Credential_gen.py
--------------------

Usage:
    This tool fetches a temporary email address (using 10MinuteMail),
    allows you to check that inbox, generates secure passwords,
    and logs important operations into a SQLite database.

Requirements:
    - Python 3.x
    - cryptography: pip install cryptography
    - requests: pip install requests
    - beautifulsoup4: pip install beautifulsoup4

TO-DO:
    - Discord webhook logs
    - Password saver
"""

import os
import sys
import subprocess
import argparse
import secrets
import string
import time
import pickle
import base64
import requests
from bs4 import BeautifulSoup
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import logging
import sqlite3
from datetime import datetime





#######################################
# _   _                 _ _           #
#| | | | __ _ _ __   __| | | ___ _ __ #
#| |_| |/ _` | '_ \ / _` | |/ _ \ '__|#
#|  _  | (_| | | | | (_| | |  __/ |   #
#|_| |_|\__,_|_| |_|\__,_|_|\___|_|   #
#                                     #
#######################################


class DBHandler(logging.Handler):  # Custom logging handler

    def __init__(self, db_path='logs.db'):
        super().__init__()
        self.db_path = db_path
        self._connect_db()
        self._create_table()

    def _connect_db(self):
        # database connection.
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
    
    # Create a table for logs if it doesnt already exist.
    def _create_table(self):
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                levelname TEXT,
                message TEXT,
                logger_name TEXT
            )
        """
        self.cursor.execute(create_table_sql)
        self.conn.commit()
    
    # Insert the log record into the database.
    def emit(self, record): 
        try:
            log_message = self.format(record)
            insert_sql = """
                INSERT INTO logs (created_at, levelname, message, logger_name)
                VALUES (?, ?, ?, ?)
            """
            self.cursor.execute(insert_sql, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                record.levelname,
                log_message,
                record.name
            ))
            self.conn.commit()
        except Exception:
            self.handleError(record)

    def close(self):
        """
        Close the database connection.
        """
        self.conn.close()
        super().close()


# Global loggers
logger = logging.getLogger("combined_script_logger")
logger.setLevel(logging.DEBUG)  # Adjust as needed (DEBUG, INFO, WARNING, etc.)

# Check to see file exists to save emails
SESSION_DIR = "temp_mail"
if not os.path.exists(SESSION_DIR):
    os.makedirs(SESSION_DIR)

# 10 minute mail email
BASE_URL = "https://10minutemail.net"

# Change it depending on prefrences of allowed characters (recommended to keep it unchanged)
PASSWORD_SET = (
    string.ascii_lowercase
    + string.ascii_uppercase
    + string.digits
    + string.punctuation
)

DISCORD_WEBHOOK = '' # Optional way to send logs to a discord webhook TO-DO





#######################################################
# _____                             _   _             #
#| ____|_ __   ___ _ __ _   _ _ __ | |_(_) ___  _ __  #
#|  _| | '_ \ / __| '__| | | | '_ \| __| |/ _ \| '_ \ #
#| |___| | | | (__| |  | |_| | |_) | |_| | (_) | | | |#
#|_____|_| |_|\___|_|   \__, | .__/_\__|_|\___/|_| |_|#
#|  _ \  ___  ___ _ __ _|___/|_|_ | |_(_) ___  _ __   #
#| | | |/ _ \/ __| '__| | | | '_ \| __| |/ _ \| '_ \  #
#| |_| |  __/ (__| |  | |_| | |_) | |_| | (_) | | | | #
#|____/ \___|\___|_|   \__, | .__/ \__|_|\___/|_| |_| #
#                      |___/|_|                       #
#######################################################

# Derive a Fernet-compatible key from the provided password and salt.
def derive_fernet_key(password: str, salt: bytes) -> bytes:
    # Uses PBKDF2-HMAC with SHA256.
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend()
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


def encrypt_data(data: bytes, password: str) -> bytes:
    """
    Encrypt the given data with a key derived from the password.
    The returned bytes have the first 16 bytes as the salt.
    """
    salt = os.urandom(16)
    key = derive_fernet_key(password, salt)
    fernet = Fernet(key)
    encrypted = fernet.encrypt(data)
    return salt + encrypted


def decrypt_data(encrypted_data: bytes, password: str) -> bytes:
    
    #Decrypt the given data, which must have the first 16 bytes as the salt.
    
    salt = encrypted_data[:16]
    actual_encrypted = encrypted_data[16:]
    key = derive_fernet_key(password, salt)
    fernet = Fernet(key)
    return fernet.decrypt(actual_encrypted)





####################
# __  __       _ _ #
#|  \/  | __ _(_) |#
#| |\/| |/ _` | | |#
#| |  | | (_| | | |#
#|_|  |_|\__,_|_|_|#
#                  #
####################


def sanitize_email(email: str) -> str:
    return email.replace("@", "_at_").replace(".", "_dot_") # Clean the email for saving


def session_filename(email: str) -> str:
    return os.path.join(SESSION_DIR, f"session_{sanitize_email(email)}.dat") # Return filename for storing session data


# Save the session's cookies to a file, optionally encrypting with encryption_key if given.
def save_session(email: str, session_obj: requests.Session, encryption_key: str = None):
    filename = session_filename(email)
    try:
        data = pickle.dumps(session_obj.cookies)
        if encryption_key is not None: # If an encryption key is provided, encrypt data
            data = encrypt_data(data, encryption_key)
        with open(filename, "wb") as f:
            f.write(data)
        logger.info(f"Session saved for {email} (file: {filename})")
    except Exception as e:
        logger.error(f"Error saving session for {email}: {e}")


# Load the session's cookies from a file, optionally decrypting with encryption_key if given.
def load_session(email: str, session_obj: requests.Session, encryption_key: str = None):
    filename = session_filename(email)
    if not os.path.exists(filename):
        raise FileNotFoundError(f"No session file found for {email}")

    with open(filename, "rb") as f:
        data = f.read()
    
    if encryption_key is not None:
        data = decrypt_data(data, encryption_key)

    cookies = pickle.loads(data)
    session_obj.cookies.update(cookies)
    logger.info(f"Session loaded for {email} (from {filename})")


# Fetch a new temp email
def get_temp_email(session: requests.Session) -> str:
    response = session.get(BASE_URL + "/")
    soup = BeautifulSoup(response.text, "html.parser")
    email_elem = soup.find("input", {"id": "fe_text"})
    if email_elem:
        email = email_elem.get("value")
        logger.info(f"Temporary Email acquired: {email}")
        return email # Return the email if found
    else:
        logger.error("Failed to retrieve temporary email from 10MinuteMail.")
        return None

# Retrieve contents of specific email from inbox
def get_email_contents(session: requests.Session, email_url: str):
    full_url = f"{BASE_URL}/{email_url.lstrip('/')}"
    logger.info(f"Fetching email content from: {full_url}")
    try:
        response = session.get(full_url)
        if response.status_code != 200:
            logger.error(f"Failed to fetch email content. HTTP Status: {response.status_code}")
            return

        soup = BeautifulSoup(response.text, "html.parser")
        email_content = None

        # Check possible container ids with the data
        for cid in ["email_content", "email_body", "mailbody"]:
            container = soup.find("div", {"id": cid})
            if container:
                email_content = container.get_text("\n", strip=True)
                logger.debug(f"Found email content in container with id='{cid}'.")
                break

        # Try class 'mailinhtml' if not found
        if not email_content:
            container = soup.find("div", class_="mailinhtml")
            if container:
                email_content = container.get_text("\n", strip=True)
                logger.debug("Found email content in 'mailinhtml' container.")
        # Retrieve all text if still not found
        if not email_content:
            logger.warning("No expected container found. Attempting fallback snippet.")
            logger.debug(response.text[:500])
            email_content = soup.get_text("\n", strip=True)
        
        if email_content:
            print("\n[Email Contents]")
            print(email_content)
            print("-" * 50)
        else:
            logger.warning("No content found in this email.")

    except Exception as e:
        logger.error(f"Error while fetching email contents: {e}")


# Check inbox for the session and display messages.
def check_inbox(session: requests.Session):
    inbox_url = BASE_URL + "/"
    try:
        response = session.get(inbox_url)
        if response.status_code != 200: # Ensure we are getting a correct response
            logger.error(f"Failed to fetch inbox. HTTP Status: {response.status_code}")
            logger.debug(f"Response snippet: {response.text[:300]}")
            return

        soup = BeautifulSoup(response.text, "html.parser")
        mail_table = soup.find("table", {"id": "maillist"})
        if not mail_table:
            logger.info("No emails found in the inbox.")
            return

        rows = mail_table.find_all("tr")[1:]  # skip header
        if not rows:
            logger.info("Inbox is empty (no new emails).")
            return

        print("\n[Inbox Emails]")
        for row in rows:
            columns = row.find_all("td")
            if len(columns) >= 3:
                # sender/link
                sender_link = columns[0].find("a")
                if sender_link:
                    sender = sender_link.get_text(strip=True)
                    email_link = sender_link.get("href", "")
                else:
                    sender = columns[0].get_text(strip=True)
                    email_link = ""

                subject = columns[1].get_text(strip=True)
                timestamp_span = columns[2].find("span")
                if timestamp_span and "title" in timestamp_span.attrs:
                    timestamp = timestamp_span["title"].strip()
                else:
                    timestamp = columns[2].get_text(strip=True)

                print(f"From    : {sender}")
                print(f"Subject : {subject}")
                print(f"Date    : {timestamp}")
                if email_link:
                    print(f"Link    : {BASE_URL}/{email_link.lstrip('/')}")
                else:
                    print("[!] No link found for this email.")
                print("-" * 50)

                # Auto-fetch the contents of each message
                if email_link:
                    get_email_contents(session, email_link)

    except Exception as e:
        logger.error(f"Error while checking the inbox: {e}")


def print_inbox(session: requests.Session, email: str, encryption_key: str = None):
    try:
        load_session(email, session, encryption_key) # Load the session from file using the key if given
    except Exception as e:
        logger.error(f"Could not load session for {email}: {e}") # Wrong password or other errors
        sys.exit(1)
    logger.info(f"Viewing inbox for {email} ...")
    check_inbox(session)






##############################################
# ____                                     _ #
#|  _ \ __ _ ___ _____      _____  _ __ __| |#
#| |_) / _` / __/ __\ \ /\ / / _ \| '__/ _` |#
#|  __/ (_| \__ \__ \\ V  V / (_) | | | (_| |#
#|_|   \__,_|___/___/ \_/\_/ \___/|_|  \__,_|#
#                                            #
##############################################


def get_picks(size: int, char_pool: str) -> list:
    return [secrets.choice(char_pool) for _ in range(size)] # Return a list of characters randomly chosen from char_pool.


# Shuffle the order of characters in the list
def shuffle(character_list: list) -> str:
    secrets.SystemRandom().shuffle(character_list)
    return ''.join(character_list) 


def pass_gen(length: int, upper: int, lower: int, num: int, special: int) -> str:
    """
    Generate a password of length 'length', ensuring that it contains at least
    the specified number of uppercase, lowercase, numeric, and special chars.
    """
    required_count = upper + lower + num + special
    if required_count > length:
        raise ValueError("Total required characters exceed the specified length.")

    password_chars = (
        get_picks(lower, string.ascii_lowercase) +
        get_picks(upper, string.ascii_uppercase) +
        get_picks(num, string.digits) +
        get_picks(special, string.punctuation) +
        get_picks(length - required_count, PASSWORD_SET)
    )
    return shuffle(password_chars)





########################
# _                    #
#| |    ___   __ _ ___ #
#| |   / _ \ / _` / __|#
#| |__| (_) | (_| \__ \#
#|_____\___/ \__, |___/#
#            |___/     #
########################


# Retrieve recent log entries from logs.db
def view_logs(limit: int = 20):
    try:
        conn = sqlite3.connect("logs.db")
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT created_at, levelname, message, logger_name "
            "FROM logs ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()

        if not rows:
            print("[!] No logs found in the database.")
            return

        print(f"[+] Showing the most recent {len(rows)} logs:")
        for r in rows:
            created, level, message, logger_name = r
            print(f"{created} [{level}] <{logger_name}>: {message}")

    except Exception as e:
        logger.error(f"Error while viewing logs: {e}")
        print(f"[-] Could not retrieve logs from database: {e}")




########################
# __  __       _       #
#|  \/  | __ _(_)_ __  #
#| |\/| |/ _` | | '_ \ #
#| |  | | (_| | | | | |#
#|_|  |_|\__,_|_|_| |_|#
#                      #
########################


def main():
    # Arguments
    parser = argparse.ArgumentParser(
        description="Combined Mail & Password Generator Script"
    )
    parser.add_argument("--generate-password", action="store_true",
                        help="Generate a secure password.")
    parser.add_argument("--generate-email", action="store_true",
                        help="Generate a temporary email (and save session).")
    parser.add_argument("--view-inbox", type=str,
                        help="View inbox messages of a previously created email.")
    parser.add_argument("--view-passwords", action="store_true",
                        help="(Placeholder) View saved passwords (not yet implemented #TO-DO).")
    parser.add_argument("--view-logs", action="store_true",
                        help="View the most recent logs from the database.")

    parser.add_argument("-l", "--length", type=int, default=8,
                        help="Length of the password (default: 8).")
    parser.add_argument("-uc", "--uppercase", type=int, default=1,
                        help="Number of uppercase letters (default: 1).")
    parser.add_argument("-lc", "--lowercase", type=int, default=1,
                        help="Number of lowercase letters (default: 1).")
    parser.add_argument("-n", "--num", type=int, default=1,
                        help="Number of digits (default: 1).")
    parser.add_argument("-sp", "--special", type=int, default=1,
                        help="Number of special characters (default: 1).")

    parser.add_argument("-s", "--save", type=str,
                        help="Encryption key to encrypt/decrypt the session file.")
    parser.add_argument("-r", "--remove-emails", action="store_true",
                        help="Remove all saved session files from the temp_mail folder.")

    args = parser.parse_args()
    #
    
    # Create DBHandler locally and add to the logger
    db_handler = DBHandler(db_path="logs.db")
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    db_handler.setFormatter(formatter)
    logger.addHandler(db_handler)
    #
    
    session = requests.Session()
    encryption_key = None

    # Remove all saved session files
    if args.remove_emails:
        count = 0
        for filename in os.listdir(SESSION_DIR):
            file_path = os.path.join(SESSION_DIR, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
                count += 1
        logger.info(f"Removed {count} session file(s) from '{SESSION_DIR}'.")
        print(f"[+] Removed {count} session file(s) from '{SESSION_DIR}'.")
        return 0

    if args.save:
        encryption_key = args.save
        logger.debug("Encryption key provided and stored locally.")

    # Generate new email
    if args.generate_email:
        temp_email = get_temp_email(session)
        if temp_email:
            save_session(temp_email, session, encryption_key)
            logger.info(f"Email generated and session saved: {temp_email}")
            print(f"[+] Email generated: {temp_email}")
        else:
            print("[-] Failed to generate temporary email.")
        return 0

    # Generate a secure password
    if args.generate_password:
        try:
            pwd = pass_gen(args.length, args.uppercase, args.lowercase, args.num, args.special)
            print(f"[+] Generated password: {pwd}")
            logger.info("Password generated successfully.")
        except ValueError as e:
            logger.error(f"Error generating password: {e}")
            print(f"[-] Error: {e}")
        return 0

    # View inbox for the provided email
    if args.view_inbox:
        print_inbox(session, args.view_inbox, encryption_key)
        return 0

    # Placeholder: View saved passwords TO-DO***
    if args.view_passwords:
        print("[!] View saved passwords is not yet implemented.")
        logger.warning("Attempted to view passwords, but not implemented.")
        return 0

    # View logs from the database
    if args.view_logs:
        view_logs(limit=20)  # show the last 20 logs
        return 0

    # If no arguments print help
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
