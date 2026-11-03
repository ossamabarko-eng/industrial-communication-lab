import asyncio
from asyncua import Client, ua
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256

SECURE = True            # must match the server
USERNAME = "operator"
PASSWORD = "lab-pass-1"

SETPOINT = 1500.0   # rpm
FAULT = 1           # fault to inject: 1 = bearing wear, 2 = overheating
FAULT_AT = 290      # seconds of healthy running before the fault is injected
FAULT_RAMP = 180    # seconds for the fault to develop fully (small = abrupt, large = gradual wear)
SECONDS = 480       # total run time

async def main():
    client = Client("opc.tcp://127.0.0.1:4840/motor/")
    if SECURE:
        client.application_uri = "urn:lab:motor:client"
        client.set_user(USERNAME)
        client.set_password(PASSWORD)
        await client.set_security(
            SecurityPolicyBasic256Sha256,
            certificate="certs/client.der",
            private_key="certs/client-key.pem",
            server_certificate="certs/server.der",     # we only trust THIS server
            mode=ua.MessageSecurityMode.SignAndEncrypt,
        )
    async with client:
        idx = await client.get_namespace_index("http://lab.example/motor")
        motor = await client.nodes.objects.get_child([f"{idx}:Motor"])

        # browse: the server describes itself (names, current values, units)
        print("Nodes under Motor:")
        for child in await motor.get_children():
            name = (await child.read_browse_name()).Name
            props = await child.get_properties()
            unit = await props[0].read_value() if props else ""
            print(f"   {name:14s} = {await child.read_value()!s:8}  [{unit}]")

        async def node(name):
            return await motor.get_child([f"{idx}:{name}"])

        # commands: write by name, no register addresses
        await (await node("Run")).write_value(True)
        await (await node("SpeedSetpoint")).write_value(SETPOINT)
        await (await node("FaultMode")).write_value(0, ua.VariantType.Int32)
        await (await node("FaultRampSeconds")).write_value(float(FAULT_RAMP))
        print(f"\nCommanded: run at {SETPOINT:.0f} rpm, healthy. Fault {FAULT} will be injected at t={FAULT_AT}s")

        temp, vib, cur, spd, alarm = [await node(n) for n in
                                      ("Temperature", "Vibration", "Current", "Speed", "Alarm")]
        for t in range(SECONDS):
            if t == FAULT_AT:
                await (await node("FaultMode")).write_value(FAULT, ua.VariantType.Int32)
                print(f"*** t={t}s: fault {FAULT} injected ***")
            if t % 5 == 0 or t == FAULT_AT:
                print(f"t={t:3d}s  temp: {await temp.read_value():5.1f} C | "
                  f"vib: {await vib.read_value():4.2f} mm/s | "
                  f"current: {await cur.read_value():4.2f} A | "
                  f"speed: {await spd.read_value():4.0f} rpm | alarm: {await alarm.read_value()}")
            await asyncio.sleep(1)

        # stop the motor and clear the fault when finished
        await (await node("Run")).write_value(False)
        await (await node("FaultMode")).write_value(0, ua.VariantType.Int32)

asyncio.run(main())