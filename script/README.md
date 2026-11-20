# Monitor de Servicios (Flask)
Servicio web ligero que verifica la disponibilidad de servicios y la muestra en un dashboard en tiempo real.

## Características
- **Tres tipos de verificación**: HTTP/HTTPS (código esperado), Ping (ICMP) y puertos TCP.
- **Monitoreo en segundo plano** con hilos: revisa todos los servicios en paralelo cada 10 s.
- **Métricas**: latencia actual y promedio, porcentaje de disponibilidad (uptime) e historial de las últimas 30 revisiones.
- **Dashboard** con tarjetas, gráfica de latencia (SVG) y barra de historial UP/DOWN.
- **API JSON** en `/api/status` y endpoint `/health`.

## Estructura
```
proyecto_monitoreo/
└── script/
    ├── app.py              # Lógica del monitor y rutas Flask
    ├── templates/
    │   └── index.html      # Dashboard
    ├── requirements.txt
    └── README.md
```

## Instalación y ejecución
```bash
cd script
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Abrir <http://localhost:5000>.

## Agregar un servicio
Edita la lista `SERVIDORES` en `app.py`:
```python
{"nombre": "Mi API", "tipo": "http", "destino": "https://miapi.com/health", "esperado": 200},
{"nombre": "Mi servidor", "tipo": "ping", "destino": "192.168.1.10"},
{"nombre": "MySQL", "tipo": "tcp", "destino": "192.168.1.10", "puerto": 3306},
```

## Rutas
| Ruta | Descripción |
|------|-------------|
| `/` | Dashboard |
| `/api/status` | Estado completo en JSON |
| `/health` | Health check del propio monitor |

## Capturas
### Servicios activos (UP)
![UP](capturas/up.png)

### Servicio caído (DOWN)
![DOWN](capturas/down.png)

## Notas
- El ping usa el comando `ping` del sistema (funciona en Windows, Linux y macOS).
- El servicio "Puerto cerrado (demo DOWN)" existe para mostrar cómo se ve una caída.
