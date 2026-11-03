import asyncio
import paho.mqtt.client as mqtt
from asyncua import Client, ua
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256

# --- OPC UA side (locked server) ---
OPC_URL = "opc.tcp://127.0.0.1:4840/motor/"
OPC_USER = "operator"
OPC_PASS = "lab-pass-1"

# --- MQTT side (locked broker) ---
BROKER = "127.0.0.1"
MQTT_PORT = 1884
MQTT_USER = "bridge"
MQTT_PASS = "bridge-pass-1"

TOPIC_ROOT = "lab/motor"
STATUS_TOPIC = f"{TOPIC_ROOT}/status"
WATCHED = ["Temperature", "Vibration", "Current", "Speed", "Running", "Alarm"]

# publish only if the value moved at least this much since the last published one
DEADBAND = {"Temperature": 0.05, "Vibration": 0.02, "Current": 0.02, "Speed": 1.0}

# MQTT client created first, so the last will can be registered before connecting
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
mqttc.username_pw_set(MQTT_USER, MQTT_PASS)
# LAST WILL: if this bridge disappears without saying goodbye, the BROKER
# publishes this message on our behalf.
mqttc.will_set(STATUS_TOPIC, "offline", qos=1, retain=True)

class Handler:
    """Called by asyncua whenever the OPC UA server reports a changed value."""
    def __init__(self):
        self.names = {}      # node id -> node name
        self.last = {}       # node name -> last value we published

    def datachange_notification(self, node, val, data):
        name = self.names[node.nodeid.to_string()]

        # deadband: skip changes that are too small to matter
        band = DEADBAND.get(name, 0)
        last = self.last.get(name)
        if band and last is not None and abs(val - last) < band:
            return
        self.last[name] = val

        topic = f"{TOPIC_ROOT}/{name.lower()}"
        # retain=True: the broker keeps the latest value for late subscribers
        mqttc.publish(topic, str(val), qos=1, retain=True)
        print(f"{topic} <- {val}")

async def main():
    mqttc.connect(BROKER, MQTT_PORT, keepalive=10)
    mqttc.loop_start()          # network loop runs in a background thread
    mqttc.publish(STATUS_TOPIC, "online", qos=1, retain=True)

    client = Client(OPC_URL)
    client.application_uri = "urn:lab:motor:client"
    client.set_user(OPC_USER)
    client.set_password(OPC_PASS)
    await client.set_security(
        SecurityPolicyBasic256Sha256,
        certificate="certs/client.der",
        private_key="certs/client-key.pem",
        server_certificate="certs/server.der",
        mode=ua.MessageSecurityMode.SignAndEncrypt,
    )
    async with client:
        idx = await client.get_namespace_index("http://lab.example/motor")
        motor = await client.nodes.objects.get_child([f"{idx}:Motor"])

        handler = Handler()
        nodes = []
        for name in WATCHED:
            n = await motor.get_child([f"{idx}:{name}"])
            handler.names[n.nodeid.to_string()] = name
            nodes.append(n)

        sub = await client.create_subscription(500, handler)
        await sub.subscribe_data_change(nodes)
        print(f"Bridge running: OPC UA -> MQTT ({TOPIC_ROOT}/...). Ctrl+C to stop.")

        while True:
            await asyncio.sleep(1)

try:
    asyncio.run(main())
except KeyboardInterrupt:
    # clean shutdown: the will is NOT sent for a normal disconnect, so say goodbye ourselves
    mqttc.publish(STATUS_TOPIC, "offline", qos=1, retain=True).wait_for_publish()
    mqttc.loop_stop()
    mqttc.disconnect()
    print("\nBridge stopped.")