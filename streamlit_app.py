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
st.title("🥊 Matador")
st.subheader("Command the Crowd.")
st.write("Enter up to 5 US ZIP codes to generate local audience personas and analyze competitive restaurant brands.")

# ---------- INPUT ----------
zip_codes_input = st.text_input("Enter up to 5 ZIP Codes, separated by commas")
user_notes = st.text_area("Add any known local insights, cultural notes, or behaviors (optional)")
mode = st.radio("Choose persona generation mode:", ["Cumulative (combined)", "Individual (per ZIP)"])

service_styles = st.multiselect(
    "Select Service Style(s):",
    ["Full Service", "Fast Casual", "Quick Service", "Café"]
)

cuisine_styles = st.multiselect(
    "Select Cuisine Type(s):",
    [
        "Mexican", "Chinese", "Japanese", "Italian", "Thai", "Vietnamese",
        "Indian", "American", "Korean", "Mediterranean", "Seafood",
        "Barbecue", "Vegan", "Vegetarian", "Burgers", "Pizza", "Coffee", "Bakery"
    ]
)

competitor_mode = st.radio("Choose how to analyze competitors:", ["Auto via Google Places", "Manual Entry"])
manual_competitors = []

if competitor_mode == "Manual Entry":
    with st.expander("Add Manual Competitor Info"):
        for i in range(3):
            name = st.text_input(f"Competitor {i+1} Name", key=f"manual_name_{i}")
            website = st.text_input(f"Competitor {i+1} Website", key=f"manual_site_{i}")
            if name:
                manual_competitors.append({"name": name, "website": website})

# ---------- DATA FUNCTIONS ----------
def get_census_data(zip_code):
    url = "https://api.census.gov/data/2021/acs/acs5"
    params = {
        "get": "NAME,B01001_001E,B19013_001E,B02001_002E,B02001_003E,B02001_005E",
        "for": f"zip code tabulation area:{zip_code}",
        "key": st.secrets["CENSUS_API_KEY"]
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if len(data) > 1:
            labels = data[0]
            values = data[1]
            return dict(zip(labels, values))
    return None

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

# ---------- RUN ----------
if st.button("Generate Analysis"):
    zip_codes = [z.strip() for z in zip_codes_input.split(",") if z.strip()]
    if 1 <= len(zip_codes) <= 5:
        search_terms = service_styles + cuisine_styles
        all_competitors = []

        for zip_code in zip_codes:
            census_data = get_census_data(zip_code)
            lat, lon = get_lat_lon(zip_code)

            if competitor_mode == "Auto via Google Places" and lat and lon:
                competitors = get_places_data(lat, lon, search_terms)
            else:
                competitors = []

            all_competitors.extend(competitors)

        all_competitors.extend(manual_competitors)

        # Limit to Top 10 by score
        all_competitors = sorted(
            all_competitors,
            key=lambda x: (x.get("rating", 0) or 0) * (x.get("review_count", 0) or 0),
            reverse=True
        )[:10]

        st.subheader("Top 10 Competitor Analysis")
        for comp in all_competitors:
            st.markdown(f"### {comp['name']}")
            st.markdown(f"_Location:_ {comp.get('vicinity', 'Manual Entry')}")
            st.markdown(f"⭐ **Rating:** {comp.get('rating', 'N/A')} ({comp.get('review_count', '0')} reviews)")
            if comp.get("website"):
                website_text = get_website_text(comp['website'])
                analysis = analyze_brand_with_gpt(comp['name'], comp.get('vicinity', ''), website_text)
                st.markdown(analysis)
            else:
                st.markdown("_No website available for this competitor._")
    else:
        st.warning("Please enter between 1 and 5 ZIP codes, separated by commas.")
