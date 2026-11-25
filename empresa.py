"""
API de la empresa: la única forma de leer o cambiar el estado del negocio.

Versión simplificada del "Company MCP" de agentes-sas. Los agentes no modifican
los datos directamente: llaman estas funciones, que aplican las reglas de negocio
en código y no en los prompts:

- Un descuento mayor al 10 % necesita una decisión aprobada por el CEO.
- Un reembolso mayor a 5.000.000 COP también necesita aprobación del CEO.
- Nada se despacha antes de recibir el pago.
- Un pedido cancelado no recibe más trabajo y un pedido despachado no se cancela.
- Cada escritura es idempotente: repetir un pedido o una acción no la duplica.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta

LIMITE_DESCUENTO_GERENTE = 10.0          # % que puede autorizar el gerente comercial
LIMITE_REEMBOLSO_SIN_CEO = 5_000_000.0   # COP: por encima de esto el CEO debe aprobar

# Catálogo de TecnoNorte S.A.S. (precios en pesos colombianos). Los márgenes son distintos a propósito:
# un 30 % de descuento sigue dejando ganancia en teclados, pero no en cámaras web.
PRODUCTOS = {
    "PORTATIL-PRO": {"nombre": "Portátil Pro 14", "precio": 4_500_000.0, "costo": 3_300_000.0, "disponible": 10, "icono": "💻"},
    "MONITOR-27": {"nombre": "Monitor 4K de 27 pulgadas", "precio": 1_350_000.0, "costo": 900_000.0, "disponible": 25, "icono": "🖥️"},
    "DOCK-USBC": {"nombre": "Dock USB-C", "precio": 540_000.0, "costo": 330_000.0, "disponible": 2, "icono": "🔌"},
    "TECLADO-MX": {"nombre": "Teclado mecánico", "precio": 360_000.0, "costo": 180_000.0, "disponible": 60, "icono": "⌨️"},
    "DIADEMA-PRO": {"nombre": "Diadema con cancelación de ruido", "precio": 600_000.0, "costo": 450_000.0, "disponible": 30, "icono": "🎧"},
    "CAMARA-4K": {"nombre": "Cámara web 4K", "precio": 450_000.0, "costo": 360_000.0, "disponible": 20, "icono": "📷"},
}

CLIENTES = {
    "CLI-NORTE": {"nombre": "Comercializadora Norte S.A.S.", "segmento": "empresa", "estado": "ACTIVO", "cupo": 80_000_000.0},
    "CLI-CAFE": {"nombre": "Café Andino", "segmento": "pyme", "estado": "ACTIVO", "cupo": 8_000_000.0},
    "CLI-FRONTERA": {"nombre": "Ferretería La Frontera", "segmento": "pyme", "estado": "BLOQUEADO", "cupo": 0.0},
    "CLI-CLINICA": {"nombre": "Clínica Santa Ana", "segmento": "empresa", "estado": "ACTIVO", "cupo": 50_000_000.0},
    "CLI-HOTEL": {"nombre": "Hotel Tonchalá", "segmento": "empresa", "estado": "ACTIVO", "cupo": 150_000_000.0},
    "CLI-COLEGIO": {"nombre": "Colegio San José", "segmento": "pyme", "estado": "ACTIVO", "cupo": 15_000_000.0},
}


def cop(valor: float) -> str:
    """Formato de pesos colombianos: $ 4.500.000"""
    return "$ " + f"{valor:,.0f}".replace(",", ".")


class ErrorNegocio(Exception):
    """Respuesta de la API cuando una regla de negocio impide la acción."""

    def __init__(self, codigo: str, mensaje: str, reintentable: bool = False):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.reintentable = reintentable


@dataclass
class Pedido:
    id: str
    cliente_id: str
    lineas: list
    descuento_solicitado: float
    pago_cliente: float
    estado: str = "RECIBIDO"
    descuento_aprobado: float | None = None
    subtotal: float = 0.0
    total: float = 0.0
    pago_estado: str = "PENDIENTE"
    pago_recibido: float = 0.0
    reserva_estado: str = "PENDIENTE"
    factura: dict | None = None
    envio: dict | None = None
    reembolso: dict | None = None
    motivo_cancelacion: str | None = None
    creado: str = ""


@dataclass
class Empresa:
    productos: dict = field(default_factory=lambda: copy.deepcopy(PRODUCTOS))
    clientes: dict = field(default_factory=lambda: copy.deepcopy(CLIENTES))
    pedidos: dict = field(default_factory=dict)
    tareas: dict = field(default_factory=dict)
    decisiones: dict = field(default_factory=dict)
    eventos: list = field(default_factory=list)
    actividad: list = field(default_factory=list)
    estados: dict = field(default_factory=dict)      # estado de cada agente por pedido
    reloj: datetime = field(default_factory=lambda: datetime(2026, 11, 25, 9, 0, 0))
    contador: int = 0

    # ------------------------------------------------------------------ utilidades
    def ahora(self) -> str:
        self.reloj += timedelta(seconds=2)
        return self.reloj.strftime("%H:%M:%S")

    def nuevo_id(self, prefijo: str) -> str:
        self.contador += 1
        return f"{prefijo}-{self.contador:04d}"

    def pedido(self, pedido_id: str) -> Pedido:
        if pedido_id not in self.pedidos:
            raise ErrorNegocio("ORDER_NOT_FOUND", f"No existe el pedido {pedido_id}")
        return self.pedidos[pedido_id]

    def registrar_actividad(self, agente: str, herramienta: str, detalle: str, pedido_id: str, ok: bool = True):
        self.actividad.append({"hora": self.ahora(), "agente": agente, "herramienta": herramienta,
                               "detalle": detalle, "pedido": pedido_id, "ok": ok})

    def publicar(self, tipo: str, origen: str, pedido_id: str, datos: dict | None = None):
        evento = {"id": self.nuevo_id("EVT"), "hora": self.ahora(), "tipo": tipo, "origen": origen,
                  "pedido": pedido_id, "datos": datos or {}}
        self.eventos.append(evento)
        return evento

    # ------------------------------------------------------------------ consultas
    def subtotal(self, lineas) -> float:
        return round(sum(self.productos[l["producto"]]["precio"] * l["cantidad"] for l in lineas), 2)

    def margen_con_descuento(self, pedido: Pedido, descuento: float) -> float:
        venta = pedido.subtotal * (1 - descuento / 100)
        costo = sum(self.productos[l["producto"]]["costo"] * l["cantidad"] for l in pedido.lineas)
        return round(venta - costo, 2)

    def faltantes(self, pedido: Pedido) -> list:
        return [{"producto": self.productos[l["producto"]]["nombre"], "pedido": l["cantidad"],
                 "disponible": self.productos[l["producto"]]["disponible"]}
                for l in pedido.lineas if l["cantidad"] > self.productos[l["producto"]]["disponible"]]

    # ------------------------------------------------------------------ comandos
    def crear_pedido(self, pedido_id: str, cliente_id: str, lineas: list, descuento: float, pago: float):
        """Idempotente: si el pedido ya existe, no lo vuelve a crear."""
        if pedido_id in self.pedidos:
            return self.pedidos[pedido_id], False
        p = Pedido(id=pedido_id, cliente_id=cliente_id, lineas=lineas, descuento_solicitado=float(descuento),
                   pago_cliente=round(float(pago), 2), creado=self.reloj.strftime("%Y-%m-%d %H:%M"))
        p.subtotal = self.subtotal(lineas)
        self.pedidos[pedido_id] = p
        return p, True

    def validar_pedido(self, pedido_id: str, descuento: float):
        p = self.pedido(pedido_id)
        if p.estado == "CANCELADO":
            raise ErrorNegocio("ORDER_CANCELLED", "El pedido está cancelado")
        if p.estado != "RECIBIDO":
            return p
        cliente = self.clientes[p.cliente_id]
        if cliente["estado"] != "ACTIVO":
            raise ErrorNegocio("CUSTOMER_NOT_ACTIVE", f"El cliente {cliente['nombre']} está {cliente['estado'].lower()}")
        if p.subtotal > cliente["cupo"]:
            raise ErrorNegocio("CREDIT_LIMIT_EXCEEDED", f"El subtotal {cop(p.subtotal)} supera el cupo {cop(cliente['cupo'])}")
        if descuento > LIMITE_DESCUENTO_GERENTE:
            aprobada = any(d["tipo"] == "DESCUENTO_ESPECIAL" and d["pedido"] == pedido_id and d["estado"] == "APROBADA"
                           and d["valor"] >= descuento for d in self.decisiones.values())
            if not aprobada:
                raise ErrorNegocio("ESCALATION_REQUIRED", f"Un descuento de {descuento:g} % necesita aprobación del CEO")
        p.descuento_aprobado = float(descuento)
        p.total = round(p.subtotal * (1 - descuento / 100), 0)
        p.estado = "VALIDADO"
        return p

    def registrar_pago(self, pedido_id: str):
        p = self.pedido(pedido_id)
        if p.estado == "CANCELADO":
            raise ErrorNegocio("ORDER_CANCELLED", "El pedido está cancelado")
        if p.pago_estado == "RECIBIDO":
            return p
        if abs(p.pago_cliente - p.total) > 1:
            p.pago_estado = "RECHAZADO"
            raise ErrorNegocio("PAYMENT_REJECTED", f"El pago de {cop(p.pago_cliente)} no coincide con el total {cop(p.total)}")
        p.pago_estado = "RECIBIDO"
        p.pago_recibido = p.total
        return p

    def crear_factura(self, pedido_id: str):
        p = self.pedido(pedido_id)
        if p.factura is None:
            p.factura = {"id": f"FAC-{pedido_id}", "total": p.total, "estado": "EMITIDA"}
        return p.factura

    def reservar_inventario(self, pedido_id: str):
        p = self.pedido(pedido_id)
        if p.estado == "CANCELADO":
            raise ErrorNegocio("ORDER_CANCELLED", "El pedido está cancelado")
        if p.reserva_estado == "RESERVADO":
            return p
        faltan = self.faltantes(p)
        if faltan:
            texto = ", ".join(f"{f['producto']}: pedido {f['pedido']}, disponible {f['disponible']}" for f in faltan)
            raise ErrorNegocio("INVENTORY_UNAVAILABLE", texto)
        for l in p.lineas:
            self.productos[l["producto"]]["disponible"] -= l["cantidad"]
        p.reserva_estado = "RESERVADO"
        return p

    def crear_envio(self, pedido_id: str):
        p = self.pedido(pedido_id)
        if p.estado == "CANCELADO":
            raise ErrorNegocio("ORDER_CANCELLED", "El pedido está cancelado")
        if p.pago_estado != "RECIBIDO":
            raise ErrorNegocio("PAYMENT_PENDING", "No se despacha antes de recibir el pago")
        if p.envio is None:
            p.envio = {"id": f"ENV-{pedido_id}", "guia": f"CO{abs(hash(pedido_id)) % 10**9:09d}", "estado": "DESPACHADO"}
            p.estado = "DESPACHADO"
        return p.envio

    def cancelar_pedido(self, pedido_id: str, motivo: str):
        p = self.pedido(pedido_id)
        if p.estado == "DESPACHADO":
            raise ErrorNegocio("ORDER_SHIPPED", "Un pedido despachado no se puede cancelar")
        if p.estado == "CANCELADO":
            return p, 0.0
        if p.reserva_estado == "RESERVADO":
            for l in p.lineas:
                self.productos[l["producto"]]["disponible"] += l["cantidad"]
            p.reserva_estado = "LIBERADO"
        if p.factura:
            p.factura["estado"] = "ANULADA"
        p.estado = "CANCELADO"
        p.motivo_cancelacion = motivo
        return p, (p.pago_recibido if p.pago_estado == "RECIBIDO" else 0.0)

    def reembolsar(self, pedido_id: str):
        p = self.pedido(pedido_id)
        if p.reembolso:
            return p.reembolso
        if p.pago_recibido > LIMITE_REEMBOLSO_SIN_CEO:
            aprobada = any(d["tipo"] == "REEMBOLSO" and d["pedido"] == pedido_id and d["estado"] == "APROBADA"
                           for d in self.decisiones.values())
            if not aprobada:
                raise ErrorNegocio("ESCALATION_REQUIRED", f"Un reembolso de {cop(p.pago_recibido)} necesita aprobación del CEO")
        p.reembolso = {"valor": p.pago_recibido, "estado": "REEMBOLSADO"}
        p.pago_estado = "REEMBOLSADO"
        return p.reembolso

    def pedir_decision(self, pedido_id: str, tipo: str, valor: float, motivo: str, solicitante: str):
        for d in self.decisiones.values():
            if d["pedido"] == pedido_id and d["tipo"] == tipo and d["estado"] == "PENDIENTE":
                return d
        d = {"id": self.nuevo_id("DEC"), "pedido": pedido_id, "tipo": tipo, "valor": valor, "motivo": motivo,
             "solicitante": solicitante, "estado": "PENDIENTE", "razon": ""}
        self.decisiones[d["id"]] = d
        return d

    def cerrar_decision(self, decision_id: str, aprobada: bool, razon: str):
        d = self.decisiones[decision_id]
        d["estado"] = "APROBADA" if aprobada else "RECHAZADA"
        d["razon"] = razon
        return d
