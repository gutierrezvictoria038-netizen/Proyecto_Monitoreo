"""
Monitor de Servicios - Flask
============================
Verifica la disponibilidad de servicios mediante:
  * HTTP/HTTPS  -> codigo de estado esperado + latencia
  * PING (ICMP) -> alcanzabilidad del host
  * TCP         -> puerto abierto/cerrado

"""

import platform
import re
import socket
import subprocess
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from flask import Flask, jsonify, render_template

app = Flask(__name__)

# CONFIGURACION
INTERVALO_SEGUNDOS = 10   # cada cuanto se revisan los servicios
TIMEOUT_SEGUNDOS = 3      # tiempo maximo de espera por revision
HISTORIAL_MAX = 30        # muestras guardadas por servicio

SERVIDORES = [
    {"nombre": "Servicio Web Local", "tipo": "http",
     "destino": "http://localhost:5000/health", "esperado": 200},
    {"nombre": "Servidor Principal (httpbin)", "tipo": "http",
     "destino": "https://httpbin.org/status/200", "esperado": 200},
    {"nombre": "Google (HTTPS)", "tipo": "http",
     "destino": "https://www.google.com", "esperado": 200},
    {"nombre": "Google DNS (Ping)", "tipo": "ping",
     "destino": "8.8.8.8"},
    {"nombre": "Cloudflare DNS (Ping)", "tipo": "ping",
     "destino": "1.1.1.1"},
    {"nombre": "Google DNS (Puerto 53)", "tipo": "tcp",
     "destino": "8.8.8.8", "puerto": 53},
    {"nombre": "GitHub SSH (Puerto 22)", "tipo": "tcp",
     "destino": "github.com", "puerto": 22},
    {"nombre": "Puerto cerrado (demo DOWN)", "tipo": "tcp",
     "destino": "localhost", "puerto": 9},
]

# VERIFICADORES  (cada uno devuelve: estado, latencia_ms, detalle)
def verificar_http(srv):
    inicio = time.perf_counter()
    try:
        resp = requests.get(srv["destino"], timeout=TIMEOUT_SEGUNDOS)
        ms = (time.perf_counter() - inicio) * 1000
        if resp.status_code == srv.get("esperado", 200):
            return "UP", ms, f"HTTP {resp.status_code}"
        return "DOWN", ms, f"HTTP {resp.status_code} (esperado {srv.get('esperado', 200)})"
    except requests.exceptions.Timeout:
        return "DOWN", None, "Timeout"
    except requests.exceptions.RequestException as e:
        return "DOWN", None, type(e).__name__


def verificar_ping(srv):
    sistema = platform.system().lower()
    if sistema == "windows":
        cmd = ["ping", "-n", "1", "-w", str(TIMEOUT_SEGUNDOS * 1000), srv["destino"]]
    else:
        cmd = ["ping", "-c", "1", "-W", str(TIMEOUT_SEGUNDOS), srv["destino"]]
    inicio = time.perf_counter()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=TIMEOUT_SEGUNDOS + 2)
        ms = (time.perf_counter() - inicio) * 1000
        if r.returncode == 0:
            m = re.search(r"time[=<]\s*([\d.]+)", r.stdout)
            if m:
                ms = float(m.group(1))
            return "UP", ms, "Echo reply"
        return "DOWN", None, "Sin respuesta ICMP"
    except FileNotFoundError:
        return "DOWN", None, "Comando ping no disponible"
    except subprocess.TimeoutExpired:
        return "DOWN", None, "Timeout"


def verificar_tcp(srv):
    inicio = time.perf_counter()
    try:
        with socket.create_connection((srv["destino"], srv["puerto"]),
                                      timeout=TIMEOUT_SEGUNDOS):
            ms = (time.perf_counter() - inicio) * 1000
            return "UP", ms, f"Puerto {srv['puerto']} abierto"
    except socket.timeout:
        return "DOWN", None, "Timeout"
    except OSError:
        return "DOWN", None, f"Puerto {srv['puerto']} cerrado/inaccesible"


VERIFICADORES = {"http": verificar_http, "ping": verificar_ping, "tcp": verificar_tcp}

# ESTADO COMPARTIDO
lock = threading.Lock()
estado = {
    srv["nombre"]: {
        "historial": deque(maxlen=HISTORIAL_MAX),
        "total": 0,
        "exitosos": 0,
        "ultimo": None,
    }
    for srv in SERVIDORES
}
ultima_revision = {"timestamp": None}


def revisar(srv):
    try:
        est, ms, detalle = VERIFICADORES[srv["tipo"]](srv)
    except Exception as e:  # nunca debe caerse el monitor
        est, ms, detalle = "DOWN", None, f"Error interno: {type(e).__name__}"
    ahora = datetime.now().strftime("%H:%M:%S")
    with lock:
        s = estado[srv["nombre"]]
        s["total"] += 1
        if est == "UP":
            s["exitosos"] += 1
        s["historial"].append({"hora": ahora, "estado": est,
                               "latencia": round(ms, 2) if ms is not None else None})
        s["ultimo"] = {"estado": est,
                       "latencia": round(ms, 2) if ms is not None else None,
                       "detalle": detalle, "hora": ahora}


def ciclo_monitoreo():
    time.sleep(2)  # esperar a que Flask empiece a escuchar (para el check local)
    while True:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(revisar, SERVIDORES))
        ultima_revision["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time.sleep(INTERVALO_SEGUNDOS)


# RUTAS
@app.route("/")
def index():
    return render_template("index.html", intervalo=INTERVALO_SEGUNDOS)


@app.route("/health")
def health():
    """Endpoint que el propio monitor usa para verificar el 'Servicio Web Local'."""
    return jsonify(status="ok"), 200


@app.route("/api/status")
def api_status():
    servicios = []
    with lock:
        for srv in SERVIDORES:
            s = estado[srv["nombre"]]
            destino = srv["destino"] + (f":{srv['puerto']}" if "puerto" in srv else "")
            disponibilidad = round(100 * s["exitosos"] / s["total"], 1) if s["total"] else None
            lats = [h["latencia"] for h in s["historial"] if h["latencia"] is not None]
            servicios.append({
                "nombre": srv["nombre"],
                "tipo": srv["tipo"].upper(),
                "destino": destino,
                "ultimo": s["ultimo"],
                "disponibilidad": disponibilidad,
                "latencia_promedio": round(sum(lats) / len(lats), 2) if lats else None,
                "historial": list(s["historial"]),
            })
    arriba = sum(1 for s in servicios if s["ultimo"] and s["ultimo"]["estado"] == "UP")
    return jsonify({
        "resumen": {"total": len(servicios), "up": arriba,
                    "down": len(servicios) - arriba,
                    "ultima_revision": ultima_revision["timestamp"]},
        "servicios": servicios,
    })


if __name__ == "__main__":
    threading.Thread(target=ciclo_monitoreo, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
