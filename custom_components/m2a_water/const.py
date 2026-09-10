"""Constants for the m2A Water integration."""

from datetime import timedelta

DOMAIN = "m2a_water"

CONF_COUNTER_NUMBER = "counter_number"
CONF_REFERENCE = "reference"
CONF_STARTS_AT = "starts_at"

BASE_URL = "https://e-services.mulhouse-alsace.fr"
LOGIN_PATH = "/api/auth/login"
WATER_API_PATH = "/api/user/servicedeseaux"

UPDATE_INTERVAL = timedelta(hours=1)
FORCE_REFRESH_INTERVAL = timedelta(hours=1)
RECENT_HISTORY_DAYS = 62
HISTORY_REQUEST_DELAY_SECONDS = 0.25
REQUEST_TIMEOUT_SECONDS = 30

STORE_VERSION = 1
