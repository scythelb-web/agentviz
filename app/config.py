import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_CLIENT_ID = os.getenv("STRIPE_CLIENT_ID", "")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

PRICING = {
    "starter": {"price": 29, "label": "Starter", "transactions": 1000},
    "growth": {"price": 79, "label": "Growth", "transactions": 10000},
    "scale": {"price": 199, "label": "Scale", "transactions": 100000},
}
