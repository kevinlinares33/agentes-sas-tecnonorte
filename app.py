"""
TecnoNorte S.A.S.: una tienda de tecnología operada por siete agentes de IA.

Versión simplificada, en Streamlit, del proyecto agentes-sas.
Ejecutar:  streamlit run app.py
"""

import json

import pandas as pd
import streamlit as st

import asistente
from agentes import AGENTES, DEPARTAMENTOS, NOMBRE_EVENTO, Orquestador
from empresa import LIMITE_DESCUENTO_GERENTE, PRODUCTOS, Empresa, cop

st.set_page_config(page_title="TecnoNorte S.A.S. | Agentes de IA", page_icon="🤖", layout="wide")

# ---------------------------------------------------------------------------
# Estado de la sesión
# ---------------------------------------------------------------------------
def reiniciar():
    st.session_state.empresa = Empresa()
    st.session_state.chat = [{"role": "assistant", "content": asistente.ayuda(saludo=True), "fuente": "agente"}]
    st.session_state.consecutivo = 0
    st.session_state.pedido_activo = None
    for pid in PRODUCTOS:
        st.session_state[f"cant_{pid}"] = 0
    st.session_state.cliente = "CLI-NORTE"
    st.session_state.descuento = 0
    st.session_state.duplicar = False


if "empresa" not in st.session_state:
    reiniciar()

E: Empresa = st.session_state.empresa


def clave_ia():
    try:
        return st.secrets.get("GEMINI_API_KEY") or None
    except Exception:
        return None


API_KEY = clave_ia()

ESCENARIOS = {
    "normal": ("01", "Todo en orden", "Una compra sin excepciones", "CLI-NORTE", {"PORTATIL-PRO": 3}, 0, False),
    "descuento": ("02", "¿Un 25 % de descuento?", "Una decisión para la CEO", "CLI-NORTE", {"PORTATIL-PRO": 3}, 25, False),
    "margen": ("03", "Descuento que deja pérdida", "La CEO protege el margen", "CLI-CLINICA", {"CAMARA-4K": 10}, 30, False),
    "stock": ("04", "Más demanda que stock", "Operaciones detecta el faltante", "CLI-CAFE", {"DOCK-USBC": 3}, 0, False),
    "reembolso": ("05", "Reembolso grande", "Sin stock y la CEO aprueba devolver", "CLI-HOTEL", {"DOCK-USBC": 3, "PORTATIL-PRO": 2}, 0, False),
    "bloqueado": ("06", "Cliente bloqueado", "Comercial frena la venta", "CLI-FRONTERA", {"TECLADO-MX": 2}, 0, False),
    "duplicado": ("07", "El mismo pedido, dos veces", "Prueba la idempotencia", "CLI-COLEGIO", {"MONITOR-27": 2}, 5, True),
}


