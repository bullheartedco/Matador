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
st.write("Enter a US ZIP code to generate a local audience persona and analyze competitive restaurant brands.")

# ---------- INPUT ----------
zip_code = st.text_input("Enter a ZIP Code")
user_notes = st.text_area("Add any known local insights, cultural notes, or behaviors (optional)")

service_styles = st.multiselect(
    "Select Service Style(s):",
    [
        "Fast food restaurant",
        "Fast casual restaurant",
        "Casual dining restaurant",
        "Fine dining restaurant",
        "Café",
        "Coffee shop",
        "Bakery",
        "Buffet restaurant",
        "Deli",
        "Food court"
    ]
)

cuisine_styles = st.multiselect(
    "Select Cuisine Type(s):",
    [
        "Mexican", "Chinese", "Japanese", "Italian", "Thai", "Vietnamese",
        "Indian", "American", "Korean", "Mediterranean", "Seafood",
        "Barbecue", "Vegan", "Vegetarian", "Burgers", "Pizza", "Coffee", "Bakery"
    ]
)

# ---------- DATA FUNCTIONS ----------
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
    nearby_response = requests.get(nearby_url)
    raw_places = []

    if nearby_response.status_code == 200:
        data = nearby_response.json()
        for result in data.get("results", []):
            rating = result.get("rating", 0)
            review_count = result.get("user_ratings_total", 0)
            score = rating * review_count
            raw_places.append({
                "name": result.get("name"),
                "vicinity": result.get("vicinity"),
                "rating": rating,
                "review_count": review_count
            })

    top_places = sorted(raw_places, key=lambda x: x["score"], reverse=True)[:10]
    return top_places

# ---------- BUILD PROMPT ----------
def build_persona_prompt(zip_code, user_notes):
    mock_data = {
        "Demographics": {
            "Age": "25–39 dominant",
            "Household": "Mostly renters, 1–2 person homes",
            "Income": "$65k–$95k range",
            "Education": "Mostly Bachelor's or higher",
            "Race/Ethnicity": "Diverse, white-majority"
        },
        "Behavior Patterns": [
            "Frequent indie cafes and yoga studios",
            "High grocery spend on organic/local food",
            "Use bikes and public transit"
        ],
        "Values & Interests": [
            "Sustainability", "Localism", "DIY culture", "Progressive causes"
        ],
        "Cultural Markers": [
            "Tattoos, vintage fashion, visible piercings"
        ],
        "User Notes": user_notes
    }

    prompt = f"""
    You are an expert in psychographics, anthropology, and brand strategy.

    Based on the following data for a 10-mile radius around ZIP {zip_code}, generate:

    1. Primary audience persona (name + description)
    2. Archetype (choose 1 from: Citizen, Sage, Rebel, Lover, etc.)
    3. Top motivators
    4. 2–3 secondary influenced groups
    5. 1 brand strategy insight

    Data:
    {json.dumps(mock_data, indent=2)}
    """
    return prompt

# ---------- RUN ----------
if st.button("Generate Analysis"):
    if zip_code:
        lat, lon = get_lat_lon(zip_code)
        with st.spinner("Gathering data and building persona..."):
            persona_prompt = build_persona_prompt(zip_code, user_notes)
            try:
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": persona_prompt}],
                    temperature=0.8,
                    max_tokens=1000
                )
                st.subheader("Patron Persona")
                st.markdown(response.choices[0].message.content)
            except Exception as e:
                st.error(f"Error generating persona: {e}")

        if lat and lon:
            st.subheader("Top Competitors")
            competitors = get_places_data(lat, lon, service_styles + cuisine_styles)
            for comp in competitors:
                st.markdown(f"### {comp['name']}")
                st.markdown(f"- Location: {comp['vicinity']}")
                st.markdown(f"- Rating: ⭐ {comp['rating']} ({comp['review_count']} reviews)")
    else:
        st.warning("Please enter a ZIP code.")
