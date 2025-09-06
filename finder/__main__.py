from __future__ import annotations

import json
import time
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


class Config(TypedDict):
    """Type definition for the configuration dictionary."""
    brewery_ids: List[str]
    desired_styles: List[str]


def load_config() -> Config:
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
    """Set up and return a configured Chrome WebDriver"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--proxy-server='direct://'")
    chrome_options.add_argument("--proxy-bypass-list=*")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--no-sandbox')

    # Add a user agent
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    chrome_options.add_argument(f'user-agent={user_agent}')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    return driver


def get_beers_from_brewery(brewery_id: str) -> List[Beer]:
    """Scrape beer information from a brewery's Untappd page using Selenium"""
    base_url = f"https://untappd.com/w/{brewery_id}/beer?sort=created_at_desc"
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
    desired_styles = [style.lower() for style in config.get('desired_styles', [])]

    matching_beers = []

    for brewery_id in brewery_ids:
        print(f"Checking beers from brewery: {brewery_id}")
        beers = get_beers_from_brewery(brewery_id)

        for beer in beers:
            if any(style in beer['style'].lower() for style in desired_styles):
                matching_beers.append(beer)

    return matching_beers


def main() -> None:
    print("Searching for beers that match your desired styles...\n")

    matching_beers = find_matching_beers()

    if not matching_beers:
        print("No matching beers found.")
        return

    print("\nFound the following matching beers:")
    print("-" * 50)
    for i, beer in enumerate(matching_beers, 1):
        print(f"{i}. {beer['name']}")
        print(f"   Style: {beer['style']}")
        print(f"   Brewery: {beer['brewery']}")
        print("-" * 50)


if __name__ == "__main__":
    main()
