from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import requests
import datetime
import hashlib
import logging
import random
from functools import lru_cache
import os

# Initialize Flask application
app = Flask(__name__)
CORS(app)

# Configure application logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database of major cities with real coordinates
CITIES = {
    "delhi": {
        "lat": 28.6139,
        "lon": 77.2090,
        "display_name": "Delhi, India",
        "normal_temp": 25.5,
        "description": "Capital city with diverse climate patterns"
    },
    "mumbai": {
        "lat": 19.0760,
        "lon": 72.8777,
        "display_name": "Mumbai, Maharashtra, India",
        "normal_temp": 27.0,
        "description": "Coastal metropolitan with humid climate"
    },
    "bangalore": {
        "lat": 12.9716,
        "lon": 77.5946,
        "display_name": "Bengaluru, Karnataka, India",
        "normal_temp": 23.5,
        "description": "Garden city with pleasant weather"
    },
    "kolkata": {
        "lat": 22.5726,
        "lon": 88.3639,
        "display_name": "Kolkata, West Bengal, India",
        "normal_temp": 26.8,
        "description": "Cultural hub with tropical climate"
    },
    "chennai": {
        "lat": 13.0827,
        "lon": 80.2707,
        "display_name": "Chennai, Tamil Nadu, India",
        "normal_temp": 28.7,
        "description": "Coastal city with hot summers"
    },
    "hyderabad": {
        "lat": 17.3850,
        "lon": 78.4867,
        "display_name": "Hyderabad, Telangana, India",
        "normal_temp": 26.5,
        "description": "Historic city with moderate climate"
    },
    "tokyo": {
        "lat": 35.6762,
        "lon": 139.6503,
        "display_name": "Tokyo, Japan",
        "normal_temp": 15.0,
        "description": "Metropolitan capital with seasonal climate"
    },
    "new york": {
        "lat": 40.7128,
        "lon": -74.0060,
        "display_name": "New York City, USA",
        "normal_temp": 12.0,
        "description": "Global financial hub with continental climate"
    },
    "london": {
        "lat": 51.5074,
        "lon": -0.1278,
        "display_name": "London, UK",
        "normal_temp": 11.0,
        "description": "Historic city with temperate maritime climate"
    },
    "sydney": {
        "lat": -33.8688,
        "lon": 151.2093,
        "display_name": "Sydney, Australia",
        "normal_temp": 18.0,
        "description": "Coastal city with subtropical climate"
    },
    "amazon": {
        "lat": -3.4653,
        "lon": -62.2159,
        "display_name": "Amazon Rainforest",
        "normal_temp": 26.0,
        "description": "World's largest tropical rainforest"
    },
    "sahara": {
        "lat": 25.0,
        "lon": 0.0,
        "display_name": "Sahara Desert",
        "normal_temp": 30.0,
        "description": "World's largest hot desert"
    }
}

# Helper functions (kept from your original code)
def normalize_value(value, min_val, max_val):
    try:
        if max_val <= min_val:
            return 50.0
        normalized = 100.0 * (value - min_val) / (max_val - min_val)
        return max(0.0, min(100.0, normalized))
    except Exception:
        return 50.0

def calculate_temperature_score(current_temp, normal_temp, location_type="inland"):
    if 20 <= current_temp <= 28:
        temp_score = 100.0
    elif current_temp < 10 or current_temp > 38:
        temp_score = 20.0
    elif current_temp < 20:
        temp_score = 50.0 + (current_temp - 10) * 5
    else:
        temp_score = 100.0 - (current_temp - 28) * 8

    temp_anomaly = abs(current_temp - normal_temp)
    if temp_anomaly <= 1.0:
        anomaly_score = 100.0
    elif temp_anomaly <= 3.0:
        anomaly_score = 100.0 - (temp_anomaly - 1.0) * 25
    elif temp_anomaly <= 5.0:
        anomaly_score = 50.0 - (temp_anomaly - 3.0) * 15
    else:
        anomaly_score = 10.0

    if location_type == "coastal":
        adjustment = 1.1 if abs(current_temp - 25) <= 5 else 0.9
        temp_score *= adjustment
    elif location_type == "urban":
        if current_temp > normal_temp + 2:
            temp_score *= 0.9

    climate_score = (temp_score * 0.7 + anomaly_score * 0.3)
    return min(100.0, max(0.0, climate_score))

