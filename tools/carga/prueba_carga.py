"""Ejecuta un flujo concurrente con imágenes sintéticas en una instancia de ensayo."""

import argparse
import asyncio
import io
import math
import os
from collections import Counter
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import httpx
from PIL import Image

ETAPAS = (
    "Inicio de sesión",
    "Listado de casos",
    "Creación de caso",
    "Carga PNG",
    "Solicitud de análisis",
    "Tiempo hasta resultado",
)


@dataclass
class Intento:
    latencias: dict[str, float] = field(default_factory=dict)
    error: str | None = None


def png_sintetico() -> bytes:
    lado = 256
    pixeles = bytes((x + y) % 256 for y in range(lado) for x in range(lado))
    salida = io.BytesIO()
    Image.frombytes("L", (lado, lado), pixeles).save(salida, format="PNG")
    return salida.getvalue()


async def medir(cliente, intento, etapa, metodo, ruta, **opciones):
    inicio = perf_counter()
    respuesta = await cliente.request(metodo, ruta, **opciones)
    respuesta.raise_for_status()
    intento.latencias[etapa] = perf_counter() - inicio
    return respuesta.json()


async def esperar_resultado(cliente, analisis, intervalo, limite):
    async with asyncio.timeout(limite):
        while True:
            respuesta = await cliente.get(f"/api/analyses/{analisis}")
            respuesta.raise_for_status()
            estado = respuesta.json()["status"]
            if estado == "done":
                return
            if estado == "failed":
                raise RuntimeError("El worker devolvió failed")
            await asyncio.sleep(intervalo)


async def recorrer(cliente, args, correo, clave, png, referencia):
    intento = Intento()
    etapa = ETAPAS[0]
    try:
        token = await medir(
            cliente,
            intento,
            etapa,
            "POST",
            "/api/auth/login",
            data={"username": correo, "password": clave},
        )
        cliente.headers["Authorization"] = f"Bearer {token['access_token']}"
        etapa = ETAPAS[1]
        await medir(cliente, intento, etapa, "GET", "/api/cases")
        etapa = ETAPAS[2]
        caso = await medir(
            cliente, intento, etapa, "POST", "/api/cases", json={"patient_ref": referencia}
        )
        etapa = ETAPAS[3]
        imagen = await medir(
            cliente,
            intento,
            etapa,
            "POST",
            f"/api/cases/{caso['id']}/images",
            files={"file": ("sintetica.png", png, "image/png")},
        )
        etapa = ETAPAS[4]
        inicio = perf_counter()
        analisis = await medir(
            cliente, intento, etapa, "POST", f"/api/images/{imagen['id']}/analyses", json={}
        )
        etapa = ETAPAS[5]
        await esperar_resultado(cliente, analisis["id"], args.intervalo, args.espera)
        intento.latencias[etapa] = perf_counter() - inicio
    except httpx.HTTPStatusError as exc:
        intento.error = f"{etapa} / HTTP {exc.response.status_code}"
    except RuntimeError as exc:
        intento.error = f"{etapa} / {exc}"
    except (httpx.RequestError, TimeoutError, KeyError, ValueError, TypeError) as exc:
        intento.error = f"{etapa} / {type(exc).__name__}"
    return intento


def percentil(ordenadas, fraccion):
    posicion = (len(ordenadas) - 1) * fraccion
    inferior = math.floor(posicion)
    superior = math.ceil(posicion)
    return ordenadas[inferior] + (ordenadas[superior] - ordenadas[inferior]) * (posicion - inferior)


