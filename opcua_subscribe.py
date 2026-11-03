import asyncio
import time
from asyncua import Client, ua

SETPOINT = 1500.0   # rpm
FAULT = 1           # 0 = healthy, 1 = bearing wear, 2 = overheating
SECONDS = 30

class Handler:
    """Called by the library whenever the server reports a changed value."""
    def __init__(self):
        self.names = {}          # node id -> readable name
        self.t0 = time.time()
        self.count = 0

    def datachange_notification(self, node, val, data):
        self.count += 1
        name = self.names[node.nodeid.to_string()]
        print(f"[{time.time() - self.t0:5.1f}s] {name:12s} -> {val}")

async def main():
    async with Client("opc.tcp://127.0.0.1:4840/motor/") as client:
        idx = await client.get_namespace_index("http://lab.example/motor")
        motor = await client.nodes.objects.get_child([f"{idx}:Motor"])

        async def node(name):
            return await motor.get_child([f"{idx}:{name}"])

        # subscribe: tell the server which nodes we care about
        handler = Handler()
        watched = ["Speed", "Running", "Alarm", "Temperature"]
        nodes = [await node(n) for n in watched]
        for n, name in zip(nodes, watched):
            handler.names[n.nodeid.to_string()] = name
        sub = await client.create_subscription(500, handler)   # check every 500 ms
        await sub.subscribe_data_change(nodes)

        # now start the motor: from here on we only LISTEN, no read loop
        await (await node("Run")).write_value(True)
        await (await node("SpeedSetpoint")).write_value(SETPOINT)
        await (await node("FaultMode")).write_value(FAULT, ua.VariantType.Int32)
        print(f"Commanded: run at {SETPOINT:.0f} rpm, fault mode {FAULT}\n")

        await asyncio.sleep(SECONDS)

        await (await node("Run")).write_value(False)
        await (await node("FaultMode")).write_value(0, ua.VariantType.Int32)
        await sub.delete()
        print(f"\n{handler.count} notifications in {SECONDS} s")

asyncio.run(main())