def get_temperature_insight(current_temp, normal_temp):
    anomaly = current_temp - normal_temp
    if current_temp < 10:
        category = "Very Cold ❄️"
        feeling = "Bundle up! It's quite chilly."
    elif current_temp < 20:
        category = "Cool 🌤️"
        feeling = "A light jacket might be comfortable."
    elif current_temp <= 28:
        category = "Comfortable 😊"
        feeling = "Perfect weather for outdoor activities!"
    elif current_temp <= 32:
        category = "Warm ☀️"
        feeling = "Stay hydrated in this warm weather."
    elif current_temp <= 38:
        category = "Hot 🔥"
        feeling = "Avoid peak sun hours, stay cool."
    else:
        category = "Extreme Heat 🥵"
        feeling = "Take precautions against heat stress."

    if abs(anomaly) < 1:
        anomaly_desc = "Seasonal average"
        trend = "Stable"
    elif anomaly > 3:
        anomaly_desc = f"Significantly warmer than usual (+{anomaly:.1f}°C)"
        trend = "Warmer"
    elif anomaly > 1:
        anomaly_desc = f"Warmer than usual (+{anomaly:.1f}°C)"
        trend = "Slightly warmer"
    elif anomaly < -3:
        anomaly_desc = f"Significantly cooler than usual ({anomaly:.1f}°C)"
        trend = "Cooler"
    elif anomaly < -1:
        anomaly_desc = f"Cooler than usual ({anomaly:.1f}°C)"
        trend = "Slightly cooler"
    else:
        anomaly_desc = "Typical for this season"
        trend = "Normal"

    return {
        "category": category,
        "feeling": feeling,
        "anomaly_description": anomaly_desc,
        "trend": trend
    }

def calculate_heat_index(temp_c, humidity=65):
    if temp_c < 27:
        return temp_c
    temp_f = (temp_c * 9/5) + 32
    heat_index_f = -42.379 + 2.04901523*temp_f + 10.14333127*humidity - 0.22475541*temp_f*humidity
    heat_index_c = (heat_index_f - 32) * 5/9
    return round(heat_index_c, 1)

