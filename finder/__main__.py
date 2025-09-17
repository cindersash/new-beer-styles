from __future__ import annotations

import json
import logging
import logging.handlers
import platform
import random
import smtplib
import sys
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, TypedDict, Dict, Set

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


class Beer(TypedDict):
    """Type definition for beer information."""
    name: str
    style: str
    brewery: str
    brewery_id: str


def load_sent_beers() -> Dict[str, Set[str]]:
    """Load the set of already sent beer names for each brewery."""
    try:
        with open('sent_beers.json', 'r') as f:
            data = json.load(f)
            # Convert lists back to sets
            return {brewery_id: set(beers) for brewery_id, beers in data.items()}
    except FileNotFoundError:
        return {}


def save_sent_beers(sent_beers: Dict[str, Set[str]]) -> None:
    """Save the set of sent beer names for each brewery to a file."""
    # Convert sets to lists for JSON serialization
    data = {brewery_id: list(beers) for brewery_id, beers in sent_beers.items()}
    with open('sent_beers.json', 'w') as f:
        json.dump(data, f, indent=2)


def filter_new_beers(beers: List[Beer], sent_beers: Dict[str, Set[str]], brewery_id: str) -> List[Beer]:
    """Filter out beers that have already been sent."""
    new_beers = []
    for beer in beers:
        if beer['name'] not in sent_beers.get(brewery_id, set()):
            new_beers.append(beer)
    return new_beers


def load_config() -> dict:
    """Load configuration from config.json"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error("config.json not found. Please make sure it exists in the root directory.")
        exit(1)
    except json.JSONDecodeError:
        logging.error("config.json is not a valid JSON file.")
        exit(1)


def setup_driver() -> WebDriver:
    """Setup Chrome WebDriver with anti-detection options"""
    chrome_options = Options()

    # Headless mode (using newer syntax for better compatibility)
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")

    # Anti-detection options
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    # User agent
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    ]
    chrome_options.add_argument(f"--user-agent={random.choice(user_agents)}")

    try:
        if platform.system() == "Windows":
            service = Service(ChromeDriverManager().install())
        else:
            # Use a fixed path for non-Windows systems because it will install x64 which doesn't work on raspberry pi
            service = Service("/usr/bin/chromedriver")
        web_driver = webdriver.Chrome(service=service, options=chrome_options)

        # Execute script to remove webdriver property
        web_driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        return web_driver

    except Exception as e:
        logging.error(f"Failed to setup Chrome WebDriver: {e}")
        logging.error("Make sure Chrome browser and ChromeDriver are installed on your system")
        logging.error("For Raspberry Pi: sudo apt-get install chromium-browser chromium-chromedriver")
        raise


def get_beers_from_brewery(brewery_id: str) -> List[Beer]:
    """Scrape beer information from a brewery's Untappd page using Selenium"""
    base_url = f"https://untappd.com/{brewery_id}/beer?sort=created_at_desc"
    driver = None

    try:
        driver = setup_driver()
        driver.get(base_url)

        # Wait for the page to load and for beer items to be present
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[class*='beer-item']"))
        )

        # Get the page source and parse with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, 'html.parser')

        brewery_card = soup.select_one('div[class*="name"]')
        brewery_name = brewery_card.select_one('h1').get_text(strip=True)

        beers = []
        beer_cards = soup.select('div[class*="beer-item"]')

        for card in beer_cards:
            try:
                name_elem = card.select_one('p[class*="name"]')
                style_elem = card.select_one('p[class*="style"]')

                if name_elem and style_elem:
                    beer_name = name_elem.get_text(strip=True)
                    beer_style = style_elem.get_text(strip=True)

                    beers.append({
                        'name': beer_name,
                        'style': beer_style,
                        'brewery': brewery_name,
                        'brewery_id': brewery_id
                    })
            except Exception as e:
                logging.warning(f"Error parsing beer card: {e}")
                continue

        return beers

    except Exception as e:
        logging.error(f"Error fetching data from Untappd: {e}", exc_info=True)
        return []
    finally:
        if driver:
            driver.quit()


