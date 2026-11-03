import asyncio
import time
from pymodbus import pymodbus_apply_logging_config
from pymodbus.client import AsyncModbusTcpClient

PORT = 5021          # 5020 = direct to the server, 5021 = through the flaky proxy
TIMEOUT = 1.0        # seconds to wait for each reply
RETRIES = 0          # how many times pymodbus re-sends a request that got no reply
POLLS = 20

pymodbus_apply_logging_config("CRITICAL")   # keep the console readable

async def main():
    client = AsyncModbusTcpClient("127.0.0.1", port=PORT, timeout=TIMEOUT, retries=RETRIES)
    await client.connect()
    print(f"timeout={TIMEOUT}s retries={RETRIES}")

    # command: start the motor (this message can be lost too!)
    try:
        await client.write_coil(0, True, device_id=1)
        await client.write_register(0, 1500, device_id=1)
        print("Start command acknowledged")
    except Exception as e:
        print("Start command FAILED:", type(e).__name__)

    ok = failed = 0
    t0 = time.time()
    for i in range(POLLS):
        try:
            r = await client.read_input_registers(0, count=4, device_id=1)
            if r.isError():
                raise IOError(str(r))
            ok += 1
            print(f"poll {i:2d}: ok    speed={r.registers[3]:4d} rpm")
        except Exception as e:
            failed += 1
            print(f"poll {i:2d}: FAIL  ({type(e).__name__})")
        await asyncio.sleep(0.5)

    print(f"\n{ok} ok, {failed} failed, in {time.time() - t0:.0f} s")
    client.close()

asyncio.run(main())