def generate_environmental_scores(location_seed):
    random.seed(location_seed)
    environmental_data = {
        "vegetation_index": round(random.uniform(0.2, 0.8), 3),
        "habitat_quality": round(random.uniform(0.3, 0.9), 3),
        "protected_areas": round(random.uniform(0.05, 0.4), 3),
        "annual_rainfall": round(random.uniform(300, 2500), 1),
        "groundwater_risk": round(random.uniform(0.2, 0.9), 3),
        "water_quality": round(random.uniform(0.4, 0.95), 3),
        "pm25_level": round(random.uniform(15, 180), 1),
        "air_purity": round(random.uniform(0.3, 0.95), 3),
        "species_richness": random.randint(30, 350),
        "ecosystem_health": round(random.uniform(0.4, 0.9), 3),
        "current_temperature": round(random.uniform(15.0, 38.0), 1),
        "normal_temperature": round(random.uniform(22.0, 30.0), 1),
        "humidity_level": random.randint(40, 90)
    }

    is_coastal = random.random() < 0.3
    is_urban = random.random() < 0.6

    land_score = (
        0.5 * normalize_value(environmental_data["vegetation_index"], 0, 1) +
        0.3 * (100 - normalize_value(1 - environmental_data["habitat_quality"], 0, 1)) +
        0.2 * normalize_value(environmental_data["protected_areas"], 0, 0.5)
    )

    water_score = (
        0.4 * normalize_value(environmental_data["annual_rainfall"], 200, 3000) +
        0.4 * (100 - normalize_value(environmental_data["groundwater_risk"], 0, 1)) +
        0.2 * normalize_value(environmental_data["water_quality"], 0, 1)
    )

    air_score = 100 - normalize_value(environmental_data["pm25_level"], 0, 200)

    biodiversity_score = (
        0.6 * normalize_value(environmental_data["species_richness"], 0, 500) +
        0.4 * normalize_value(environmental_data["ecosystem_health"], 0, 1)
    )

    location_type = "coastal" if is_coastal else "urban" if is_urban else "inland"
    climate_score = calculate_temperature_score(
        environmental_data["current_temperature"],
        environmental_data["normal_temperature"],
        location_type
    )

    overall_score = (land_score + water_score + air_score + biodiversity_score + climate_score) / 5.0
    overall_score = round(max(0.0, min(100.0, overall_score)), 1)

    temp_insight = get_temperature_insight(
        environmental_data["current_temperature"],
        environmental_data["normal_temperature"]
    )

    feels_like = calculate_heat_index(
        environmental_data["current_temperature"],
        environmental_data["humidity_level"]
    )

    pm25 = environmental_data["pm25_level"]
    if pm25 <= 12:
        air_quality = "Excellent"
    elif pm25 <= 35:
        air_quality = "Good"
    elif pm25 <= 55:
        air_quality = "Moderate"
    elif pm25 <= 150:
        air_quality = "Poor"
    else:
        air_quality = "Hazardous"

    return {
        "overall_score": overall_score,
        "category_scores": {
            "land": round(land_score, 1),
            "water": round(water_score, 1),
            "air": round(air_score, 1),
            "biodiversity": round(biodiversity_score, 1),
            "climate": round(climate_score, 1)
        },
        "temperature_data": {
            "current": environmental_data["current_temperature"],
            "normal": environmental_data["normal_temperature"],
            "feels_like": feels_like,
            "anomaly": round(environmental_data["current_temperature"] - environmental_data["normal_temperature"], 1),
            "category": temp_insight["category"],
            "feeling": temp_insight["feeling"],
            "trend": temp_insight["trend"],
            "unit": "°C"
        },
        "detailed_metrics": {
            "vegetation_health": environmental_data["vegetation_index"],
            "annual_rainfall_mm": environmental_data["annual_rainfall"],
            "pm25_concentration": environmental_data["pm25_level"],
            "air_quality": air_quality,
            "species_count": environmental_data["species_richness"],
            "groundwater_risk": environmental_data["groundwater_risk"],
            "humidity_percent": environmental_data["humidity_level"]
        },
        "descriptions": {
            "overall": get_score_description(overall_score),
            "land": get_category_description("land", land_score),
            "water": get_category_description("water", water_score),
            "air": get_category_description("air", air_score),
            "biodiversity": get_category_description("biodiversity", biodiversity_score),
            "climate": get_category_description("climate", climate_score)
        }
    }

def get_score_description(score):
    if score >= 85:
        return "Excellent 🌟 - Outstanding environmental conditions"
    elif score >= 70:
        return "Good 👍 - Healthy environment with minor concerns"
    elif score >= 55:
        return "Moderate ⚖️ - Average environmental conditions"
    elif score >= 40:
        return "Needs Attention ⚠️ - Some environmental challenges"
    elif score >= 25:
        return "Poor 😟 - Significant environmental issues"
    else:
        return "Critical 🚨 - Severe environmental problems"

def get_category_description(category, score):
    descriptions = {
        "land": {
            "high": "Lush vegetation with healthy ecosystems",
            "medium": "Moderate land health with some conservation",
            "low": "Limited vegetation and habitat concerns"
        },
        "water": {
            "high": "Abundant clean water resources",
            "medium": "Adequate water with some sustainability concerns",
            "low": "Water scarcity or quality issues"
        },
        "air": {
            "high": "Fresh, clean air quality",
            "medium": "Moderate air with occasional pollution",
            "low": "Poor air quality affecting health"
        },
        "biodiversity": {
            "high": "Rich diversity of species and habitats",
            "medium": "Moderate biodiversity with conservation efforts",
            "low": "Limited species diversity"
        },
        "climate": {
            "high": "Comfortable climate with stable patterns",
            "medium": "Variable climate with some extremes",
            "low": "Challenging climate conditions"
        }
    }
    
    if score >= 70:
        level = "high"
    elif score >= 40:
        level = "medium"
    else:
        level = "low"
    
    return descriptions[category][level]

def create_location_seed(location_name):
    clean_name = location_name.strip().lower()
    name_hash = hashlib.sha256(clean_name.encode()).hexdigest()
    return int(name_hash[:8], 16)

