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
st.write("Enter up to 5 US ZIP codes to generate local audience personas, analyze competitive restaurant brands, and identify whitespace opportunities.")

# ---------- INPUT ----------
zip_codes_input = st.text_input("Enter up to 5 ZIP Codes, separated by commas")
user_notes = st.text_area("Add any known local insights, cultural notes, or behaviors (optional)")

service_styles = st.multiselect(
    "Select Service Style(s):",
    ["Full Service", "Fast Casual", "Quick Service", "Café"]
)

cuisine_styles = st.multiselect(
    "Select Cuisine Type(s):",
    [
        "American", "Barbecue", "Burgers", "Bakery", "Breakfast",
        "Bubble Tea", "Café", "Caribbean", "Chinese", "Coffee",
        "Creole", "Cuban", "Desserts", "Diner", "Donuts",
        "Ethiopian", "Filipino", "French", "Greek", "Hawaiian",
        "Indian", "Indonesian", "Irish", "Italian", "Japanese",
        "Korean", "Latin American", "Lebanese", "Malaysian", "Mediterranean",
        "Mexican", "Middle Eastern", "Noodle Bar", "Peruvian", "Pizza",
        "Pub Food", "Ramen", "Salads", "Sandwiches", "Seafood",
        "Soul Food", "Soup", "Spanish", "Steakhouse", "Sushi",
        "Taiwanese", "Tapas", "Tea Room", "Tex-Mex", "Thai",
        "Turkish", "Vegan", "Vegetarian", "Vietnamese", "Wings"
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
            try:
                score = float(rating) * int(review_count)
            except:
                score = 0
            raw_places.append({
                "name": result.get("name"),
                "vicinity": result.get("vicinity"),
                "rating": rating,
                "review_count": review_count,
                "place_id": result.get("place_id"),
                "score": score
            })

    top_places = sorted(raw_places, key=lambda x: x["score"], reverse=True)[:10]
    places = []
    for place in top_places:
        details_url = (
            f"https://maps.googleapis.com/maps/api/place/details/json?"
            f"place_id={place['place_id']}&fields=website&key={st.secrets['GOOGLE_API_KEY']}"
        )
        details_response = requests.get(details_url)
        website = ""
        if details_response.status_code == 200:
            website = details_response.json().get("result", {}).get("website", "")

        places.append({
            "name": place["name"],
            "vicinity": place["vicinity"],
            "rating": place["rating"],
            "review_count": place["review_count"],
            "website": website
        })

    return places

def get_website_text(url):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.get_text(separator=' ', strip=True)
    except Exception as e:
        return f"Error fetching website content: {e}"

def analyze_brand_with_gpt(name, address, website_text):
    prompt = f"""
    You are a brand strategist. Based on the following content from the restaurant's website, analyze and return:

    1. The brand’s tone of voice
    2. Three personality traits that reflect the brand
    3. Their core brand message or positioning
    4. What they emphasize in marketing (e.g. ingredients, experience, convenience)
    5. Overall impression in 1 sentence

    Restaurant Name: {name}
    Location: {address}
    Website Text: {website_text[:3000]}
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

def build_patron_prompt(mock_data):
    prompt = f"""
    You are an expert in psychographics, anthropology, and brand strategy.

    Based on the following data for a 10-mile radius, generate:

    1. Primary audience persona (name + description)
    2. Archetype (choose 1 from: Citizen, Sage, Rebel, Lover, etc.)
    3. Top motivators
    4. 2–3 secondary influenced groups
    5. 1 brand strategy insight

    Data:
    {json.dumps(mock_data, indent=2)}
    """
    return prompt

def build_whitespace_prompt(patron_summary, competitor_summary):
    return f"""
    You are a brand strategist analyzing whitespace. Based on these patron groups and competitor brand summaries, identify 3 whitespace opportunities for new brand positioning.

    For each:
    - List 3 personality traits
    - Name the Patron groups they’d attract
    - Give a short rationale why this is a whitespace

    Patron Summary:
    {patron_summary}

    Competitor Summary:
    {competitor_summary}
    """

# ---------- RUN ----------
if st.button("Generate Report"):
    zip_codes = [z.strip() for z in zip_codes_input.split(",") if z.strip()]
    if 1 <= len(zip_codes) <= 5:
        search_terms = service_styles + cuisine_styles
        competitors = []
        patron_outputs = []
        lat, lon = get_lat_lon(zip_codes[0])
        if lat and lon:
            competitors = get_places_data(lat, lon, search_terms)

        for zip_code in zip_codes:
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

            prompt = build_patron_prompt(mock_data)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=700
            )
            patron_outputs.append(response.choices[0].message.content)

        tabs = st.tabs(["Patrons", "Competition", "Whitespace"])

        with tabs[0]:
            st.subheader("📍 Patron Personas")
            for out in patron_outputs:
                st.markdown(out)

        with tabs[1]:
            st.subheader("🍽️ Top 10 Competitors")
            for comp in competitors:
                st.markdown(f"### {comp['name']}")
                st.markdown(f"**Rating:** {comp['rating']} ({comp['review_count']} reviews)")
                st.markdown(f"**Address:** {comp['vicinity']}")
                st.markdown(f"**Website:** {comp['website'] if comp['website'] else 'N/A'}")
                if comp['website']:
                    site_text = get_website_text(comp['website'])
                    desc = analyze_brand_with_gpt(comp['name'], comp['vicinity'], site_text)
                    st.markdown(desc)

        with tabs[2]:
            st.subheader("🧠 Whitespace Opportunities")
            competitor_summary = ", ".join([comp['name'] for comp in competitors])
            whitespace_prompt = build_whitespace_prompt("\n".join(patron_outputs), competitor_summary)
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": whitespace_prompt}],
                temperature=0.7,
                max_tokens=800
            )
            st.markdown(response.choices[0].message.content)
    else:
        st.warning("Please enter between 1 and 5 ZIP codes.")
