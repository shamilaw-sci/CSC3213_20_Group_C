"""Speed check to compare two laptops running the VFF backend.

How to run (in the backend folder, with the venv active):
    python scripts/diagnose_speed.py

Start the backend first (uvicorn on port 8000) if you want the backend timings.
It reads SUPABASE_URL and SUPABASE_KEY from .env, only reads data, and never
prints the key. Copy everything it prints and send it back.
"""
import importlib.metadata as md
import os
import platform
import socket
import ssl
import statistics
import subprocess
import sys
import time
from urllib.parse import urlparse

T0 = time.perf_counter()
import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()
URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_KEY"]
HOST = urlparse(URL).hostname
HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}
REPEAT = 5


def ms(seconds):
    return f"{seconds * 1000:.0f} ms"


def summary(samples):
    return (f"median {ms(statistics.median(samples))}, "
            f"min {ms(min(samples))}, max {ms(max(samples))}")


def timed(fn):
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


def powershell(cmd):
    if platform.system() != "Windows":
        return "n/a (not Windows)"
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=30,
        )
        return (out.stdout or out.stderr).strip() or "(empty)"
    except Exception as e:  # noqa: BLE001
        return f"failed: {e}"


def section(title):
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------- computer
section("Computer")
print("OS:", platform.platform())
print("Python:", sys.version.split()[0], "|", sys.executable)
print("CPU:", platform.processor() or "unknown", "| cores:", os.cpu_count())
for pkg in ("supabase", "httpx", "fastapi", "uvicorn", "postgrest", "gotrue", "supabase_auth"):
    try:
        print(f"  {pkg}: {md.version(pkg)}")
    except md.PackageNotFoundError:
        pass
print("Power plan:", powershell("powercfg /getactivescheme"))
print("On battery:", powershell(
    "(Get-CimInstance Win32_Battery | Select-Object -First 1).BatteryStatus "
    "-replace '^1$','yes (discharging)' -replace '^2$','no (plugged in)'"))
print("Antivirus:", powershell(
    "(Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct "
    "| Select-Object -ExpandProperty displayName) -join ', '"))
print("Defender real-time on:", powershell(
    "(Get-MpComputerStatus).RealTimeProtectionEnabled"))
print("Defender excluded folders:", powershell(
    "(Get-MpPreference).ExclusionPath -join ', '"))
print("VPN / network adapters up:", powershell(
    "(Get-NetAdapter | Where-Object Status -eq 'Up' | "
    "ForEach-Object { $_.InterfaceDescription }) -join ' | '"))
print("DNS servers:", powershell(
    "(Get-DnsClientServerAddress -AddressFamily IPv4 | "
    "Where-Object ServerAddresses | ForEach-Object { $_.ServerAddresses }) -join ', '"))
print("Proxy env vars:", {k: v for k, v in os.environ.items()
                          if k.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")} or "none")

# ---------------------------------------------------------------- CPU speed
section("CPU speed (same work on every laptop)")
cpu = [timed(lambda: sum(i * i for i in range(2_000_000))) for _ in range(3)]
print("Python loop:", summary(cpu))
print("Import httpx + dotenv:", ms(time.perf_counter() - T0))
t = time.perf_counter()
from supabase import create_client  # noqa: E402
print("Import supabase:", ms(time.perf_counter() - t))
print("create_client():", summary([timed(lambda: create_client(URL, KEY)) for _ in range(REPEAT)]))

# ---------------------------------------------------------------- network
section(f"Network to Supabase ({HOST})")
dns = []
for _ in range(REPEAT):
    t = time.perf_counter()
    infos = socket.getaddrinfo(HOST, 443, proto=socket.IPPROTO_TCP)
    dns.append(time.perf_counter() - t)
print("DNS lookup:", summary(dns))
print("Addresses:", sorted({i[4][0] for i in infos}))


def tls_handshake():
    ctx = ssl.create_default_context()
    with socket.create_connection((HOST, 443), timeout=15) as raw:
        with ctx.wrap_socket(raw, server_hostname=HOST) as s:
            return s.getpeercert().get("issuer")


issuer = tls_handshake()
print("TCP + TLS handshake:", summary([timed(tls_handshake) for _ in range(REPEAT)]))
# A certificate issued by an antivirus (not Google Trust Services / Let's
# Encrypt / Cloudflare) means it is inspecting HTTPS traffic.
print("Certificate issuer:", ", ".join(v for part in issuer for k, v in part if k in ("organizationName", "commonName")))

PATH = f"{URL}/rest/v1/roles?select=id&limit=1"


def new_conn_call():
    with httpx.Client(timeout=30) as c:
        c.get(PATH, headers=HEADERS).raise_for_status()


print("REST call, new connection:", summary([timed(new_conn_call) for _ in range(REPEAT)]))
with httpx.Client(timeout=30) as c:
    c.get(PATH, headers=HEADERS)
    reused = []
    for _ in range(REPEAT):
        t = time.perf_counter()
        r = c.get(PATH, headers=HEADERS)
        reused.append(time.perf_counter() - t)
    print("REST call, reused connection:", summary(reused))
    print("  server headers:", {k: r.headers.get(k) for k in ("cf-ray", "server", "x-envoy-upstream-service-time") if r.headers.get(k)})
with httpx.Client(timeout=30) as c:
    auth = [timed(lambda: c.get(f"{URL}/auth/v1/health", headers=HEADERS)) for _ in range(REPEAT)]
print("Auth health call:", summary(auth))

# ---------------------------------------------------------------- backend
section("Local backend (port 8000)")
for name, base in (("127.0.0.1", "http://127.0.0.1:8000"), ("localhost", "http://localhost:8000")):
    try:
        with httpx.Client(timeout=30) as c:
            samples = [timed(lambda: c.get(f"{base}/openapi.json")) for _ in range(3)]
        print(f"GET {name}:8000/openapi.json:", summary(samples))
    except Exception as e:  # noqa: BLE001
        print(f"GET {name}:8000: not reachable ({type(e).__name__}). Is the backend running?")
print("localhost resolves to:", sorted({i[4][0] for i in socket.getaddrinfo('localhost', 8000)}))

print(f"\nTotal run time: {ms(time.perf_counter() - T0)}")
