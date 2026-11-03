import asyncio
from asyncua import Client, ua
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256

URL = "opc.tcp://127.0.0.1:4840/motor/"
MODE = "anonymous"   # "anonymous", "wrong_password", or "encrypted_wrong_password"

async def main():
    client = Client(URL, timeout=5)
    if MODE in ("wrong_password", "encrypted_wrong_password"):
        client.set_user("operator")
        client.set_password("guess123")
    if MODE == "encrypted_wrong_password":
        # a determined attacker can also speak the encrypted protocol
        client.application_uri = "urn:lab:motor:client"
        await client.set_security(
            SecurityPolicyBasic256Sha256,
            certificate="certs/client.der",
            private_key="certs/client-key.pem",
            server_certificate="certs/server.der",
            mode=ua.MessageSecurityMode.SignAndEncrypt,
        )
    try:
        async with client:
            idx = await client.get_namespace_index("http://lab.example/motor")
            motor = await client.nodes.objects.get_child([f"{idx}:Motor"])
            run = await motor.get_child([f"{idx}:Run"])
            await run.write_value(False)
            print("ATTACK SUCCEEDED: run = False was written")
    except Exception as e:
        print(f"Attack blocked: {type(e).__name__}: {str(e)[:90]}")

asyncio.run(main())