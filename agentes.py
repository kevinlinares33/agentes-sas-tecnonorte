"""
Los siete agentes de TecnoNorte S.A.S. y el bus de eventos que los coordina.

Cada agente tiene un cargo, un jefe, una autoridad y unas herramientas permitidas
(igual que las "descripciones de cargo" en prompts/ de agentes-sas). Los agentes
no se hablan directamente: reaccionan a eventos de negocio y solo pueden cambiar
el estado de la empresa a través de la API de empresa.py.

Un evento = un turno de trabajo de un agente.
"""

from __future__ import annotations

from empresa import (LIMITE_DESCUENTO_GERENTE, LIMITE_REEMBOLSO_SIN_CEO, Empresa, ErrorNegocio, cop)

# ---------------------------------------------------------------------------
# Organigrama: quiénes son, a quién reportan y qué herramientas pueden usar
# ---------------------------------------------------------------------------
AGENTES = {
    "ceo": {"nombre": "Valentina Rojas", "cargo": "CEO", "departamento": "Dirección", "icono": "👩‍💼", "jefe": None,
            "funcion": "Decide lo que supera la autoridad de los gerentes: descuentos mayores al 10 % y reembolsos grandes.",
            "herramientas": ["leer_decision", "consultar_margen", "consultar_cliente", "aprobar_decision", "rechazar_decision"]},
    "gerente-comercial": {"nombre": "Andrés Pérez", "cargo": "Gerente Comercial", "departamento": "Comercial", "icono": "🧑‍💼",
                          "jefe": "ceo", "funcion": "Recibe el pedido, delega la validación del cliente y autoriza descuentos hasta el 10 %.",
                          "herramientas": ["asignar_tarea", "validar_pedido", "solicitar_aprobacion_ceo", "cancelar_pedido"]},
    "vendedor": {"nombre": "Laura Gómez", "cargo": "Asesora Comercial", "departamento": "Comercial", "icono": "🧑‍💻",
                 "jefe": "gerente-comercial", "funcion": "Verifica que el cliente esté activo y que el pedido quepa en su cupo.",
                 "herramientas": ["consultar_cliente", "consultar_pedido", "completar_tarea", "fallar_tarea"]},
    "gerente-operaciones": {"nombre": "Camilo Duarte", "cargo": "Gerente de Operaciones", "departamento": "Operaciones", "icono": "👨‍🔧",
                            "jefe": "ceo", "funcion": "Ordena reservar el stock y despachar solo cuando hay reserva y pago.",
                            "herramientas": ["asignar_tarea", "consultar_estado", "cancelar_pedido"]},
    "logistica": {"nombre": "Sergio Ortega", "cargo": "Coordinador de Logística", "departamento": "Operaciones", "icono": "📦",
                  "jefe": "gerente-operaciones", "funcion": "Reserva el inventario y crea el envío con su número de guía.",
                  "herramientas": ["reservar_inventario", "crear_envio", "completar_tarea", "fallar_tarea"]},
    "gerente-contabilidad": {"nombre": "Natalia Suárez", "cargo": "Gerente de Contabilidad", "departamento": "Contabilidad", "icono": "👩‍💼",
                             "jefe": "ceo", "funcion": "Ordena cobrar y facturar, y gestiona los reembolsos de pedidos cancelados.",
                             "herramientas": ["asignar_tarea", "solicitar_aprobacion_ceo", "cancelar_pedido"]},
    "contador": {"nombre": "Julián Castro", "cargo": "Contador", "departamento": "Contabilidad", "icono": "🧾",
                 "jefe": "gerente-contabilidad", "funcion": "Registra el pago, emite la factura y hace los reembolsos.",
                 "herramientas": ["registrar_pago", "crear_factura", "reembolsar_pago", "completar_tarea", "fallar_tarea"]},
}

DEPARTAMENTOS = ["Comercial", "Operaciones", "Contabilidad"]

TIPOS_TAREA = {"ValidarCliente": "vendedor", "ReservarInventario": "logistica", "Despachar": "logistica",
               "LiquidarPedido": "contador", "Reembolsar": "contador"}

NOMBRE_EVENTO = {
    "PedidoRecibido": "Pedido recibido", "PedidoDuplicado": "Pedido duplicado ignorado",
    "TareaAsignada": "Tarea asignada", "TareaCompletada": "Tarea completada", "TareaFallida": "Tarea fallida",
    "PedidoValidado": "Pedido validado", "DecisionSolicitada": "Decisión escalada al CEO",
    "DecisionAprobada": "El CEO aprobó", "DecisionRechazada": "El CEO rechazó", "PagoRecibido": "Pago recibido",
    "PedidoCancelado": "Pedido cancelado", "ReembolsoRealizado": "Reembolso realizado", "PedidoDespachado": "Pedido despachado",
}


