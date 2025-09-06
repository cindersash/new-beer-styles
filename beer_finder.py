import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def load_config():
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

def get_beers_from_brewery(brewery_id):
    """Scrape beer information from a brewery's Untappd page"""
    base_url = f"https://untappd.com/w/{brewery_id}/beer?sort=created_at_desc"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(base_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        beers = []
        beer_cards = soup.select('div[class*="beer-item"]')
        
        for card in beer_cards:
            try:
                name_elem = card.select_one('p[class*="beer-name"]')
                style_elem = card.select_one('p[class*="style"]')
                
                if name_elem and style_elem:
                    beer_name = name_elem.get_text(strip=True)
                    beer_style = style_elem.get_text(strip=True)
                    
                    # Get the brewery name from the page
                    brewery_name_elem = soup.select_one('div.brewery a')
                    brewery_name = brewery_name_elem.get_text(strip=True) if brewery_name_elem else "Unknown Brewery"
                    
                    beers.append({
                        'name': beer_name,
                        'style': beer_style,
                        'brewery': brewery_name
                    })
            except Exception as e:
                print(f"Error parsing beer card: {e}")
                continue
                
        return beers
        
    except requests.RequestException as e:
        print(f"Error fetching data from Untappd: {e}")
        return []

def find_matching_beers():
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

def main():
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
