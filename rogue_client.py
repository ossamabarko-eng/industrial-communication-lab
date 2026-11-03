import asyncio
from pymodbus.client import AsyncModbusTcpClient

ACTION = "stop"        # "stop" or "overspeed"

async def main():
    client = AsyncModbusTcpClient("127.0.0.1", port=5020)
    await client.connect()

    if ACTION == "overspeed":
        # coil 0 = run command: write False
        await client.write_coil(0, False, device_id=1)
        print("Sent: run = False")
    elif ACTION == "overspeed":
        # holding register 0 = speed setpoint: write 3000 rpm
        await client.write_register(0, 3000, device_id=1)
        print("Sent: speed setpoint = 3000 rpm")

    client.close()

asyncio.run(main())