class Orquestador:
    """Bus de eventos: entrega cada evento al agente que el organigrama indica."""

    def __init__(self, empresa: Empresa):
        self.e = empresa
        self.cola: list = []

    # ------------------------------------------------------------------ utilidades
    def estado(self, pid, agente, estado, nota):
        self.e.estados.setdefault(pid, {a: {"estado": "En espera", "nota": "Sin trabajo en este pedido"} for a in AGENTES})
        self.e.estados[pid][agente] = {"estado": estado, "nota": nota}

    def herramienta(self, agente, nombre, detalle, pid, ok=True):
        self.e.registrar_actividad(agente, nombre, detalle, pid, ok)

    def emitir(self, tipo, origen, pid, descripcion, **datos):
        datos["descripcion"] = descripcion
        self.cola.append(self.e.publicar(tipo, origen, pid, datos))

    def asignar(self, jefe, tipo, pid, motivo):
        trabajador = TIPOS_TAREA[tipo]
        tid = f"TAR-{pid}-{tipo}-{len(self.e.tareas) + 1}"
        self.e.tareas[tid] = {"id": tid, "tipo": tipo, "pedido": pid, "asignada_a": trabajador, "por": jefe, "estado": "PENDIENTE", "resultado": ""}
        self.herramienta(jefe, "asignar_tarea", f"{tipo} para {AGENTES[trabajador]['cargo']}: {motivo}", pid)
        self.estado(pid, jefe, "Delegó", f"Asignó {tipo} a {AGENTES[trabajador]['nombre']}")
        self.emitir("TareaAsignada", jefe, pid, f"{AGENTES[jefe]['cargo']} asigna {tipo} a {AGENTES[trabajador]['cargo']}. {motivo}",
                    tarea=tid, tipo_tarea=tipo, para=trabajador)

    def terminar(self, agente, tid, ok, resultado, codigo=None):
        t = self.e.tareas[tid]
        t["estado"] = "COMPLETADA" if ok else "FALLIDA"
        t["resultado"] = resultado
        self.herramienta(agente, "completar_tarea" if ok else "fallar_tarea", resultado, t["pedido"], ok)
        self.estado(t["pedido"], agente, "Terminó" if ok else "Reportó un problema", resultado)
        self.emitir("TareaCompletada" if ok else "TareaFallida", agente, t["pedido"], resultado,
                    tarea=tid, tipo_tarea=t["tipo"], para=t["por"], codigo=codigo)

    def cancelar(self, agente, pid, motivo):
        try:
            p, reembolso = self.e.cancelar_pedido(pid, motivo)
        except ErrorNegocio as err:
            self.herramienta(agente, "cancelar_pedido", err.mensaje, pid, False)
            return
        self.herramienta(agente, "cancelar_pedido", motivo, pid)
        self.estado(pid, agente, "Canceló el pedido", motivo)
        extra = f" Se debe reembolsar {cop(reembolso)}." if reembolso else " No hubo cobro, no hay nada que reembolsar."
        self.emitir("PedidoCancelado", agente, pid, f"Pedido cancelado: {motivo}.{extra}", reembolso=reembolso, motivo=motivo)

    # ------------------------------------------------------------------ entrada
    def recibir_pedido(self, pid, cliente_id, lineas, descuento, pago):
        p, nuevo = self.e.crear_pedido(pid, cliente_id, lineas, descuento, pago)
        if not nuevo:
            self.e.publicar("PedidoDuplicado", "tienda", pid, {"descripcion":
                            "El pedido ya existía. La API es idempotente: no se creó otro pedido ni se repitió ningún cobro."})
            return p, False
        cliente = self.e.clientes[cliente_id]["nombre"]
        self.estado(pid, "gerente-comercial", "En espera", "Pedido en su bandeja de entrada")
        self.emitir("PedidoRecibido", "tienda", pid,
                    f"{cliente} compra por {cop(p.subtotal)} y solicita {descuento:g} % de descuento. Pago enviado: {cop(pago)}.")
        self.procesar()
        return p, True

    def procesar(self):
        """Entrega cada evento a sus suscriptores hasta que no quede trabajo."""
        pasos = 0
        while self.cola and pasos < 200:
            pasos += 1
            ev = self.cola.pop(0)
            for agente in self.suscriptores(ev):
                getattr(self, "turno_" + agente.replace("-", "_"))(ev)

    def suscriptores(self, ev):
        t, d = ev["tipo"], ev["datos"]
        if t == "PedidoRecibido":
            return ["gerente-comercial"]
        if t == "TareaAsignada":
            return [d["para"]]
        if t in ("TareaCompletada", "TareaFallida"):
            return [d["para"]]
        if t == "DecisionSolicitada":
            return ["ceo"]
        if t in ("DecisionAprobada", "DecisionRechazada"):
            return [d["solicitante"]]
        if t == "PedidoValidado":
            return ["gerente-contabilidad", "gerente-operaciones"]
        if t == "PagoRecibido":
            return ["gerente-operaciones"]
        if t == "PedidoCancelado":
            return ["gerente-contabilidad"]
        return []

    # ------------------------------------------------------------------ Comercial
    def turno_gerente_comercial(self, ev):
        a, pid, t, d = "gerente-comercial", ev["pedido"], ev["tipo"], ev["datos"]
        p = self.e.pedido(pid)
        if p.estado in ("CANCELADO",) and t != "PedidoRecibido":
            return
        if t == "PedidoRecibido":
            self.estado(pid, a, "Trabajando", "Revisa el pedido nuevo")
            self.asignar(a, "ValidarCliente", pid, "Verificar estado y cupo del cliente, y reportar el descuento pedido.")
        elif t == "TareaCompletada" and d["tipo_tarea"] == "ValidarCliente":
            desc = p.descuento_solicitado
            if desc <= LIMITE_DESCUENTO_GERENTE:
                self.validar(a, pid, desc)
            else:
                dec = self.e.pedir_decision(pid, "DESCUENTO_ESPECIAL", desc,
                                            f"El cliente pide {desc:g} %, por encima de mi límite de {LIMITE_DESCUENTO_GERENTE:g} %", a)
                self.herramienta(a, "solicitar_aprobacion_ceo", f"Descuento especial de {desc:g} % ({dec['id']})", pid)
                self.estado(pid, a, "Escaló al CEO", f"Espera la decisión sobre {desc:g} % de descuento")
                self.emitir("DecisionSolicitada", a, pid,
                            f"El Gerente Comercial solo puede autorizar hasta {LIMITE_DESCUENTO_GERENTE:g} %. Escala al CEO un descuento de {desc:g} %.",
                            decision=dec["id"], tipo_decision="DESCUENTO_ESPECIAL", solicitante=a)
        elif t == "TareaFallida" and d["tipo_tarea"] == "ValidarCliente":
            self.cancelar(a, pid, f"cliente no elegible ({d['descripcion']})")
        elif t == "DecisionAprobada" and d["tipo_decision"] == "DESCUENTO_ESPECIAL":
            self.validar(a, pid, p.descuento_solicitado)
        elif t == "DecisionRechazada" and d["tipo_decision"] == "DESCUENTO_ESPECIAL":
            self.cancelar(a, pid, f"el descuento de {p.descuento_solicitado:g} % no fue aprobado por el CEO")

    def validar(self, a, pid, desc):
        try:
            p = self.e.validar_pedido(pid, desc)
        except ErrorNegocio as err:
            self.herramienta(a, "validar_pedido", err.mensaje, pid, False)
            self.cancelar(a, pid, err.mensaje.lower())
            return
        self.herramienta(a, "validar_pedido", f"Descuento {desc:g} %. Total a cobrar {cop(p.total)}", pid)
        self.estado(pid, a, "Terminó", f"Validó el pedido con {desc:g} % de descuento")
        self.emitir("PedidoValidado", a, pid, f"Pedido validado con {desc:g} % de descuento. Total: {cop(p.total)}.", total=p.total)

    def turno_vendedor(self, ev):
        a, pid, d = "vendedor", ev["pedido"], ev["datos"]
        p = self.e.pedido(pid)
        self.estado(pid, a, "Trabajando", "Revisa al cliente")
        c = self.e.clientes[p.cliente_id]
        self.herramienta(a, "consultar_cliente", f"{c['nombre']}: {c['estado'].lower()}, cupo {cop(c['cupo'])}", pid)
        if p.estado == "CANCELADO":
            self.terminar(a, d["tarea"], False, "El pedido ya está cancelado", "ORDER_CANCELLED")
        elif c["estado"] != "ACTIVO":
            self.terminar(a, d["tarea"], False, f"El cliente {c['nombre']} está {c['estado'].lower()}", "CUSTOMER_NOT_ELIGIBLE")
        elif p.subtotal > c["cupo"]:
            self.terminar(a, d["tarea"], False, f"El subtotal {cop(p.subtotal)} supera el cupo de {cop(c['cupo'])}", "CUSTOMER_NOT_ELIGIBLE")
        else:
            self.terminar(a, d["tarea"], True,
                          f"Cliente {c['nombre']} activo y dentro de su cupo. Descuento solicitado: {p.descuento_solicitado:g} %.")

    # ------------------------------------------------------------------ CEO
    def turno_ceo(self, ev):
        a, pid, d = "ceo", ev["pedido"], ev["datos"]
        dec = self.e.decisiones[d["decision"]]
        p = self.e.pedido(pid)
        self.estado(pid, a, "Decidiendo", f"Analiza {dec['tipo'].replace('_', ' ').lower()}")
        self.herramienta(a, "leer_decision", f"{dec['id']}: {dec['motivo']}", pid)
        if dec["tipo"] == "DESCUENTO_ESPECIAL":
            margen = self.e.margen_con_descuento(p, dec["valor"])
            cliente = self.e.clientes[p.cliente_id]
            self.herramienta(a, "consultar_margen", f"Margen con {dec['valor']:g} %: {cop(margen)}", pid)
            aprobar = cliente["estado"] == "ACTIVO" and margen > 0
            razon = (f"Apruebo: con {dec['valor']:g} % el margen sigue positivo ({cop(margen)}) y {cliente['nombre']} es cliente activo."
                     if aprobar else f"Rechazo: con {dec['valor']:g} % el pedido deja pérdida ({cop(margen)}). Protejo el margen de la empresa.")
        else:
            aprobar = p.estado == "CANCELADO" and abs(p.pago_recibido - dec["valor"]) < 1
            razon = (f"Apruebo: el pedido está cancelado y el cliente pagó {cop(p.pago_recibido)}. Se le debe devolver."
                     if aprobar else "Rechazo: el valor pedido no coincide con lo que el cliente pagó.")
        self.e.cerrar_decision(dec["id"], aprobar, razon)
        self.herramienta(a, "aprobar_decision" if aprobar else "rechazar_decision", razon, pid, aprobar)
        self.estado(pid, a, "Aprobó" if aprobar else "Rechazó", razon)
        self.emitir("DecisionAprobada" if aprobar else "DecisionRechazada", a, pid, razon,
                    decision=dec["id"], tipo_decision=dec["tipo"], solicitante=dec["solicitante"])

    # ------------------------------------------------------------------ Contabilidad
    def turno_gerente_contabilidad(self, ev):
        a, pid, t, d = "gerente-contabilidad", ev["pedido"], ev["tipo"], ev["datos"]
        p = self.e.pedido(pid)
        if t == "PedidoValidado":
            self.asignar(a, "LiquidarPedido", pid, "Registrar el pago y emitir la factura.")
        elif t == "TareaCompletada":
            self.estado(pid, a, "Terminó", d["descripcion"])
        elif t == "TareaFallida":
            if d.get("codigo") == "PAYMENT_REJECTED":
                self.cancelar(a, pid, d["descripcion"].lower())
            elif d.get("codigo") == "REFUND_NEEDS_APPROVAL":
                self.escalar_reembolso(a, pid, p.pago_recibido)
        elif t == "PedidoCancelado":
            reembolso = d.get("reembolso") or 0
            if not reembolso:
                self.estado(pid, a, "Terminó", "Pedido cancelado sin cobro: no hay reembolso")
            elif reembolso <= LIMITE_REEMBOLSO_SIN_CEO:
                self.asignar(a, "Reembolsar", pid, f"Devolver {cop(reembolso)} al cliente.")
            else:
                self.escalar_reembolso(a, pid, reembolso)
        elif t == "DecisionAprobada" and d["tipo_decision"] == "REEMBOLSO":
            self.asignar(a, "Reembolsar", pid, f"El CEO aprobó devolver {cop(p.pago_recibido)}.")
        elif t == "DecisionRechazada" and d["tipo_decision"] == "REEMBOLSO":
            self.estado(pid, a, "Terminó", "El CEO no aprobó el reembolso")

    def escalar_reembolso(self, a, pid, valor):
        dec = self.e.pedir_decision(pid, "REEMBOLSO", valor, f"Reembolso de {cop(valor)}, mayor a {cop(LIMITE_REEMBOLSO_SIN_CEO)}", a)
        self.herramienta(a, "solicitar_aprobacion_ceo", f"Reembolso de {cop(valor)} ({dec['id']})", pid)
        self.estado(pid, a, "Escaló al CEO", f"Reembolso de {cop(valor)} supera su autoridad")
        self.emitir("DecisionSolicitada", a, pid,
                    f"La Gerente de Contabilidad solo reembolsa hasta {cop(LIMITE_REEMBOLSO_SIN_CEO)}. Escala al CEO un reembolso de {cop(valor)}.",
                    decision=dec["id"], tipo_decision="REEMBOLSO", solicitante=a)

    def turno_contador(self, ev):
        a, pid, d = "contador", ev["pedido"], ev["datos"]
        self.estado(pid, a, "Trabajando", d["tipo_tarea"])
        if d["tipo_tarea"] == "LiquidarPedido":
            try:
                p = self.e.registrar_pago(pid)
            except ErrorNegocio as err:
                self.herramienta(a, "registrar_pago", err.mensaje, pid, False)
                self.terminar(a, d["tarea"], False, err.mensaje, err.codigo)
                return
            self.herramienta(a, "registrar_pago", f"Pago de {cop(p.pago_recibido)} recibido", pid)
            self.emitir("PagoRecibido", a, pid, f"Pago de {cop(p.pago_recibido)} recibido.")
            fac = self.e.crear_factura(pid)
            self.herramienta(a, "crear_factura", f"{fac['id']} por {cop(fac['total'])}", pid)
            self.terminar(a, d["tarea"], True, f"Pago recibido y factura {fac['id']} emitida por {cop(fac['total'])}.")
        elif d["tipo_tarea"] == "Reembolsar":
            try:
                r = self.e.reembolsar(pid)
            except ErrorNegocio as err:
                self.herramienta(a, "reembolsar_pago", err.mensaje, pid, False)
                self.terminar(a, d["tarea"], False, err.mensaje, "REFUND_NEEDS_APPROVAL")
                return
            self.herramienta(a, "reembolsar_pago", f"{cop(r['valor'])} devueltos al cliente", pid)
            self.emitir("ReembolsoRealizado", a, pid, f"Se devolvieron {cop(r['valor'])} al cliente.")
            self.terminar(a, d["tarea"], True, f"Reembolso de {cop(r['valor'])} realizado.")

    # ------------------------------------------------------------------ Operaciones
    def turno_gerente_operaciones(self, ev):
        a, pid, t, d = "gerente-operaciones", ev["pedido"], ev["tipo"], ev["datos"]
        p = self.e.pedido(pid)
        if p.estado == "CANCELADO":
            return
        if t == "PedidoValidado":
            self.asignar(a, "ReservarInventario", pid, "Separar las unidades del pedido en bodega.")
        elif t == "TareaFallida" and d.get("codigo") == "INVENTORY_UNAVAILABLE":
            self.cancelar(a, pid, f"sin stock suficiente ({d['descripcion']})")
        elif t == "TareaCompletada" and d["tipo_tarea"] == "Despachar":
            self.estado(pid, a, "Terminó", d["descripcion"])
        elif t in ("PagoRecibido", "TareaCompletada"):
            self.herramienta(a, "consultar_estado", f"Reserva: {p.reserva_estado.lower()}, pago: {p.pago_estado.lower()}", pid)
            despacho_pendiente = any(x["pedido"] == pid and x["tipo"] == "Despachar" for x in self.e.tareas.values())
            if p.reserva_estado == "RESERVADO" and p.pago_estado == "RECIBIDO" and not despacho_pendiente:
                self.asignar(a, "Despachar", pid, "Hay reserva y pago: crear el envío.")
            elif not despacho_pendiente:
                self.estado(pid, a, "En espera", "Falta la reserva o el pago para despachar")

    def turno_logistica(self, ev):
        a, pid, d = "logistica", ev["pedido"], ev["datos"]
        self.estado(pid, a, "Trabajando", d["tipo_tarea"])
        try:
            if d["tipo_tarea"] == "ReservarInventario":
                self.e.reservar_inventario(pid)
                self.herramienta(a, "reservar_inventario", "Unidades separadas en bodega", pid)
                self.terminar(a, d["tarea"], True, "Stock reservado.")
            else:
                envio = self.e.crear_envio(pid)
                self.herramienta(a, "crear_envio", f"{envio['id']}, guía {envio['guia']}", pid)
                self.emitir("PedidoDespachado", a, pid, f"Pedido despachado con la guía {envio['guia']}.")
                self.terminar(a, d["tarea"], True, f"Envío {envio['id']} creado con la guía {envio['guia']}.")
        except ErrorNegocio as err:
            herramienta = "reservar_inventario" if d["tipo_tarea"] == "ReservarInventario" else "crear_envio"
            self.herramienta(a, herramienta, err.mensaje, pid, False)
            self.terminar(a, d["tarea"], False, err.mensaje, err.codigo)
