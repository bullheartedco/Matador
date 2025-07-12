# Matador: Streamlit App for Local Patron & Competitor Analysis
import streamlit as st
import requests
from openai import OpenAI
from bs4 import BeautifulSoup
import re

# ---------- CONFIG ----------
st.set_page_config(page_title="Matador: Local Audience Profiler", layout="wide")

# ---------- OPENAI CLIENT ----------
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ---------- APP HEADER ----------
st.title("💃🏻 Matador")
st.subheader("Command the Crowd.")
st.write("Enter up to 5 US ZIP codes to generate local audience personas, analyze competitors, and reveal whitespace opportunities.")

# ---------- INPUTS ----------
zip_codes_input = st.text_input("Enter up to 5 ZIP Codes, separated by commas")
user_notes = st.text_area("Local insights, cultural notes, or behaviors (optional)")
mode = st.radio("Persona generation mode:", ["Cumulative (combined)", "Individual (per ZIP)"])

service_styles = st.multiselect(
    "Select Service Style(s):",
    ["Full Service", "Fast Casual", "Quick Service", "Café"]
)

cuisine_styles = st.multiselect(
    "Select Cuisine Type(s):",
    ["Mexican", "Chinese", "Japanese", "Italian", "Thai", "Vietnamese",
     "Indian", "American", "Korean", "Mediterranean", "Seafood",
     "Barbecue", "Vegan", "Vegetarian", "Burgers", "Pizza", "Coffee", "Bakery"]
)

competitor_mode = st.radio("Analyze competitors by:", ["Auto via Google Places", "Manual Entry"])
manual_competitors = []

if competitor_mode == "Manual Entry":
    with st.expander("Add Manual Competitors"):
        for i in range(3):
            name = st.text_input(f"Competitor {i+1} Name", key=f"manual_name_{i}")
            website = st.text_input(f"Competitor {i+1} Website", key=f"manual_site_{i}")
            if name:
                manual_competitors.append({"name": name, "website": website})

# ---------- FUNCTIONS ----------
def get_lat_lon(zip_code):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={zip_code}&key={st.secrets['GOOGLE_API_KEY']}"
    r = requests.get(url)
    if r.status_code == 200 and r.json()["results"]:
        loc = r.json()["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    return None, None

def classify_service_style(place):
    name = place.get("name", "").lower()
    if "drive" in name or "express" in name or place.get("user_ratings_total", 0) > 300:
        return "Quick Service"
    elif "grill" in name or "house" in name:
        return "Fast Casual"
    elif "bar" in name or "bistro" in name:
        return "Full Service"
    else:
        return "Café"

def filter_competitors_by_service_style(comp_list, selected_styles):
    return [c for c in comp_list if c.get("service_classification") in selected_styles]

def get_website_text(url):
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.get_text(separator=' ', strip=True)
    except:
        return ""

def analyze_brand_with_gpt(name, location, website_text):
    prompt = f"""
    Analyze the brand tone of voice, 3 brand personality traits, and positioning based on this restaurant's website content:
    Name: {name}
    Location: {location}
    Content: {website_text[:3000]}
    Output in bullets.
    """
    try:
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500
        )
        return res.choices[0].message.content
    except:
        return "Could not analyze."

def build_patron_prompt(zip_codes, notes, mode):
    return f"""
    You are a consumer behavior analyst. Using local ZIPs: {', '.join(zip_codes)} and notes: {notes}, output 5 unique persona profiles with:
    - Persona Name (e.g., "Sun Chasers")
    - Lifestyle Summary
    - Motivators
    - Archetypal Opportunity
    - 3 Personality Traits
    - Influenced Groups
    - 5 Brands They Love
    - Prevalence Score (%)
    Format each in sections.
    """

def render_persona_output(text):
    personas = re.split(r'\n(?=Persona Name\s*:\s*)', text.strip())
    for p in personas:
        name_match = re.search(r'Persona Name\s*:\s*(.+)', p)
        prevalence_match = re.search(r'Prevalence Score\s*:\s*(\d+%?)', p)
        name = name_match.group(1).strip() if name_match else "Unnamed"
        prevalence = prevalence_match.group(1).strip() if prevalence_match else "N/A"
        st.markdown(f"### {name} — {prevalence}")
        for label in ["Lifestyle Summary", "Motivators", "Archetypal Opportunity", "3 Personality Traits", "Influenced Groups", "5 Brands They Love"]:
            match = re.search(rf"{label}\s*:\s*(.+?)(?=\n[A-Z]|$)", p, re.DOTALL)
            if match:
                st.markdown(f"- **{label}:** {match.group(1).strip()}")

# ---------- RUN ----------
if st.button("Generate Analysis"):
    zip_codes = [z.strip() for z in zip_codes_input.split(",") if z.strip()]
    if 1 <= len(zip_codes) <= 5:
        search_terms = service_styles + cuisine_styles
        competitors = []

        for z in zip_codes:
            lat, lon = get_lat_lon(z)
            if lat and lon and competitor_mode == "Auto via Google Places":
                places_url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={lat},{lon}&radius=5000&type=restaurant&keyword={'%20'.join(search_terms)}&key={st.secrets['GOOGLE_API_KEY']}"
                r = requests.get(places_url)
                for place in r.json().get("results", []):
                    competitors.append({
                        "name": place.get("name"),
                        "vicinity": place.get("vicinity", ""),
                        "rating": place.get("rating", ""),
                        "review_count": place.get("user_ratings_total", 0),
                        "website": "",
                        "service_classification": classify_service_style(place),
                        "multi_unit": "Likely" if place.get("user_ratings_total", 0) > 100 else "Independent"
                    })

        for c in manual_competitors:
            competitors.append({
                "name": c["name"],
                "vicinity": "Manual Entry",
                "rating": None,
                "review_count": None,
                "website": c["website"],
                "service_classification": "Manual",
                "multi_unit": "Unknown"
            })

        filtered = filter_competitors_by_service_style(competitors, service_styles)
        unique = {c['name']: c for c in filtered}.values()
        sorted_comps = sorted(unique, key=lambda x: (x.get("rating") or 0) * (x.get("review_count") or 0), reverse=True)[:10]

        tabs = st.tabs(["Patrons", "Competition", "Whitespace"])

        with tabs[0]:
            st.subheader("Patron Personas")
            patron_prompt = build_patron_prompt(zip_codes, user_notes, mode)
            res = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": patron_prompt}],
                temperature=0.8,
                max_tokens=2500
            )
            render_persona_output(res.choices[0].message.content)

        with tabs[1]:
            st.subheader("Top Competitors")
            for comp in sorted_comps:
                st.markdown(f"### {comp['name']}")
                st.markdown(f"- **Location:** {comp['vicinity']}")
                st.markdown(f"- **Rating:** {comp.get('rating', 'N/A')} ({comp.get('review_count', 0)} reviews)")
                st.markdown(f"- **Service Style:** {comp['service_classification']}")
                st.markdown(f"- **Business Type:** {comp['multi_unit']}")
                if comp.get("website"):
                    st.markdown(f"- **Website:** {comp['website']}")

        with tabs[2]:
            st.subheader("Whitespace Opportunities")
            whitespace_prompt = f"""
            From the personas and competitive brand list, identify 3 whitespace personality trait trios not present in the market.
            For each trio:
            - List 3 traits
            - Match Patron Personas most likely to love them
            - Provide 1-2 sentence explanation for the opportunity.
            """
            ws = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": whitespace_prompt}],
                temperature=0.7,
                max_tokens=800
            )
            st.markdown(ws.choices[0].message.content)
    else:
        st.warning("Enter 1 to 5 ZIP codes.")
