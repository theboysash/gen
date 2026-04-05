import requests
import json
import time
import csv
from datetime import datetime

API_KEY = "AIzaSyDt-QOkiAg8fLRi1N4eGk2GTGGHp26pByk"

def search_businesses(query, location="Johannesburg", max_results=60):
    """
    Search using the NEW Places API (v1)
    """
    url = "https://places.googleapis.com/v1/places:searchText"
    
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.rating,places.userRatingCount"
    }
    
    all_places = []
    page_token = None

    while len(all_places) < max_results:
        body = {
            "textQuery": f"{query} in {location}",
            "pageSize": 40
        }
        
        if page_token:
            body["pageToken"] = page_token
            time.sleep(2)

        response = requests.post(url, headers=headers, json=body)
        data = response.json()

        if "error" in data:
            print(f"API error: {data['error']['message']}")
            break

        places = data.get("places", [])
        all_places.extend(places)
        print(f"Fetched {len(places)} results (total: {len(all_places)})")

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return all_places


def collect_leads(industry, location="Johannesburg"):
    print(f"\nSearching for: {industry} in {location}")
    print("=" * 50)

    places = search_businesses(industry, location)
    print(f"\nFound {len(places)} businesses.\n")

    leads = []

    for i, place in enumerate(places):
        lead = {
            "name": place.get("displayName", {}).get("text", ""),
            "address": place.get("formattedAddress", ""),
            "phone": place.get("nationalPhoneNumber", ""),
            "website": place.get("websiteUri", ""),
            "has_website": "Yes" if place.get("websiteUri") else "No",
            "rating": place.get("rating", ""),
            "total_reviews": place.get("userRatingCount", ""),
            "place_id": place.get("id", ""),
        }

        leads.append(lead)
        website_status = f"Website: {lead['website']}" if lead['website'] else "NO WEBSITE"
        print(f"[{i+1}/{len(places)}] {lead['name']} | {website_status}")

    return leads


def save_to_csv(leads, industry, location="Johannesburg"):
    if not leads:
        print("No leads to save.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    industry_slug = industry.replace(" ", "_").lower()
    filename = f"leads_{industry_slug}_{location.lower()}_{timestamp}.csv"

    fieldnames = ["name", "address", "phone", "website", "has_website",
                  "rating", "total_reviews", "place_id"]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(leads)

    print(f"\nSaved {len(leads)} leads to {filename}")
    return filename


def summarise_leads(leads):
    total = len(leads)
    no_website = sum(1 for l in leads if not l["website"])
    has_website = total - no_website

    print("\n" + "=" * 50)
    print("LEAD SUMMARY")
    print("=" * 50)
    print(f"Total businesses found : {total}")
    print(f"Have a website         : {has_website}")
    print(f"No website at all      : {no_website}  <-- easiest targets")
    print("=" * 50)


if __name__ == "__main__":
    INDUSTRY = "Real estate"
    LOCATION = "Johannesburg"

    leads = collect_leads(INDUSTRY, LOCATION)
    summarise_leads(leads)
    save_to_csv(leads, INDUSTRY, LOCATION)