def find_matching_beers() -> List[Beer]:
    """Find beers that match the desired styles from config"""
    config = load_config()
    brewery_ids = config.get('brewery_ids', [])

    # Don't worry about case
    desired_styles = [style.lower() for style in config.get('desired_styles', [])]

    # Load previously sent beers
    sent_beers = load_sent_beers()
    new_beers = []

    for brewery_id in brewery_ids:
        # Sleep between requests to avoid being detected as a bot
        time.sleep(random.uniform(5.0, 35.0))
        logging.info(f"Checking beers from brewery: {brewery_id}")
        beers = get_beers_from_brewery(brewery_id)
        logging.info(f"Found {len(beers)} beers from brewery {brewery_id}")

        # Filter for matching styles and new beers
        matching_beers = []
        for beer in beers:
            if any(style in beer['style'].lower() for style in desired_styles):
                matching_beers.append(beer)

        # Filter out already sent beers
        new_brewery_beers = filter_new_beers(matching_beers, sent_beers, brewery_id)
        new_beers.extend(new_brewery_beers)

        # Update sent_beers with new beers
        if new_brewery_beers:
            if brewery_id not in sent_beers:
                sent_beers[brewery_id] = set()
            sent_beers[brewery_id].update(beer['name'] for beer in new_brewery_beers)

    # Save the updated sent_beers to disk
    if new_beers:
        save_sent_beers(sent_beers)

    return new_beers


def format_beer_list(beers: List[Beer]) -> str:
    """Format the list of beers as a string."""
    beers_by_brewery = {}
    for beer in beers:
        if beer['brewery'] not in beers_by_brewery:
            beers_by_brewery[beer['brewery']] = []
        beers_by_brewery[beer['brewery']].append(beer)

    result = []
    for brewery, brewery_beers in beers_by_brewery.items():
        result.append(f"{brewery}")
        result.append("-" * len(brewery))
        for beer in brewery_beers:
            result.append(f"{beer['name']} | {beer['style']}")
        result.append("")  # Add empty line between breweries

    return "\n".join(result)


def send_email(subject: str, body: str) -> None:
    config = load_config()
    email_config = config.get("email", {})

    sender_email = email_config.get("sender")
    to_email = email_config.get("recipient")
    password = email_config.get("password")

    if not all([sender_email, password, to_email]):
        logging.error("Email configuration is incomplete. Please check your config.json file.")
        return

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, password)
            server.send_message(msg)
        logging.info("Email notification sent successfully")
    except Exception as e:
        logging.error(f"Error sending email: {e}", exc_info=True)
        raise e


def _process():
    logging.info("Searching for beers that match your desired styles...")

    # Find matching beers
    matching_beers = find_matching_beers()

    if not matching_beers:
        logging.info("No matching beers found.")
        return

    # Format the beer list for both console and email
    beer_list = format_beer_list(matching_beers)

    # Log the found beers
    logging.info("\nFound the following matching beers:")
    logging.info("=" * 50)
    for line in beer_list.split('\n'):
        if line.strip() and '|' in line:
            logging.info(line.strip())
    logging.info("=" * 50)

    # Send email
    current_date = datetime.now().strftime("%Y-%m-%d")
    send_email(f"{len(matching_beers)} New Beer Styles - {current_date}", beer_list)


def setup_logging() -> logging.Logger:
    """Configure logging to output to both console and a file."""
    # Create logs directory if it doesn't exist
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)

    # Create a logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # File handler (single file, no rotation)
    file_handler = logging.FileHandler(log_dir / 'beer_finder.log', mode='a')
    file_handler.setFormatter(formatter)

    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


def main() -> None:
    # Setup logging
    logger = setup_logging()

    try:
        _process()
        config = load_config()
        healthcheck_url = config.get("healthcheck_url")

        if healthcheck_url:
            logger.info("Sending healthcheck ping...")
            response = requests.get(healthcheck_url)
            response.raise_for_status()
            logger.info("Healthcheck successful")
        else:
            logger.warning("No healthcheck URL configured")

        logger.info("Script completed successfully")
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
