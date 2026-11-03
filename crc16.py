def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc = crc >> 1
    return crc

frame = bytes.fromhex("01 05 00 00 ff 00")
crc = crc16(frame)
print("CRC: %04X" % crc)
print("on the wire (low byte first): %02X %02X" % (crc & 0xFF, crc >> 8))