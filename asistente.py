"""
Agente de atención de TecnoNorte S.A.S.

Responde las preguntas del usuario consultando la API de la empresa: estado de un
pedido, por qué se canceló, inventario, precios, políticas, el equipo de agentes y
un resumen de ventas. Si hay una clave de Google Gemini configurada, las preguntas
abiertas las responde ese modelo de IA con el estado real de la empresa como contexto.
"""

from __future__ import annotations

import json
import re
import unicodedata

import requests

from agentes import AGENTES
from empresa import LIMITE_DESCUENTO_GERENTE, LIMITE_REEMBOLSO_SIN_CEO, Empresa, cop

ALIAS_PRODUCTOS = {
    "PORTATIL-PRO": ["portatil", "laptop", "computador", "pc"],
    "MONITOR-27": ["monitor", "pantalla"],
    "DOCK-USBC": ["dock", "usb"],
    "TECLADO-MX": ["teclado"],
    "DIADEMA-PRO": ["diadema", "audifono", "auricular"],
    "CAMARA-4K": ["camara", "webcam"],
}

ESTADOS = {"RECIBIDO": "recibido", "VALIDADO": "validado", "DESPACHADO": "despachado ✅", "CANCELADO": "cancelado ❌"}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def hay(t: str, *palabras) -> bool:
    return any(p in t for p in palabras)


def productos_mencionados(t: str):
    return [pid for pid, alias in ALIAS_PRODUCTOS.items() if any(a in t for a in alias)]


def resumen_pedido(e: Empresa, pid: str) -> str:
    p = e.pedidos[pid]
    cliente = e.clientes[p.cliente_id]["nombre"]
    lineas = ", ".join(f"{l['cantidad']} × {e.productos[l['producto']]['nombre']}" for l in p.lineas)
    partes = [f"**Pedido {pid}** de {cliente}: {lineas}.",
              f"Estado: **{ESTADOS.get(p.estado, p.estado.lower())}**."]
    if p.total:
        partes.append(f"Total con {p.descuento_aprobado:g} % de descuento: **{cop(p.total)}**.")
    partes.append(f"Pago: {p.pago_estado.lower()}. Inventario: {p.reserva_estado.lower()}.")
    if p.factura:
        partes.append(f"Factura {p.factura['id']} ({p.factura['estado'].lower()}).")
    if p.envio:
        partes.append(f"Envío con la guía **{p.envio['guia']}**.")
    if p.motivo_cancelacion:
        partes.append(f"Motivo de la cancelación: {p.motivo_cancelacion}.")
    if p.reembolso:
        partes.append(f"Se reembolsaron {cop(p.reembolso['valor'])}.")
    decisiones = [d for d in e.decisiones.values() if d["pedido"] == pid]
    for d in decisiones:
        partes.append(f"Decisión del CEO ({d['tipo'].replace('_', ' ').lower()}): {d['estado'].lower()}. {d['razon']}")
    return " ".join(partes)


def resumen_empresa(e: Empresa) -> dict:
    pedidos = list(e.pedidos.values())
    return {
        "pedidos": len(pedidos),
        "despachados": sum(p.estado == "DESPACHADO" for p in pedidos),
        "cancelados": sum(p.estado == "CANCELADO" for p in pedidos),
        "ventas": sum(p.total for p in pedidos if p.estado == "DESPACHADO"),
        "reembolsos": sum(p.reembolso["valor"] for p in pedidos if p.reembolso),
        "decisiones_ceo": len(e.decisiones),
    }


def responder_con_ia(pregunta: str, e: Empresa, historial: list, api_key: str, modelo: str = "gemini-2.0-flash"):
    contexto = {
        "productos": {k: {"nombre": v["nombre"], "precio_cop": v["precio"], "disponible": v["disponible"]} for k, v in e.productos.items()},
        "clientes": {k: {"nombre": v["nombre"], "estado": v["estado"], "cupo_cop": v["cupo"]} for k, v in e.clientes.items()},
        "pedidos": [resumen_pedido(e, pid) for pid in e.pedidos],
        "resumen": resumen_empresa(e),
        "agentes": {k: f"{v['nombre']}, {v['cargo']}: {v['funcion']}" for k, v in AGENTES.items()},
    }
    instrucciones = (
        "Eres el agente de atención de TecnoNorte S.A.S., una tienda de tecnología de Cúcuta operada por siete agentes de IA. "
        "Responde en español, breve y profesional, usando SOLO los datos del contexto. Los valores están en pesos colombianos. "
        f"Reglas: el gerente comercial autoriza descuentos hasta {LIMITE_DESCUENTO_GERENTE:g} %, más que eso lo decide el CEO; "
        f"los reembolsos mayores a {cop(LIMITE_REEMBOLSO_SIN_CEO)} los aprueba el CEO; nada se despacha sin pago. "
        "Si te piden algo que no está en los datos o que no tiene relación con la empresa, dilo con amabilidad.\n\n"
        "CONTEXTO:\n" + json.dumps(contexto, ensure_ascii=False))
    contenidos = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in historial[-6:]]
    contenidos.append({"role": "user", "parts": [{"text": pregunta}]})
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent?key={api_key}"
    cuerpo = {"system_instruction": {"parts": [{"text": instrucciones}]}, "contents": contenidos,
              "generationConfig": {"temperature": 0.3, "maxOutputTokens": 700}}
    try:
        r = requests.post(url, data=json.dumps(cuerpo), headers={"Content-Type": "application/json"}, timeout=25)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return None


