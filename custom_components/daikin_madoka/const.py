"""Daikin Madoka constants."""

DOMAIN = "daikin_madoka"
TITLE = "BRC1H"
UNIQUE_ID = "BRC1H-id"

MIN_TEMP = 16
MAX_TEMP = 32

# Seconds between polls of the device over its active BLE connection.
SCAN_INTERVAL = 60
# Seconds to wait for the initial connection before giving up setup (retried).
CONNECT_TIMEOUT = 30
