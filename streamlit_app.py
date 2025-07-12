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

def build_patron_prompt(zip_codes, user_notes, mode):
    base = f"""
    You are a consumer behavior analyst helping a brand strategist understand the local market across these ZIP codes: {', '.join(zip_codes)}.

    Use the following insights and data from the U.S. Census and local observation notes:
    Notes: {user_notes}

    Output 5 persona profiles that are representative of the population across these ZIPs. For each include:
    - Persona Name (use descriptive names like "Sun Chasers")
    - Lifestyle Summary
    - Motivators (behavioral and emotional drivers)
    - Archetypal Opportunity (what they're psychologically drawn to)
    - 3 Personality Traits
    - Influenced Groups (2–3 audience types they influence)
    - 5 Brands They Love (based on personality + values)
    - Prevalence Score (estimate % in market)
    """
    return base

def build_whitespace_prompt(competitors_summary, patrons_summary):
    return f"""
    Based on the competitor brand summaries:
    {competitors_summary}

    And these patron persona profiles:
    {patrons_summary}

    Identify 3 whitespace opportunities for a new restaurant brand to stand apart. For each, provide:
    - A unique combination of 3 personality traits not represented by competitors
    - Patron groups most likely to be attracted to each combination
    """

# ---------- RUN ----------
if st.button("Generate Analysis"):
    zip_codes = [z.strip() for z in zip_codes_input.split(",") if z.strip()]
    if 1 <= len(zip_codes) <= 5:
        search_terms = service_styles + cuisine_styles
        all_competitors = []
        all_latlon = []

        for zip_code in zip_codes:
            lat, lon = get_lat_lon(zip_code)
            if lat and lon:
                all_latlon.append((zip_code, lat, lon))

            if competitor_mode == "Auto via Google Places" and lat and lon:
                competitors = get_places_data(lat, lon, search_terms)
                all_competitors.extend(competitors)

        all_competitors.extend(manual_competitors)

        # Deduplicate competitors by name
        seen = set()
        unique_competitors = []
        for c in all_competitors:
            if c["name"] not in seen:
                unique_competitors.append(c)
                seen.add(c["name"])

        # Sort and limit to 10
        sorted_comps = sorted(
            unique_competitors,
            key=lambda x: (x.get("rating", 0) or 0) * (x.get("review_count", 0) or 0),
            reverse=True
        )[:10]

        tabs = st.tabs(["Patrons", "Competition", "Whitespace"])

        with tabs[0]:
            with st.spinner("Generating persona profiles..."):
                patron_prompt = build_patron_prompt(zip_codes, user_notes, mode)
                try:
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": patron_prompt}],
                        temperature=0.8,
                        max_tokens=2000
                    )
                    raw_output = response.choices[0].message.content

                    personas = raw_output.split("\n\n")
                    persona_blocks = [p for p in personas if "Prevalence Score" in p]

                    sorted_personas = sorted(
                        persona_blocks,
                        key=lambda x: int(x.split("Prevalence Score:")[-1].replace("%", "").strip()),
                        reverse=True
                    )

                    for persona in sorted_personas:
                        name_line = next((line for line in persona.split("\n") if line.strip() and not line.startswith("-")), "Persona")
                        prevalence_line = next((line for line in persona.split("\n") if "Prevalence Score:" in line), "")
                        prevalence = prevalence_line.replace("Prevalence Score:", "").strip()

                        st.markdown(f"### {name_line} ({prevalence})")
                        st.markdown(persona)

                except Exception as e:
                    st.error(f"Error generating persona profiles: {e}")

        with tabs[1]:
            st.subheader(f"Top {len(sorted_comps)} Competitor Analysis")
            comp_summary = ""
            for comp in sorted_comps:
                st.markdown(f"### {comp['name']}")
                st.markdown(f"_Location:_ {comp.get('vicinity', 'Manual Entry')}")
                st.markdown(f"⭐ **Rating:** {comp.get('rating', 'N/A')} ({comp.get('review_count', '0')} reviews)")
                if comp.get("website"):
                    website_text = get_website_text(comp['website'])
                    analysis = analyze_brand_with_gpt(comp['name'], comp.get('vicinity', ''), website_text)
                    st.markdown(analysis)
                    comp_summary += f"{comp['name']}: {analysis}\n\n"
                else:
                    st.markdown("_No website available for this competitor._")

        with tabs[2]:
            with st.spinner("Analyzing whitespace opportunities..."):
                try:
                    whitespace_prompt = build_whitespace_prompt(comp_summary, raw_output)
                    ws_response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": whitespace_prompt}],
                        temperature=0.8,
                        max_tokens=1000
                    )
                    st.markdown(ws_response.choices[0].message.content)
                except Exception as e:
                    st.error(f"Error generating whitespace analysis: {e}")

    else:
        st.warning("Please enter between 1 and 5 ZIP codes, separated by commas.")
