import asyncio
import hmac
import random
from asyncua import Server, ua
from asyncua.crypto.permission_rules import SimpleRoleRuleset, User, UserRole

SECURE = True            # True: encryption + login required; False: open server (Lab 3 behaviour)
USERS = {"operator": "lab-pass-1"}   # lab only: real systems never keep passwords in code

DT = 0.5  # seconds between simulation steps

class PasswordUserManager:
    """Decides who may connect: returns a User for a correct login, None otherwise."""
    def get_user(self, iserver, username=None, password=None, certificate=None):
        expected = USERS.get(username)
        if expected is not None and password is not None and hmac.compare_digest(expected, password):
            return User(role=UserRole.User, name=username)
        return None

async def main():
    server = Server(user_manager=PasswordUserManager()) if SECURE else Server()
    await server.init()
    server.set_endpoint("opc.tcp://127.0.0.1:4840/motor/")
    if SECURE:
        await server.set_application_uri("urn:lab:motor:server")
        # only encrypted + signed connections are offered; no 'NoSecurity' endpoint
        server.set_security_policy(
            [ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt],
            permission_ruleset=SimpleRoleRuleset(),
        )
        server.set_identity_tokens([ua.UserNameIdentityToken])   # username + password only
        await server.load_certificate("certs/server.der")
        await server.load_private_key("certs/server-key.pem")
    idx = await server.register_namespace("http://lab.example/motor")

    motor = await server.nodes.objects.add_object(idx, "Motor")

    async def add_var(name, value, unit, vtype=None, writable=False):
        var = await motor.add_variable(idx, name, value, vtype)
        await var.add_property(idx, "EngineeringUnits", unit)
        if writable:
            await var.set_writable()      # clients may write this node
        return var

    # sensors and status: clients can only read them
    temperature = await add_var("Temperature", 25.0, "degC")
    vibration = await add_var("Vibration", 0.2, "mm/s")
    current = await add_var("Current", 0.0, "A")
    speed = await add_var("Speed", 0.0, "rpm")
    running = await add_var("Running", False, "bool")
    alarm = await add_var("Alarm", False, "bool")

    # commands: clients may write these
    run_cmd = await add_var("Run", False, "bool", writable=True)
    setpoint_cmd = await add_var("SpeedSetpoint", 0.0, "rpm", writable=True)
    fault_cmd = await add_var("FaultMode", 0, "0 none, 1 bearing, 2 overheat",
                              ua.VariantType.Int32, writable=True)
    ramp_cmd = await add_var("FaultRampSeconds", 20.0, "s from healthy to fully developed fault",
                             writable=True)

    async with server:
        print("OPC UA server running at opc.tcp://127.0.0.1:4840/motor/")
        spd, temp, progress = 0.0, 25.0, 0.0
        while True:
            # 1) read the commands written by clients
            run = await run_cmd.read_value()
            setpt = await setpoint_cmd.read_value()
            fault = await fault_cmd.read_value()
            ramp = await ramp_cmd.read_value()

            # 2) speed ramps toward the target, at most 600 rpm per second
            target = setpt if run else 0.0
            step = 600 * DT
            spd += max(-step, min(step, target - spd))

            # 3) a fault grows slowly while injected, and fades when removed
            if fault:
                progress = min(1.0, progress + DT / max(ramp, 1.0))
            else:
                progress = max(0.0, progress - DT / 10)
            bearing = progress if fault == 1 else 0.0
            overheat = progress if fault == 2 else 0.0

            # 4) the rest depends on speed and on the fault
            vib = 0.2 + 0.0008 * spd + 3.5 * bearing + abs(random.gauss(0, 0.04))
            cur = 0.0 if spd < 1 else (1.5 + 0.0025 * spd) * (1 + 0.3 * overheat) + random.gauss(0, 0.03)
            temp += (25 + 0.02 * spd + 6 * bearing + 45 * overheat - temp) * (DT / 15)

            # 5) publish real engineering values: no scaling needed
            # real sensors jitter on every channel: measurement noise sized like a cheap industrial sensor
            await temperature.write_value(round(temp + random.gauss(0, 1.0), 1))
            await vibration.write_value(round(max(vib + random.gauss(0, 0.2), 0.0), 2))
            await current.write_value(round(max(cur + random.gauss(0, 0.04), 0.0), 2))
            await speed.write_value(round(spd + random.gauss(0, 6), 0) if spd > 1 else 0.0)
            await running.write_value(spd > 1)
            await alarm.write_value(temp > 75 or vib > 4.5)

            print("run:", run, "setpoint:", setpt, "fault:", fault, "speed:", round(spd))
            await asyncio.sleep(DT)

asyncio.run(main())