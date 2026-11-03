import asyncio
import ipaddress
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtendedKeyUsageOID
from asyncua.crypto import cert_gen

Path("certs").mkdir(exist_ok=True)

def make(name, uri):
    key = cert_gen.generate_private_key()
    cert = cert_gen.generate_self_signed_app_certificate(
        key,
        common_name=name,
        names={"countryName": "MA", "organizationName": "Industrial Communication Lab"},
        subject_alt_names=[
            x509.UniformResourceIdentifier(uri),
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ],
        extended=[ExtendedKeyUsageOID.CLIENT_AUTH, ExtendedKeyUsageOID.SERVER_AUTH],
        days=365,
    )
    Path(f"certs/{name}-key.pem").write_bytes(cert_gen.dump_private_key_as_pem(key))
    Path(f"certs/{name}.der").write_bytes(cert.public_bytes(Encoding.DER))
    print(f"created certs/{name}.der and certs/{name}-key.pem")

make("server", "urn:lab:motor:server")
make("client", "urn:lab:motor:client")