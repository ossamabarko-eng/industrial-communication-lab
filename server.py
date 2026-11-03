import asyncio
import random
from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.server import StartAsyncTcpServer

DT = 0.5  # seconds between simulation steps

async def update_loop(context):
    device = context[1]
    speed = 0.0
    temperature = 25.0
    fault_progress = 0.0   # 0 = healthy ... 1 = fault fully developed
    while True:
        # 1) read the commands written by the client
        run = device.getValues(1, 0, 1)[0]        # coil 0: run command
        setpoint = device.getValues(3, 0, 1)[0]   # holding register 0: speed setpoint
        setpoint = min(setpoint, 2000)            # safety limit
        fault = device.getValues(3, 1, 1)[0]      # holding register 1: 0 none, 1 bearing, 2 overheat

        # 2) speed ramps toward the target, at most 600 rpm per second
        target = setpoint if run else 0
        step = 600 * DT
        speed += max(-step, min(step, target - speed))

        # 3) a fault grows slowly while injected, and fades when removed
        if fault:
            fault_progress = min(1.0, fault_progress + DT / 20)
        else:
            fault_progress = max(0.0, fault_progress - DT / 10)
        bearing = fault_progress if fault == 1 else 0.0
        overheat = fault_progress if fault == 2 else 0.0

        # 4) everything else depends on speed and on the fault
        vibration = 0.2 + 0.0008 * speed + 3.5 * bearing + abs(random.gauss(0, 0.04))
        current = 0.0 if speed < 1 else (1.5 + 0.0025 * speed) * (1 + 0.3 * overheat) + random.gauss(0, 0.03)
        temp_target = 25 + 0.02 * speed + 6 * bearing + 45 * overheat
        temperature += (temp_target - temperature) * (DT / 15)

        # 5) publish sensors (input registers) and status bits (discrete inputs)
        device.setValues(4, 0, [
            int(temperature * 10),
            int(vibration * 100),
            int(max(current, 0) * 100),
            int(speed),
        ])
        device.setValues(2, 0, [int(speed > 1), int(temperature > 75 or vibration > 4.5)])

        print("run:", run, "setpoint:", setpoint, "fault:", fault, "speed:", int(speed))
        await asyncio.sleep(DT)

async def main():
    device = ModbusDeviceContext(
        ir=ModbusSequentialDataBlock(0, [0] * 16),
        di=ModbusSequentialDataBlock(0, [0] * 16),
        co=ModbusSequentialDataBlock(0, [0] * 16),
        hr=ModbusSequentialDataBlock(0, [0] * 16),
    )
    context = ModbusServerContext(devices=device, single=True)
    asyncio.create_task(update_loop(context))
    print("Server listening on port 5020")
    await StartAsyncTcpServer(context=context, address=("127.0.0.1", 5020))

asyncio.run(main())