def responder(pregunta: str, e: Empresa, historial: list | None = None, api_key: str | None = None):
    """Devuelve (respuesta, fuente) donde fuente es 'agente' o 'ia'."""
    t = normalizar(pregunta)

    # Consultas con datos exactos: siempre las resuelve el agente con la API de la empresa
    ids = re.findall(r"tn-\d{4}-\d{3}", t)
    if ids or hay(t, "mi pedido", "ultimo pedido", "el pedido", "estado del pedido"):
        if not e.pedidos:
            return "Todavía no hay pedidos. Haz uno en la pestaña **🛒 La tienda** y te cuento cómo va.", "agente"
        pid = ids[0].upper() if ids else list(e.pedidos)[-1]
        if pid not in e.pedidos:
            return f"No encuentro el pedido {pid}. Los pedidos existentes son: {', '.join(e.pedidos)}.", "agente"
        return resumen_pedido(e, pid), "agente"

    if api_key:
        respuesta = responder_con_ia(pregunta, e, historial or [], api_key)
        if respuesta:
            return respuesta, "ia"

    prods = productos_mencionados(t)
    if hay(t, "stock", "inventario", "disponib", "quedan", "unidades", "hay"):
        lista = prods or list(e.productos)
        filas = [f"- {e.productos[p]['icono']} **{e.productos[p]['nombre']}**: {e.productos[p]['disponible']} unidades disponibles"
                 for p in lista]
        return "Inventario actual en bodega:\n\n" + "\n".join(filas), "agente"
    if hay(t, "precio", "cuesta", "vale", "valor") and prods:
        return "\n".join(f"- **{e.productos[p]['nombre']}**: {cop(e.productos[p]['precio'])}" for p in prods), "agente"
    if hay(t, "descuento"):
        return (f"El **Gerente Comercial** puede autorizar hasta **{LIMITE_DESCUENTO_GERENTE:g} %** de descuento. "
                "Si el cliente pide más, el pedido se escala a la **CEO**, que solo lo aprueba si el cliente está activo "
                "y la venta sigue dejando ganancia después del descuento."), "agente"
    if hay(t, "reembolso", "devolu", "devolver"):
        return (f"Si un pedido pagado se cancela, Contabilidad devuelve el dinero. Hasta **{cop(LIMITE_REEMBOLSO_SIN_CEO)}** "
                "lo hace directamente el Contador; por encima de ese valor la **CEO** debe aprobar el reembolso."), "agente"
    if hay(t, "despach", "envio", "envia", "guia"):
        return ("Operaciones solo despacha cuando se cumplen dos condiciones: el **stock está reservado** y el "
                "**pago fue recibido**. Al despachar se genera un número de guía."), "agente"
    if hay(t, "agente", "equipo", "quien", "quienes", "organigrama", "empleado"):
        filas = [f"- {a['icono']} **{a['nombre']}**, {a['cargo']}: {a['funcion']}" for a in AGENTES.values()]
        return "El equipo de agentes de TecnoNorte S.A.S.:\n\n" + "\n".join(filas), "agente"
    if hay(t, "cliente"):
        filas = [f"- **{c['nombre']}** ({k}): {c['estado'].lower()}, cupo {cop(c['cupo'])}" for k, c in e.clientes.items()]
        return "Clientes registrados:\n\n" + "\n".join(filas), "agente"
    if hay(t, "venta", "resumen", "analisis", "cuanto", "cuantos", "reporte", "decision"):
        r = resumen_empresa(e)
        return (f"Resumen de la empresa: **{r['pedidos']}** pedidos, **{r['despachados']}** despachados y "
                f"**{r['cancelados']}** cancelados. Ventas despachadas: **{cop(r['ventas'])}**. "
                f"Reembolsos: {cop(r['reembolsos'])}. Decisiones tomadas por la CEO: {r['decisiones_ceo']}. "
                "Mira la pestaña **📊 Análisis** para ver las gráficas."), "agente"
    if prods:
        return "\n".join(f"- {e.productos[p]['icono']} **{e.productos[p]['nombre']}**: {cop(e.productos[p]['precio'])}, "
                         f"{e.productos[p]['disponible']} disponibles" for p in prods), "agente"
    if hay(t, "hola", "buenas", "buenos", "hey"):
        return ayuda(saludo=True), "agente"
    return ayuda(), "agente"


def ayuda(saludo: bool = False) -> str:
    inicio = ("¡Hola! 👋 Soy el agente de atención de **TecnoNorte S.A.S.** Te cuento qué pasa en la empresa.\n\n"
              if saludo else "Puedo ayudarte con esto:\n\n")
    return inicio + ("- 📦 **Pedidos:** *¿cómo va mi pedido?* o *estado del pedido TN-2026-001*\n"
                     "- 🏷️ **Inventario y precios:** *¿cuántos portátiles quedan?*, *precio del monitor*\n"
                     "- 📜 **Políticas:** *¿quién aprueba un descuento del 25 %?*, *¿cómo funcionan los reembolsos?*\n"
                     "- 👥 **Equipo:** *¿qué hace cada agente?*\n"
                     "- 📊 **Análisis:** *resumen de ventas*")
