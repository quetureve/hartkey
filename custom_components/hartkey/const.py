"""Constants for Hartkey integration."""

DOMAIN = "hartkey"
API_URL_DEVICES = "https://household.key.rt.ru/api/v2/app/devices/intercom"
API_URL_OPEN = "https://household.key.rt.ru/api/v2/app/devices/{intercom_id}/open"
API_URL_EVENTS = "https://events.key.rt.ru/api/v2/events/list"

CONF_BEARER_TOKEN = "bearer_token"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_UPDATE_INTERVAL = 5

PLATFORM_BUTTON = "button"
PLATFORM_SENSOR = "sensor"

EVENT_TYPES = [
    "api_open_remote",
    "face_open_remote", 
    "pin_code_open_remote",
    "code_open_local",
    "rfid_open_local",
    "dtmf_open_local"
]

ATTR_EVENT_TYPE = "event_type"
ATTR_RAISED_AT = "raised_at"
ATTR_DEVICE_ID = "device_id"
ATTR_USER_ID = "user_id"
ATTR_EVENT_TYPE_NAME = "event_type_name"
ATTR_EVENT_MESSAGE = "event_message"
ATTR_USER_AGENT = "user_agent"
ATTR_RFID = "rfid"

DEVICE_TYPE_INTERCOM = "intercom"
DEVICE_TYPE_GATE = "gate"

EVENT_TYPE_NAMES = {
    "api_open_remote": "Открытие через API",
    "face_open_remote": "Открытие по лицу",
    "pin_code_open_remote": "Открытие по пин-коду",
    "code_open_local": "Открытие по коду",
    "rfid_open_local": "Открытие по RFID",
    "dtmf_open_local": "Открытие по DTMF"
}