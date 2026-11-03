import asyncio
from pymodbus import pymodbus_apply_logging_config
from pymodbus.client import AsyncModbusSerialClient
from pymodbus.framer import FramerType

SETPOINT = 1500   # rpm
FAULT = 0         # 0 = healthy, 1 = bearing wear, 2 = overheating
SECONDS = 10
SHOW_FRAMES = True   # print the raw bytes of every frame

async def main():
    if SHOW_FRAMES:
        pymodbus_apply_logging_config("DEBUG")
    client = AsyncModbusSerialClient(
       "/tmp/ttyB",
        framer=FramerType.RTU,
        baudrate=9600,
        bytesize=8,
        parity="N",
        stopbits=1,
    )
    await client.connect()

    # commands: coil 0 (run), holding register 0 (setpoint), holding register 1 (fault mode)
    await client.write_coil(0, True, device_id=1)
    await client.write_register(0, SETPOINT, device_id=1)
    await client.write_register(1, FAULT, device_id=1)
    print("Commanded: run at", SETPOINT, "rpm, fault mode", FAULT)

    for t in range(SECONDS):
        ir = await client.read_input_registers(0, count=4, device_id=1)
        di = await client.read_discrete_inputs(0, count=2, device_id=1)
        r = ir.registers
        print(f"t={t:2d}s  temp: {r[0]/10:5.1f} C | vib: {r[1]/100:4.2f} mm/s | "
              f"current: {r[2]/100:4.2f} A | speed: {r[3]:4d} rpm | alarm: {di.bits[1]}")
        await asyncio.sleep(1)

    # stop the motor and clear the fault when finished
    await client.write_coil(0, False, device_id=1)
    await client.write_register(1, 0, device_id=1)
    client.close()

asyncio.run(main())