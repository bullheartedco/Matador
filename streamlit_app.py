# Matador: Streamlit App for Local Patron & Competitor Analysis
import streamlit as st
import requests
from openai import OpenAI
import json
from bs4 import BeautifulSoup

# ---------- CONFIG ----------
st.set_page_config(page_title="Matador: Local Audience Profiler", layout="wide")

# ---------- OPENAI CLIENT ----------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------- APP HEADER ----------
st.title("💃🏻 Matador")
st.subheader("Command the Crowd.")
st.write("Enter up to 5 US ZIP codes to generate local audience personas and analyze competitive restaurant brands.")

# ---------- INPUT ----------
zip_codes_input = st.text_input("Enter up to 5 ZIP Codes, separated by commas")
user_notes = st.text_area("Add any known local insights, cultural notes, or behaviors (optional)")
mode = st.radio("Choose persona generation mode:", ["Cumulative (combined)", "Individual (per ZIP)"])

# Google-Aligned Service Styles
service_style_map = {
    "Full Service": ["restaurant", "casual_dining", "fine_dining"],
    "Fast Casual": ["restaurant", "meal_takeaway"],
    "Quick Serve (QSR)": ["fast_food", "meal_takeaway"],
    "Café / Coffee Shop": ["cafe", "coffee_shop"],
    "Bakery": ["bakery"],
    "Bar / Pub": ["bar", "pub"],
    "Buffet": ["buffet"],
    "Food Truck": ["food_truck"]
}

selected_service_styles = st.multiselect(
    "Select Service Style(s):",
    options=list(service_style_map.keys())
)

# Expanded Cuisine Types
cuisine_styles = st.multiselect(
    "Select Cuisine Type(s):",
    [
        "Mexican", "Chinese", "Japanese", "Italian", "Thai", "Vietnamese",
        "Indian", "American", "Korean", "Mediterranean", "Seafood",
        "Barbecue", "Vegan", "Vegetarian", "Burgers", "Pizza", "Coffee",
        "Bakery", "Sushi", "Middle Eastern", "Caribbean", "French", "Greek",
        "Soul Food", "Southern", "German", "Cuban", "Hawaiian", "Brazilian",
        "Spanish", "Turkish", "African", "Tapas", "Steakhouse", "Hot Pot"
    ]
)

competitor_mode = st.radio("Choose how to analyze competitors:", ["Auto via Google Places", "Manual Entry"])
manual_competitors = []

if competitor_mode == "Manual Entry":
    with st.expander("Add Manual Competitor Info"):
        for i in range(3):
            name = st.text_input(f"Competitor {i+1} Name", key=f"manual_name_{i}")
            website = st.text_input(f"Competitor {i+1} Website", key=f"manual_site_{i}")
            multi_unit = st.radio(f"Is {name} Multi-Unit?", ["Yes", "No"], key=f"mu_{i}") if name else ""
            if name:
                manual_competitors.append({
                    "name": name,
                    "website": website,
                    "multi_unit": multi_unit
                })

# ---------- DATA FUNCTIONS ----------
def build_patron_prompt(zip_codes, user_notes, mode):
    return f"""
    You are an expert in psychographics, anthropology, and brand strategy.

    Based on the following data for a 10-mile radius around ZIP code(s): {', '.join(zip_codes)}
    - User Notes: {user_notes}

    Generate 3–5 audience personas with the following:
    1. Persona Name (must be a collective name like "Sun Chasers", not an individual name)
    2. Summary of their lifestyle and cultural tendencies
    3. Archetypal opportunity (what they're psychologically drawn to; choose 1 of the 12 Jungian archetypes but renamed as: Citizen, Sage, Rebel, Lover, Creator, Explorer, Innocent, Magician, Hero, Jester, Caregiver, Sovereign)
    4. Motivators (emotional + behavioral drivers)
    5. 2–3 influenced secondary groups
    6. 5 brands they love that reflect their values
    7. Estimated prevalence (% of total population they represent)
    """

def get_website_text(url):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.get_text(separator=' ', strip=True)
    except Exception as e:
        return f"Error fetching website content: {e}"

def analyze_brand_with_gpt(name, website_text, is_multi_unit):
    prompt = f"""
    You are a brand strategist.

    Analyze the following restaurant brand based on their website content.

    Restaurant Name: {name}
    Multi-Unit: {is_multi_unit}

    Website Content:
    {website_text[:3000]}

    Provide:
    - Tone of Voice
    - 3 Personality Traits
    - Core Message or Brand Angle
    - What they promote most (e.g., ingredients, culture, price, speed)
    - Final Impression in 1 sentence
    """
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error analyzing brand: {e}"

def get_lat_lon(zip_code):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={zip_code}&key={st.secrets['GOOGLE_API_KEY']}"
    response = requests.get(url)
    if response.status_code == 200:
        results = response.json().get("results")
        if results:
            location = results[0]["geometry"]["location"]
            return location["lat"], location["lng"]
    return None, None

def get_places_data(lat, lon, search_terms):
    keyword = "+".join(search_terms)
    nearby_url = (
        f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?"
        f"location={lat},{lon}&radius=5000&type=restaurant&keyword={keyword}"
        f"&key={st.secrets['GOOGLE_API_KEY']}"
    )
    response = requests.get(nearby_url)
    results = response.json().get("results", [])
    top_places = sorted(results, key=lambda x: x.get("user_ratings_total", 0), reverse=True)[:10]

    processed = []
    for place in top_places:
        name = place.get("name")
        rating = place.get("rating")
        count = place.get("user_ratings_total")
        place_id = place.get("place_id")
        website = ""

        detail_url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=website&key={st.secrets['GOOGLE_API_KEY']}"
        detail_response = requests.get(detail_url)
        if detail_response.status_code == 200:
            website = detail_response.json().get("result", {}).get("website", "")

        processed.append({
            "name": name,
            "rating": rating,
            "review_count": count,
            "website": website,
            "multi_unit": "Unknown"
        })
    return processed
