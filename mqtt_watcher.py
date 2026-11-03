import paho.mqtt.client as mqtt

BROKER = "127.0.0.1"
MQTT_PORT = 1884
MQTT_USER = "watcher"
MQTT_PASS = "watcher-pass-1"

def on_connect(client, userdata, flags, reason_code, properties):
    print("Watcher connected, reason:", reason_code)
    client.subscribe("lab/motor/#")

def on_message(client, userdata, msg):
    topic, value = msg.topic, msg.payload.decode()
    tag = " (retained)" if msg.retain else ""
    if topic == "lab/motor/status":
        print(f"*** BRIDGE {value.upper()}{tag}")
    elif topic == "lab/motor/alarm":
        print(f"{'!!! ALARM ACTIVE' if value == 'True' else 'alarm cleared'}{tag}")
    else:
        print(f"{topic} = {value}{tag}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, MQTT_PORT)
client.loop_forever()