@lru_cache(maxsize=100)
def find_location_coordinates(location_query):
    query_lower = location_query.strip().lower()
    for city_name, data in CITIES.items():
        if city_name in query_lower:
            logger.info(f"Found known city: {city_name}")
            return {
                "coordinates": {"lat": data["lat"], "lon": data["lon"]},
                "name": data["display_name"],
                "description": data.get("description", ""),
                "source": "predefined"
            }
    seed = create_location_seed(location_query)
    random.seed(seed)
    return {
        "coordinates": {
            "lat": round(random.uniform(-55, 70), 4),
            "lon": round(random.uniform(-180, 180), 4)
        },
        "name": f"{location_query.title()}",
        "description": "Location approximated based on name",
        "source": "estimated"
    }

# ==================== FLASK ROUTES ====================

@app.route("/")
def home_page():
    return render_template("index.html")

@app.route("/scanner")
def scanner_page():
    return render_template("scanner.html")

@app.route("/api/geocode", methods=["POST"])
def geocode_location():
    try:
        if not request.is_json:
            return jsonify({
                "success": False,
                "error": "Please send JSON data",
                "message": "Content-Type must be application/json"
            }), 400

        request_data = request.get_json()
        location = request_data.get("location", "").strip()

        if not location or len(location) < 2:
            return jsonify({
                "success": False,
                "error": "Valid location required",
                "message": "Enter a city, region, or country name"
            }), 400

        logger.info(f"Geocoding location: {location}")

        location_info = find_location_coordinates(location)
        location_seed = create_location_seed(location)
        environmental_scores = generate_environmental_scores(location_seed)

        analysis_result = {
            "location_input": location,
            "resolved_name": location_info["name"],
            "coordinates": location_info["coordinates"],
            "scores": {
                "ehs": environmental_scores["overall_score"],
                "land": environmental_scores["category_scores"]["land"],
                "water": environmental_scores["category_scores"]["water"],
                "air": environmental_scores["category_scores"]["air"],
                "bio": environmental_scores["category_scores"]["biodiversity"],
                "climate": environmental_scores["category_scores"]["climate"],
                "details": {
                    "ndvi": environmental_scores["detailed_metrics"]["vegetation_health"],
                    "pm25_ugm3": environmental_scores["detailed_metrics"]["pm25_concentration"],
                    "annual_rainfall_mm": environmental_scores["detailed_metrics"]["annual_rainfall_mm"],
                    "species_richness_index": environmental_scores["detailed_metrics"]["species_count"],
                    "temp_anomaly_c": environmental_scores["temperature_data"]["anomaly"],
                    "population_density": f"{random.randint(50, 1500)}/km²"
                }
            },
            "links": {
                "google_maps": f"https://www.google.com/maps/search/?api=1&query={location_info['coordinates']['lat']},{location_info['coordinates']['lon']}",
                "openstreetmap": f"https://www.openstreetmap.org/#map=10/{location_info['coordinates']['lat']}/{location_info['coordinates']['lon']}"
            },
            "note": "This is demonstration data generated from location name. Real environmental data would require API integration with actual data sources.",
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z"
        }

        return jsonify(analysis_result)

    except Exception as error:
        logger.error(f"Geocoding error: {error}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Geocoding failed",
            "message": "Unable to process location. Try a different search term."
        }), 500

@app.route("/api/health")
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "EcoImpactScanner",
        "version": "2.0",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
    })

# ---------- Start block for development & production ----------
if __name__ == "__main__":
    # Development startup message
    print("\n" + "="*70)
    print("🌿 ECOIMPACTSCANNER - Cinematic Environmental Scanner")
    print("="*70)
    print("\n✨ Two Beautiful Experiences:")
    print("   🎬 Cinematic Homepage: http://localhost:5000/")
    print("   📊 Interactive Scanner: http://localhost:5000/scanner")
    print("\n🔍 Try These Locations:")
    print("   • Major Indian cities: Delhi, Mumbai, Bangalore")
    print("   • International: Tokyo, New York, London")
    print("   • Natural wonders: Amazon, Sahara")
    print("\n🚀 Starting server on http://0.0.0.0:<PORT>")
    print("="*70 + "\n")

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