def resumir(n, intentos, duracion):
    errores = Counter(intento.error for intento in intentos if intento.error)
    fallidos = sum(errores.values())
    exitos = len(intentos) - fallidos
    usuarios = "usuario concurrente" if n == 1 else "usuarios concurrentes"
    lineas = [
        f"## {n} {usuarios}",
        "",
        f"- {exitos}/{len(intentos)} flujos completados en {duracion:.3f} s.",
        f"- Tasa de errores: {100 * fallidos / len(intentos):.2f} % ({fallidos}/{len(intentos)}).",
        f"- Throughput: {exitos / duracion:.3f} resultados completados/s.",
    ]
    lineas.extend(f"- {motivo}: {cantidad}." for motivo, cantidad in sorted(errores.items()))
    lineas.extend(
        [
            "",
            "| Etapa | n | p50 (ms) | p95 (ms) | p99 (ms) |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for etapa in ETAPAS:
        muestras = sorted(i.latencias[etapa] for i in intentos if etapa in i.latencias)
        valores = (
            [f"{1000 * percentil(muestras, p):.2f}" for p in (0.50, 0.95, 0.99)]
            if muestras
            else ["—"] * 3
        )
        lineas.append(f"| {etapa} | {len(muestras)} | {' | '.join(valores)} |")
    return lineas


async def ejecutar(args, correo, clave):
    fecha = datetime.now(UTC).isoformat(timespec="seconds")
    png = png_sintetico()
    identificador = uuid4().hex[:12]
    lineas = [
        "# Prueba de carga de EcoAudit",
        "",
        f"- Inicio UTC: {fecha}.",
        f"- Oleadas por escenario: {args.repeticiones}, con una sesión por usuario simulado.",
        f"- Imagen: PNG sintético de 256 × 256 px, {len(png)} bytes, sin datos personales.",
        f"- Sondeo del resultado cada {args.intervalo:g} s, con límite de {args.espera:g} s.",
        f"- Entorno: {args.entorno.rstrip('.')}.",
        "",
        "Los usuarios comparten una cuenta de ensayo con sesiones independientes. "
        "Los clientes HTTP se preparan antes de cronometrar cada oleada. "
        "Los percentiles interpolan las muestras exitosas de cada etapa. El tiempo hasta resultado "
        "va desde el inicio del POST de análisis hasta el primer GET que observa `done`. "
        "El throughput divide los resultados terminados por la duración de las oleadas del escenario.",
    ]
    hubo_errores = False
    for escenario, n in enumerate(args.concurrencia):
        intentos = []
        duracion = 0.0
        for oleada in range(args.repeticiones):
            async with AsyncExitStack() as sesiones:
                clientes = [
                    await sesiones.enter_async_context(
                        httpx.AsyncClient(base_url=args.url, timeout=30)
                    )
                    for _ in range(n)
                ]
                inicio = perf_counter()
                intentos.extend(
                    await asyncio.gather(
                        *(
                            recorrer(
                                cliente,
                                args,
                                correo,
                                clave,
                                png,
                                f"CARGA-{identificador}-{escenario}-{oleada}-{i}",
                            )
                            for i, cliente in enumerate(clientes)
                        )
                    )
                )
                duracion += perf_counter() - inicio
        lineas.extend(["", *resumir(n, intentos, duracion)])
        hubo_errores |= any(intento.error for intento in intentos)
    args.informe.parent.mkdir(parents=True, exist_ok=True)
    args.informe.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Informe guardado en {args.informe}")
    return int(hubo_errores)


def positivo(valor):
    numero = int(valor)
    if numero < 1:
        raise argparse.ArgumentTypeError("Debe ser un entero positivo.")
    return numero


def segundos(valor):
    numero = float(valor)
    if not math.isfinite(numero) or numero <= 0:
        raise argparse.ArgumentTypeError("Debe ser una duración positiva y finita.")
    return numero


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="URL base de la instancia de ensayo")
    parser.add_argument("--informe", required=True, type=Path, help="Archivo Markdown de salida")
    parser.add_argument("--concurrencia", nargs="+", type=positivo, default=[1, 5, 10])
    parser.add_argument("--repeticiones", type=positivo, default=1)
    parser.add_argument("--intervalo", type=segundos, default=0.2)
    parser.add_argument("--espera", type=segundos, default=90.0)
    parser.add_argument("--entorno", default="Sin especificar")
    args = parser.parse_args()
    correo = os.environ.get("ECOAUDIT_CARGA_EMAIL")
    clave = os.environ.get("ECOAUDIT_CARGA_PASSWORD")
    if not correo or not clave:
        parser.error("Defina ECOAUDIT_CARGA_EMAIL y ECOAUDIT_CARGA_PASSWORD en el entorno.")
    return asyncio.run(ejecutar(args, correo, clave))


if __name__ == "__main__":
    raise SystemExit(main())
