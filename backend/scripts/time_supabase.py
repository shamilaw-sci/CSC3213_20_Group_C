"""Time how long this computer takes to reach Supabase.

Run from the backend folder, with the venv active:
    python scripts/time_supabase.py

It only reads SUPABASE_URL and SUPABASE_KEY from .env and prints timings.
It does not print the key and does not change any data.
"""
import os
import socket
import ssl
import time
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()
url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_KEY"]
host = urlparse(url).hostname
headers = {"apikey": key, "Authorization": f"Bearer {key}"}


def ms(start):
    return f"{(time.perf_counter() - start) * 1000:7.0f} ms"


print(f"Supabase host: {host}")

# 1. DNS
t = time.perf_counter()
infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
print(f"DNS lookup:                       {ms(t)}")
addrs = []
for fam, _, _, _, sa in infos:
    if sa[0] not in [a[1][0] for a in addrs]:
        addrs.append((fam, sa))
for fam, sa in addrs:
    print(f"  address: {'IPv6' if fam == socket.AF_INET6 else 'IPv4'} {sa[0]}")

# 2. Plain TCP connect to each address (shows a dead IPv6 route)
for fam, sa in addrs:
    t = time.perf_counter()
    s = socket.socket(fam, socket.SOCK_STREAM)
    s.settimeout(10)
    try:
        s.connect(sa)
        print(f"TCP connect {'IPv6' if fam == socket.AF_INET6 else 'IPv4'}:                 {ms(t)}")
    except OSError as e:
        print(f"TCP connect {'IPv6' if fam == socket.AF_INET6 else 'IPv4'}: FAILED after {ms(t)} ({e})")
    finally:
        s.close()

# 3. TCP + TLS handshake the normal way
t = time.perf_counter()
ctx = ssl.create_default_context()
with socket.create_connection((host, 443), timeout=15) as raw:
    with ctx.wrap_socket(raw, server_hostname=host):
        pass
print(f"TCP + TLS handshake:              {ms(t)}")

# 4. One REST call per new connection (what the backend does today)
for i in range(3):
    t = time.perf_counter()
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{url}/rest/v1/roles?select=id&limit=1", headers=headers)
    print(f"REST call, new connection #{i + 1}:    {ms(t)}  (status {r.status_code})")

# 5. REST calls reusing one connection
with httpx.Client(timeout=30) as c:
    for i in range(3):
        t = time.perf_counter()
        r = c.get(f"{url}/rest/v1/roles?select=id&limit=1", headers=headers)
        print(f"REST call, reused connection #{i + 1}: {ms(t)}  (status {r.status_code})")

# 6. Creating a supabase-py client (done on every request)
try:
    from supabase import create_client

    t = time.perf_counter()
    create_client(url, key)
    print(f"supabase create_client():         {ms(t)}")
except Exception as e:  # noqa: BLE001
    print(f"supabase create_client() failed: {e}")

print("\nProxy settings seen by Python:",
      {k: v for k, v in os.environ.items() if k.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")} or "none")