def cargar_escenario(clave):
    _, _, _, cliente, carrito, desc, dup = ESCENARIOS[clave]
    for pid in PRODUCTOS:
        st.session_state[f"cant_{pid}"] = carrito.get(pid, 0)
    st.session_state.cliente = cliente
    st.session_state.descuento = desc
    st.session_state.duplicar = dup


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------
st.markdown("""
<style>
.block-container {padding-top: 1.6rem;}
.hero {background: linear-gradient(120deg, #1d1a33 0%, #2f2a5a 55%, #4b3f8f 100%); color: #fff; padding: 28px 32px;
       border-radius: 18px; margin-bottom: 18px;}
.hero h1 {color: #fff; font-size: 2.3rem; margin: 4px 0 6px 0; line-height: 1.15;}
.hero h1 em {color: #ffcf5c; font-style: normal;}
.hero p {color: #d9d5f2; margin: 0; font-size: 1.05rem;}
.eyebrow {font-size: .72rem; letter-spacing: .14em; font-weight: 700; color: #8f86c9; text-transform: uppercase;}
.hero .eyebrow {color: #ffcf5c;}
.tag {display: inline-block; background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.25); border-radius: 999px;
      padding: 4px 12px; margin: 10px 8px 0 0; font-size: .85rem; color: #fff;}
.card {border: 1px solid #e6e3f3; border-radius: 14px; padding: 14px 16px; background: #fff; height: 100%;}
.card h4 {margin: 2px 0 4px 0;}
.muted {color: #6f6a86; font-size: .88rem;}
.price {font-size: 1.15rem; font-weight: 700; color: #2f2a5a;}
.agent {border: 1px solid #e6e3f3; border-left: 5px solid #b9b3dc; border-radius: 12px; padding: 10px 12px; margin-bottom: 10px; background: #fff;}
.agent.activo {border-left-color: #3b82f6;} .agent.ok {border-left-color: #16a34a;} .agent.escalo {border-left-color: #f59e0b;}
.agent.error {border-left-color: #dc2626;}
.agent b {font-size: .98rem;} .agent .estado {float: right; font-size: .75rem; font-weight: 700; color: #2f2a5a;}
.evento {border-left: 3px solid #c9c4e8; padding: 4px 0 10px 14px; margin-left: 6px;}
.evento.decision {border-left-color: #f59e0b;} .evento.error {border-left-color: #dc2626;} .evento.final {border-left-color: #16a34a;}
.evento small {color: #8a85a3;}
.hito {text-align: center; padding: 10px 4px; border-radius: 12px; background: #f3f1fb; color: #8a85a3; font-weight: 600; font-size: .85rem;}
.hito.hecho {background: #e7f7ec; color: #15803d;} .hito.cancelado {background: #fdecec; color: #b91c1c;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🤖 TecnoNorte S.A.S.")
    st.caption("Una tienda de tecnología de Cúcuta operada por siete agentes de IA.")
    if API_KEY:
        st.success("Modelo de IA conectado: Google Gemini responde las preguntas abiertas del chat.")
    else:
        st.info("Agentes en modo determinista: cada decisión sigue las reglas de negocio de la empresa.")
    st.markdown("**Reglas que ningún agente puede saltarse**")
    st.markdown(f"- Descuentos mayores al {LIMITE_DESCUENTO_GERENTE:g} % los decide la CEO.\n"
                "- Reembolsos mayores a $ 5.000.000 los aprueba la CEO.\n"
                "- Nada se despacha sin pago.\n- Un pedido repetido no se duplica.")
    st.divider()
    if st.button("🔄 Reiniciar la empresa", use_container_width=True):
        reiniciar()
        st.rerun()
    st.caption("Proyecto académico de **Kevin Andrés Castañeda Linares**. Base de Datos, Ingeniería de Software, FESC. "
               "Basado en el proyecto agentes-sas.")

tab_tienda, tab_pedido, tab_chat, tab_analisis, tab_como = st.tabs(
    ["🛒 La tienda", f"🔍 Detrás del pedido ({len(E.pedidos)})", "💬 Habla con la empresa", "📊 Análisis", "🧭 Cómo funciona"])

# ---------------------------------------------------------------------------
# La tienda
# ---------------------------------------------------------------------------
with tab_tienda:
    st.markdown("""
    <div class="hero">
      <div class="eyebrow">Una tienda simulada · Agentes en acción</div>
      <h1>Tú eliges.<br>Los agentes <em>se encargan.</em></h1>
      <p>Compra tecnología y mira cómo siete agentes de IA coordinan ventas, inventario y contabilidad. Cada decisión deja una huella.</p>
      <span class="tag">✓ Comercial valida</span><span class="tag">↗ La CEO decide</span>
      <span class="tag">▤ Contabilidad cobra</span><span class="tag">→ Operaciones despacha</span>
    </div>""", unsafe_allow_html=True)

    st.markdown('<div class="eyebrow">Preparado para la demostración</div>', unsafe_allow_html=True)
    st.markdown("#### Una historia para cada escenario")
    cols = st.columns(4)
    for i, (clave, (num, titulo, sub, *_)) in enumerate(ESCENARIOS.items()):
        with cols[i % 4]:
            st.button(f"{num} · {titulo}", key=f"esc_{clave}", help=sub, on_click=cargar_escenario, args=(clave,),
                      use_container_width=True)

    izq, der = st.columns([2.2, 1], gap="large")
    with izq:
        st.markdown('<div class="eyebrow">Tecnología para tu equipo</div>', unsafe_allow_html=True)
        st.markdown("#### El catálogo")
        grid = st.columns(3)
        for i, (pid, prod) in enumerate(E.productos.items()):
            with grid[i % 3]:
                with st.container(border=True):
                    st.markdown(f"<div style='font-size:2rem'>{prod['icono']}</div><h4>{prod['nombre']}</h4>"
                                f"<div class='price'>{cop(prod['precio'])}</div>"
                                f"<div class='muted'>{prod['disponible']} disponibles · {pid}</div>", unsafe_allow_html=True)
                    st.number_input("Cantidad", min_value=0, max_value=50, step=1, key=f"cant_{pid}")

    with der:
        with st.container(border=True):
            st.markdown("#### 🧺 Tu carrito")
            lineas = [{"producto": pid, "cantidad": int(st.session_state[f"cant_{pid}"])}
                      for pid in E.productos if st.session_state[f"cant_{pid}"] > 0]
            for l in lineas:
                p = E.productos[l["producto"]]
                st.markdown(f"{l['cantidad']} × {p['nombre']} <span style='float:right'>{cop(p['precio'] * l['cantidad'])}</span>",
                            unsafe_allow_html=True)
            if not lineas:
                st.caption("Agrega productos o elige un escenario.")
            st.selectbox("Compras a nombre de", list(E.clientes), key="cliente",
                         format_func=lambda c: f"{E.clientes[c]['nombre']} ({E.clientes[c]['estado'].lower()})")
            st.number_input("Descuento solicitado (%)", min_value=0, max_value=100, step=5, key="descuento")
            st.caption(f"El Gerente Comercial puede autorizar hasta el {LIMITE_DESCUENTO_GERENTE:g} %. Más que eso lo decide la CEO.")
            subtotal = E.subtotal(lineas) if lineas else 0
            pago = round(subtotal * (1 - st.session_state.descuento / 100))
            st.markdown(f"Subtotal <span style='float:right'>{cop(subtotal)}</span><br>"
                        f"Descuento <span style='float:right'>− {cop(subtotal - pago)}</span><br>"
                        f"<b>Pago simulado</b> <span style='float:right'><b>{cop(pago)}</b></span>", unsafe_allow_html=True)
            st.checkbox("Enviar dos veces el mismo pedido", key="duplicar")
            if st.button("Confirmar compra →", type="primary", use_container_width=True, disabled=not lineas):
                st.session_state.consecutivo += 1
                pid = f"TN-2026-{st.session_state.consecutivo:03d}"
                orq = Orquestador(E)
                orq.recibir_pedido(pid, st.session_state.cliente, lineas, float(st.session_state.descuento), pago)
                if st.session_state.duplicar:
                    orq.recibir_pedido(pid, st.session_state.cliente, lineas, float(st.session_state.descuento), pago)
                st.session_state.pedido_activo = pid
                st.rerun()
            st.caption("Precios en pesos colombianos. El pago simulado corresponde al descuento solicitado.")

    if st.session_state.pedido_activo:
        p = E.pedidos[st.session_state.pedido_activo]
        icono = {"DESPACHADO": "✅", "CANCELADO": "❌"}.get(p.estado, "⏳")
        st.success(f"{icono} Pedido **{p.id}**: {asistente.ESTADOS.get(p.estado, p.estado)}. "
                   "Abre la pestaña **🔍 Detrás del pedido** para ver qué hizo cada agente.")

# ---------------------------------------------------------------------------
# Detrás del pedido
# ---------------------------------------------------------------------------
def tarjeta_agente(aid, estados):
    a = AGENTES[aid]
    est = estados.get(aid, {"estado": "En espera", "nota": "Sin trabajo en este pedido"})
    clase = {"Trabajando": "activo", "Delegó": "activo", "Decidiendo": "activo", "Terminó": "ok", "Aprobó": "ok",
             "Escaló al CEO": "escalo", "Rechazó": "error", "Reportó un problema": "error", "Canceló el pedido": "error"}.get(est["estado"], "")
    st.markdown(f"<div class='agent {clase}'><span class='estado'>{est['estado']}</span><b>{a['icono']} {a['nombre']}</b><br>"
                f"<span class='muted'>{a['cargo']}</span><br><small>{est['nota']}</small></div>", unsafe_allow_html=True)


with tab_pedido:
    st.markdown('<div class="eyebrow">La empresa en acción</div>', unsafe_allow_html=True)
    st.markdown("## Detrás de tu pedido")
    if not E.pedidos:
        st.info("Aún no hay pedidos. Confirma una compra en **🛒 La tienda**.")
    else:
        ids = list(E.pedidos)
        activo = st.session_state.pedido_activo if st.session_state.pedido_activo in ids else ids[-1]
        pid = st.selectbox("Pedido", ids[::-1], index=ids[::-1].index(activo))
        p = E.pedidos[pid]
        cliente = E.clientes[p.cliente_id]["nombre"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Estado", p.estado.capitalize())
        c2.metric("Cliente", cliente)
        c3.metric("Total", cop(p.total or p.subtotal))
        c4.metric("Guía de envío", p.envio["guia"] if p.envio else "—")

        hitos = [("Recibido", True), ("Validado", p.estado in ("VALIDADO", "DESPACHADO") or p.total > 0),
                 ("Pagado", p.pago_estado in ("RECIBIDO", "REEMBOLSADO")), ("Reservado", p.reserva_estado in ("RESERVADO", "LIBERADO")),
                 ("Despachado", p.estado == "DESPACHADO")]
        if p.estado == "CANCELADO":
            hitos.append(("Cancelado", True))
        if p.reembolso:
            hitos.append(("Reembolsado", True))
        for col, (nombre, hecho) in zip(st.columns(len(hitos)), hitos):
            clase = "cancelado" if nombre in ("Cancelado",) else ("hecho" if hecho else "")
            col.markdown(f"<div class='hito {clase}'>{'✔ ' if hecho else ''}{nombre}</div>", unsafe_allow_html=True)
        if p.motivo_cancelacion:
            st.error(f"Motivo de la cancelación: {p.motivo_cancelacion}")

        st.markdown("#### 👥 El equipo de este pedido")
        estados = E.estados.get(pid, {})
        st.markdown('<div class="eyebrow">Dirección</div>', unsafe_allow_html=True)
        ceo_col, _ = st.columns([1, 2])
        with ceo_col:
            tarjeta_agente("ceo", estados)
        for col, dep in zip(st.columns(3), DEPARTAMENTOS):
            with col:
                st.markdown(f'<div class="eyebrow">{dep}</div>', unsafe_allow_html=True)
                for aid, a in AGENTES.items():
                    if a["departamento"] == dep:
                        tarjeta_agente(aid, estados)

        izq, der = st.columns([1.3, 1], gap="large")
        with izq:
            st.markdown("#### 📜 La historia del pedido")
            for ev in [x for x in E.eventos if x["pedido"] == pid]:
                quien = AGENTES[ev["origen"]]["cargo"] if ev["origen"] in AGENTES else "Tienda"
                clase = ("decision" if ev["tipo"].startswith("Decision") else
                         "error" if ev["tipo"] in ("TareaFallida", "PedidoCancelado", "DecisionRechazada") else
                         "final" if ev["tipo"] in ("PedidoDespachado", "ReembolsoRealizado") else "")
                st.markdown(f"<div class='evento {clase}'><small>{ev['hora']} · {quien}</small><br>"
                            f"<b>{NOMBRE_EVENTO.get(ev['tipo'], ev['tipo'])}</b><br>{ev['datos']['descripcion']}</div>",
                            unsafe_allow_html=True)
        with der:
            st.markdown("#### 🛠️ Lo que hacen los agentes")
            act = [x for x in E.actividad if x["pedido"] == pid]
            st.dataframe(pd.DataFrame([{"Hora": x["hora"], "Agente": AGENTES[x["agente"]]["cargo"], "Herramienta": x["herramienta"],
                                        "Resultado": ("✔ " if x["ok"] else "✖ ") + x["detalle"]} for x in act]),
                         hide_index=True, use_container_width=True, height=420)
            with st.expander("🗄️ Lo que queda registrado"):
                st.json({"pedido": p.__dict__,
                         "tareas": [t for t in E.tareas.values() if t["pedido"] == pid],
                         "decisiones": [d for d in E.decisiones.values() if d["pedido"] == pid]})
            traza = {"pedido": p.__dict__, "eventos": [x for x in E.eventos if x["pedido"] == pid], "actividad": act}
            st.download_button("⬇️ Descargar la traza del pedido (JSON)", json.dumps(traza, ensure_ascii=False, indent=2, default=str),
                               file_name=f"traza_{pid}.json", use_container_width=True)

# ---------------------------------------------------------------------------
# Habla con la empresa
# ---------------------------------------------------------------------------
with tab_chat:
    st.markdown('<div class="eyebrow">Agente de atención</div>', unsafe_allow_html=True)
    st.markdown("## 💬 Habla con la empresa")
    st.caption("Pregunta por tus pedidos, el inventario, las políticas o el equipo. El agente consulta los datos reales de la empresa.")
    sugerencias = ["¿Cómo va mi pedido?", "¿Cuántos portátiles quedan?", "¿Quién aprueba un descuento del 25 %?",
                   "¿Qué hace cada agente?", "Resumen de ventas"]
    pendiente = None
    for col, s in zip(st.columns(len(sugerencias)), sugerencias):
        if col.button(s, use_container_width=True):
            pendiente = s
    for m in st.session_state.chat:
        with st.chat_message(m["role"], avatar="🧑" if m["role"] == "user" else "🤖"):
            st.markdown(m["content"])
            if m.get("fuente") == "ia":
                st.caption("Respuesta generada por el modelo de IA Gemini con los datos de la empresa")
    pregunta = st.chat_input("Escribe tu pregunta…") or pendiente
    if pregunta:
        historial = list(st.session_state.chat)
        st.session_state.chat.append({"role": "user", "content": pregunta})
        respuesta, fuente = asistente.responder(pregunta, E, historial, API_KEY)
        st.session_state.chat.append({"role": "assistant", "content": respuesta, "fuente": fuente})
        st.rerun()

# ---------------------------------------------------------------------------
# Análisis
# ---------------------------------------------------------------------------
with tab_analisis:
    st.markdown('<div class="eyebrow">Inteligencia de negocio</div>', unsafe_allow_html=True)
    st.markdown("## 📊 Análisis de la operación")
    r = asistente.resumen_empresa(E)
    k = st.columns(5)
    k[0].metric("Pedidos", r["pedidos"])
    k[1].metric("Despachados", r["despachados"])
    k[2].metric("Cancelados", r["cancelados"])
    k[3].metric("Ventas despachadas", cop(r["ventas"]))
    k[4].metric("Reembolsos", cop(r["reembolsos"]))

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Inventario: disponible vs. inicial**")
        st.bar_chart(pd.DataFrame({"Inicial": {v["nombre"]: PRODUCTOS[k_]["disponible"] for k_, v in E.productos.items()},
                                   "Disponible": {v["nombre"]: v["disponible"] for v in 
    with g2:
        st.markdown("**Unidades vendidas por producto**")
        vendidas = {v["nombre"]: 0 for v in E.productos.values()}
        for p in E.pedidos.values():
            if p.estado == "DESPACHADO":
                for l in p.lineas:
                    vendidas[E.productos[l["producto"]]["nombre"]] += l["cantidad"]
        st.bar_chart(pd.Series(vendidas, name="Unidades"))

    if E.pedidos:
        tabla = pd.DataFrame([{"Pedido": p.id, "Cliente": E.clientes[p.cliente_id]["nombre"], "Estado": p.estado,
                               "Descuento %": p.descuento_solicitado, "Subtotal": p.subtotal, "Total": p.total,
                               "Pago": p.pago_estado, "Motivo": p.motivo_cancelacion or ""} for p in E.pedidos.values()])
        g3, g4 = st.columns(2)
        with g3:
            st.markdown("**Pedidos por estado**")
            st.bar_chart(tabla["Estado"].value_counts())
        with g4:
            st.markdown("**Decisiones de la CEO**")
            if E.decisiones:
                st.dataframe(pd.DataFrame([{"Pedido": d["pedido"], "Tipo": d["tipo"], "Estado": d["estado"], "Razón": d["razon"]}
                                           for d in E.decisiones.values()]), hide_index=True, use_container_width=True)
            else:
                st.caption("La CEO aún no ha tenido que decidir nada.")
        st.markdown("**Detalle de pedidos**")
        st.dataframe(tabla, hide_index=True, use_container_width=True)
        st.download_button("⬇️ Descargar reporte de pedidos (CSV)", tabla.to_csv(index=False).encode("utf-8-sig"),
                           file_name="reporte_pedidos_tecnonorte.csv")
    else:
        st.info("Cuando haya pedidos verás aquí su análisis.")

# ---------------------------------------------------------------------------
# Cómo funciona
# ---------------------------------------------------------------------------
with tab_como:
    st.markdown('<div class="eyebrow">Arquitectura</div>', unsafe_allow_html=True)
    st.markdown("## 🧭 Cómo funciona")
    st.markdown("> Las instrucciones describen lo que un agente **debería** hacer. La API de la empresa define lo que **puede** hacer. "
                "Los agentes razonan; la plataforma garantiza la confiabilidad.")
    st.graphviz_chart("""
    digraph {
      rankdir=LR; node [shape=box style="rounded,filled" fillcolor="#f3f1fb" color="#8f86c9" fontname="Helvetica"];
      tienda [label="Tienda\\n(interfaz Streamlit)"]; api [label="API de la empresa\\nreglas de negocio" fillcolor="#fff4d6"];
      bus [label="Bus de eventos\\nun evento = un turno"]; datos [label="Estado durable\\npedidos, tareas, decisiones" fillcolor="#e7f7ec"];
      ceo [label="CEO"]; com [label="Comercial\\ngerente + asesora"]; ope [label="Operaciones\\ngerente + logística"];
      con [label="Contabilidad\\ngerente + contador"]; chat [label="Agente de atención\\n(chat + IA opcional)"];
      tienda -> api -> datos; api -> bus; bus -> com; bus -> ope; bus -> con; bus -> ceo;
      com -> api; ope -> api; con -> api; ceo -> api; chat -> api;
    }""")
    st.markdown("""
**Flujo de un pedido**

1. La tienda registra el pedido y publica el evento *Pedido recibido*.
2. El **Gerente Comercial** delega a la **Asesora Comercial** la validación del cliente. Si el descuento supera el 10 %, escala la decisión a la **CEO**, que revisa el margen.
3. Con el pedido validado, **Contabilidad** cobra y factura, y **Operaciones** reserva el stock.
4. Solo cuando hay **reserva y pago**, Logística despacha y genera la guía.
5. Si algo falla (cliente bloqueado, sin stock, pago incorrecto) el pedido se cancela, se libera el stock y se reembolsa lo pagado; si el reembolso supera $ 5.000.000, la CEO lo aprueba.

**Principios tomados de agentes-sas**

- Los agentes solo actúan a través de la API de la empresa y cada uno solo usa las herramientas de su cargo.
- Las reglas de negocio viven en el código, no en las instrucciones.
- Cada escritura es idempotente: un pedido repetido no se duplica ni se cobra dos veces.
- Cada evento, herramienta y decisión queda registrado para tener trazabilidad completa.
""")
    st.dataframe(pd.DataFrame([{"Agente": f"{a['icono']} {a['nombre']}", "Cargo": a["cargo"], "Departamento": a["departamento"],
                                "Reporta a": AGENTES[a["jefe"]]["cargo"] if a["jefe"] else "—", "Función": a["funcion"],
                                "Herramientas": ", ".join(a["herramientas"])} for a in AGENTES.values()]),
                 hide_index=True, use_container_width=True)
