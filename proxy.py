import asyncio
import random

LISTEN_PORT = 5021               # clients connect here instead of 5020
SERVER = ("127.0.0.1", 5020)     # the real Modbus server
DELAY = 0.2                      # seconds added to every message, each direction
DROP = 0.15                      # probability that a message is silently lost

async def pipe(reader, writer, label):
    while True:
        data = await reader.read(1024)
        if not data:
            break
        if random.random() < DROP:
            print(f"{label}: DROPPED {len(data)} bytes")
            continue
        await asyncio.sleep(DELAY)
        writer.write(data)
        await writer.drain()
    writer.close()

async def handle(client_reader, client_writer):
    server_reader, server_writer = await asyncio.open_connection(*SERVER)
    await asyncio.gather(
        pipe(client_reader, server_writer, "request "),
        pipe(server_reader, client_writer, "response"),
    )

async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", LISTEN_PORT)
    print(f"Flaky proxy on port {LISTEN_PORT} -> {SERVER}  (delay {DELAY}s, drop {DROP:.0%})")
    async with server:
        await server.serve_forever()

asyncio.run(main())