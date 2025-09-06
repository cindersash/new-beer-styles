from __future__ import annotations

import json
import platform
import random
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, TypedDict

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


def load_config() -> dict:
    """Load configuration from config.json"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Error: config.json not found. Please make sure it exists in the root directory.")
        exit(1)
    except json.JSONDecodeError:
        print("Error: config.json is not a valid JSON file.")
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
        print(f"Failed to setup Chrome WebDriver: {e}")
        print("Make sure Chrome browser and ChromeDriver are installed on your system")
        print("For Raspberry Pi: sudo apt-get install chromium-browser chromium-chromedriver")
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
                        'brewery': brewery_name
                    })
            except Exception as e:
                print(f"Error parsing beer card: {e}")
                continue

        return beers

    except Exception as e:
        print(f"Error fetching data from Untappd: {e}")
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

    matching_beers = []

    for brewery_id in brewery_ids:
        # Sleep between requests to avoid being detected as a bot
        time.sleep(random.randint(1, 5))
        print(f"Checking beers from brewery: {brewery_id}")
        beers = get_beers_from_brewery(brewery_id)
        print(f"Found {len(beers)} beers from brewery {brewery_id}")

        for beer in beers:
            if any(style in beer['style'].lower() for style in desired_styles):
                matching_beers.append(beer)

    return matching_beers


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
        print("Email configuration is incomplete. Please check your .env file.")
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
        print("\nEmail sent successfully!")
    except Exception as e:
        print(f"\nError sending email: {e}")


def main() -> None:
    print("Searching for beers that match your desired styles...\n")

    # Load configuration
    config = load_config()

    # Find matching beers
    matching_beers = find_matching_beers()

    if not matching_beers:
        print("No matching beers found.")
        return

    # Format the beer list for both console and email
    beer_list = format_beer_list(matching_beers)

    # Print to console
    print("\nFound the following matching beers:")
    print("=" * 50)
    print(beer_list)
    print("\n" + "=" * 50)

    # Send email
    current_date = datetime.now().strftime("%Y-%m-%d")
    send_email(f"{len(matching_beers)} New Beer Styles - {current_date}", beer_list)

    print("\nDone!")


if __name__ == "__main__":
    main()
