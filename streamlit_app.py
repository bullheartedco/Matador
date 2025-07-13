# Matador: Streamlit App for Local Patron & Competitor Analysis
import streamlit as st
import requests
from openai import OpenAI
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
            if name:
                manual_competitors.append({"name": name, "website": website})

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

def build_patron_prompt(zip_codes, user_notes, mode):
    return f"""
    You are an expert in psychographics, anthropology, and brand strategy.

    Based on the following data for a 10-mile radius around ZIP code(s): {', '.join(zip_codes)}
    - User Notes: {user_notes}

    Generate 3–5 audience personas with the following:
    1. Persona Name (must be a collective name like \"Sun Chasers\", not an individual name)
    2. Summary of their lifestyle and cultural tendencies
    3. Archetypal opportunity (what they're psychologically drawn to; choose 1 of the 12 Jungian archetypes but renamed as: Citizen, Sage, Rebel, Lover, Creator, Explorer, Innocent, Magician, Hero, Jester, Caregiver, Sovereign)
    4. Motivators (emotional + behavioral drivers)
    5. 2–3 influenced secondary groups
    6. 5 brands they love that reflect their values
    7. Estimated prevalence (% of total population they represent)
    """

# ---------- RUN BUTTON ----------
if st.button("Generate Report"):
    zip_codes = [z.strip() for z in zip_codes_input.split(",") if z.strip()]
    if 1 <= len(zip_codes) <= 5:
        tabs = st.tabs(["Patrons", "Competition", "White Space"])

        with tabs[0]:
            with st.spinner("Generating audience personas..."):
                try:
                    # Fetch Census Data
                    census_rows = fetch_census_for_zips(zip_codes)
                    if census_rows:
                        demo_parts = [
                            f"{z['NAME']}: Pop {z['B01001_001E']}, Income ${z['B19013_001E']}, "
                            f"White: {z['B02001_002E']}, Black: {z['B02001_003E']}"
                            for z in census_rows
                        ]
                        demographic_summary = "\n".join(demo_parts)
                    else:
                        demographic_summary = "No Census data available for these ZIPs."

                    # Build prompt using summary
                    full_prompt = f"Demographic Snapshot:\n{demographic_summary}\n\n" + build_patron_prompt(zip_codes, user_notes, mode)

                    # GPT Call
                    response = client.chat.completions.create(
                        model="gpt-4",
                        messages=[{"role": "user", "content": full_prompt}],
                        temperature=0.75,
                        max_tokens=1600
                    )
                    result = response.choices[0].message.content
                    st.session_state["patron_personas_raw"] = result  # Save for white space reference
                    personas = result.split("\n\n")

                    for p in personas:
                        if p.strip():
                            lines = p.strip().split("\n")
                            title_line = lines[0]
                            other_lines = lines[1:]
                            st.markdown(f"### {title_line}")
                            for line in other_lines:
                                st.markdown(f"- {line}")
                except Exception as e:
                    st.error(f"Error generating personas: {e}")

        with tabs[1]:
            st.subheader("Top Competitor Analysis")
            search_terms = []
            for style in selected_service_styles:
                search_terms += service_style_map.get(style, [])
            search_terms += cuisine_styles

            competitors = []
            for zip_code in zip_codes:
                lat, lon = get_lat_lon(zip_code)
                if lat and lon and competitor_mode == "Auto via Google Places":
                    comps = get_places_data(lat, lon, search_terms)
                    competitors.extend(comps)

            competitors.extend(manual_competitors)

            seen = set()
            unique_competitors = []
            for c in competitors:
                if c["name"] not in seen:
                    unique_competitors.append(c)
                    seen.add(c["name"])

            for comp in unique_competitors[:10]:
                st.markdown(f"### {comp['name']}")
                st.markdown(f"**Location:** {comp.get('vicinity', 'Manual Entry')}")
                st.markdown(f"**Rating:** {comp.get('rating', 'N/A')} ({comp.get('review_count', '0')} reviews)")
                if comp.get("website"):
                    st.markdown(f"**Website:** {comp['website']}")
                    website_text = get_website_text(comp['website'])
                    analysis = analyze_brand_with_gpt(comp['name'], comp.get('vicinity', ''), website_text)
                    st.markdown(analysis)
                else:
                    st.markdown("_No website available for this competitor._")

        with tabs[2]:
            st.subheader("White Space Opportunities")
            if "patron_personas_raw" in st.session_state:
                whitespace_prompt = f"""
                Based on the patron personas below, identify three whitespace brand personality opportunities that aren't currently dominant.

                For each opportunity:
                - List 3 underrepresented brand personality traits
                - Name 2–3 patron personas who would likely be attracted
                - Write a short brand strategy insight on how a new brand could embody this

                Patron Personas:
                {st.session_state['patron_personas_raw']}
                """
            with st.spinner("Analyzing white space opportunities..."):
                try:
                    response = client.chat.completions.create(
                        model="gpt-4",
                        messages=[{"role": "user", "content": whitespace_prompt}],
                        temperature=0.75,
                        max_tokens=1000
                    )
                    whitespace_results = response.choices[0].message.content
                    st.markdown(whitespace_results)
                except Exception as e:
                    st.error(f"Error generating whitespace analysis: {e}")
    else:
        st.warning("Please enter between 1 and 5 ZIP codes.")