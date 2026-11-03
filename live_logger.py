import csv
import time
import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
MQTT_PORT = 1884
MQTT_USER = "watcher"          # read-only user: a logger never needs to publish
MQTT_PASS = "watcher-pass-1"

OUT_FILE = "live_readings.csv"
PERIOD = 1.0                   # seconds between rows
STALE_AFTER = 5.0              # no fresh message for this long = data source is dead

last_fresh = time.time()       # when the last NEW (not retained) message arrived
bridge_online = True

# last known value of each signal (filled in as MQTT messages arrive)
latest = {"temperature": None, "vibration": None, "current": None, "speed": None}

def on_connect(client, userdata, flags, reason_code, properties):
    print("Logger connected, reason:", reason_code)
    client.subscribe("lab/motor/#")

def on_message(client, userdata, msg):
    global last_fresh, bridge_online
    name = msg.topic.split("/")[-1]          # e.g. lab/motor/temperature -> temperature
    if name == "status":
        bridge_online = msg.payload.decode() == "online"
    elif name in latest:
        latest[name] = float(msg.payload)
    if not msg.retain:                       # retained = old news replayed by the broker
        last_fresh = time.time()

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, MQTT_PORT)
client.loop_start()

try:
    with open(OUT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "temperature_C", "vibration_mm_s", "current_A", "rpm"])
        n = 0
        warned = False
        print(f"Logging one row every {PERIOD:.0f} s to {OUT_FILE}. Ctrl+C to stop.")
        while True:
            time.sleep(PERIOD)
            if any(v is None for v in latest.values()):
                continue                      # wait until every signal has a value
            stale = time.time() - last_fresh > STALE_AFTER
            if stale or not bridge_online:
                if not warned:
                    print("WARNING: no fresh data (bridge or server stopped?). Not writing rows.")
                    warned = True
                continue                      # never log frozen values as if they were real
            if warned:
                print("Fresh data is back, logging again.")
                warned = False
            writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"),
                             latest["temperature"], latest["vibration"],
                             latest["current"], latest["speed"]])
            f.flush()                         # so other programs can read it live
            n += 1
            if n % 10 == 0:
                print(f"{n} rows written")
except KeyboardInterrupt:
    print("\nLogger stopped.")
    client.loop_stop()
    client.disconnect()