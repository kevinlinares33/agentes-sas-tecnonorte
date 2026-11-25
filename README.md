# 🤖 TecnoNorte S.A.S. · Una tienda operada por siete agentes de IA

**Versión simplificada, en Streamlit, del proyecto [agentes-sas](https://github.com/aljoveza/agentes-sas).**

Un cliente compra tecnología en una tienda de demostración. Detrás de la compra, siete empleados de IA
(una CEO, tres gerentes de departamento y tres especialistas) validan al cliente, reservan el stock,
cobran, facturan, despachan y escalan a la CEO las decisiones que superan su autoridad.

> Las instrucciones describen lo que un agente **debería** hacer. La API de la empresa define lo que **puede** hacer.
> Los agentes razonan; la plataforma garantiza la confiabilidad.

**Autor:** Kevin Andrés Castañeda Linares · Ingeniería de Software · Base de Datos · FESC (Fundación de Estudios Superiores Comfanorte)

---

## El problema que resuelve

En una empresa pequeña, un pedido pasa por varias áreas: ventas valida al cliente, contabilidad cobra y factura,
bodega despacha y la gerencia aprueba las excepciones. Cuando ese proceso es manual se pierden pedidos, se despacha
sin cobrar, se aprueban descuentos que dejan pérdida y nadie sabe en qué va cada compra.

Este sistema muestra cómo un equipo de agentes de IA puede atender ese proceso de principio a fin, respetando reglas
de negocio que ningún agente puede saltarse y dejando trazabilidad completa de cada decisión.

## Función de los agentes

| Agente | Cargo | Qué hace |
|---|---|---|
| 👩‍💼 Valentina Rojas | CEO | Decide descuentos mayores al 10 % (revisa el margen) y reembolsos mayores a $ 5.000.000 |
| 🧑‍💼 Andrés Pérez | Gerente Comercial | Recibe el pedido, delega la validación y autoriza descuentos hasta el 10 % |
| 🧑‍💻 Laura Gómez | Asesora Comercial | Verifica que el cliente esté activo y que el pedido quepa en su cupo |
| 👨‍🔧 Camilo Duarte | Gerente de Operaciones | Ordena reservar el stock y despachar solo con reserva y pago |
| 📦 Sergio Ortega | Coordinador de Logística | Reserva el inventario y crea el envío con su guía |
| 👩‍💼 Natalia Suárez | Gerente de Contabilidad | Ordena cobrar y facturar; gestiona los reembolsos |
| 🧾 Julián Castro | Contador | Registra el pago, emite la factura y hace los reembolsos |

Además, un **agente de atención** responde en el chat las preguntas del usuario (estado de un pedido, inventario,
precios, políticas, equipo y ventas) consultando los datos reales de la empresa. Si se configura una clave de
**Google Gemini**, las preguntas abiertas las responde ese modelo de IA con el estado de la empresa como contexto.

## Cómo funciona

```
 Tienda (Streamlit) ──crear pedido──► API de la empresa ──escribe──► estado durable
                                         │ publica eventos de negocio      (pedidos, tareas, decisiones)
                                         ▼
                                  Bus de eventos ──según el organigrama──► agente correspondiente
                                                                           │ un evento = un turno
                        CEO · Comercial · Operaciones · Contabilidad ◄─────┘
                                         │ solo usan las herramientas de su cargo
                                         ▼
                                  API de la empresa (reglas de negocio)
```

**Principios del proyecto original que se conservan**

- **Los agentes solo actúan a través de la API de la empresa** (`empresa.py`). Cada agente tiene una lista de herramientas permitidas según su cargo.
- **Las reglas de negocio viven en el código, no en las instrucciones.** Descuentos mayores al 10 % y reembolsos mayores a $ 5.000.000 necesitan una decisión aprobada por la CEO; nada se despacha sin pago; un pedido cancelado no recibe más trabajo y uno despachado no se cancela.
- **Cada escritura es idempotente.** Enviar dos veces el mismo pedido no lo duplica ni lo cobra dos veces.
- **Los casos borde son procedimientos:** sin stock, el pedido se cancela, se libera el inventario, se anula la factura y se reembolsa (con aprobación de la CEO si supera el límite).
- **Observabilidad:** cada evento, herramienta usada y decisión queda registrado y se ve en vivo en *Detrás del pedido*.

## Funcionalidades de la aplicación

| Pestaña | Contenido |
|---|---|
| 🛒 La tienda | Catálogo, carrito, cliente, descuento solicitado y 7 escenarios de demostración |
| 🔍 Detrás del pedido | Hitos del pedido, estado de cada agente, historia de eventos, herramientas usadas, registros y descarga de la traza |
| 💬 Habla con la empresa | Chat con el agente de atención (reglas o Google Gemini) |
| 📊 Análisis | Indicadores, inventario, unidades vendidas, pedidos por estado, decisiones de la CEO y reporte CSV |
| 🧭 Cómo funciona | Arquitectura, flujo de un pedido, principios y organigrama con herramientas |

### Escenarios de demostración

| # | Escenario | Qué se observa |
|---|---|---|
| 01 | Todo en orden | El pedido se valida, se cobra, se reserva y se despacha |
| 02 | ¿Un 25 % de descuento? | El Gerente Comercial escala a la CEO; ella aprueba porque el margen sigue positivo |
| 03 | Descuento que deja pérdida | La CEO rechaza un 30 % en cámaras web y el pedido se cancela sin cobro |
| 04 | Más demanda que stock | Logística detecta el faltante, Operaciones cancela y Contabilidad reembolsa |
| 05 | Reembolso grande | Sin stock con un pago mayor a $ 5.000.000: la CEO aprueba el reembolso |
| 06 | Cliente bloqueado | La Asesora Comercial frena la venta |
| 07 | El mismo pedido, dos veces | La API ignora el duplicado (idempotencia) |

## Estructura del repositorio

```
app.py                 Interfaz web en Streamlit (tienda, trazabilidad, chat, análisis, arquitectura)
empresa.py             API de la empresa: catálogo, clientes, pedidos y reglas de negocio
agentes.py             Organigrama de los siete agentes y bus de eventos que los coordina
asistente.py           Agente de atención del chat, con Google Gemini opcional
tests/                 Pruebas de los escenarios de negocio (pytest)
.streamlit/config.toml Tema visual
requirements.txt       Dependencias
```

## Ejecutar en el computador

```bash
pip install -r requirements.txt
streamlit run app.py
```

Pruebas:

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Despliegue en Streamlit Community Cloud

1. Entrar a <https://share.streamlit.io> con la cuenta de GitHub.
2. **Create app** → elegir este repositorio, la rama `main` y el archivo `app.py`.
3. Opcional, para activar el modelo de IA en el chat: **Advanced settings → Secrets** y escribir
   `GEMINI_API_KEY = "su_clave"` (se crea gratis en <https://aistudio.google.com/apikey>).
4. **Deploy**. La aplicación queda publicada en una dirección del tipo `nombre-proyecto.streamlit.app`.

## Diferencias con agentes-sas

| agentes-sas | Esta versión |
|---|---|
| Agentes Hermes sobre Amazon Bedrock, uno por contenedor | Agentes en Python que siguen los mismos procedimientos de sus descripciones de cargo |
| EventBridge y una cola SQS por empleado | Bus de eventos en memoria con el mismo enrutamiento por organigrama |
| DynamoDB y S3 | Estado en la sesión de Streamlit |
| Terraform sobre AWS y LocalStack | Despliegue gratuito en Streamlit Community Cloud |
| Tienda Nexo en dólares | Tienda TecnoNorte S.A.S. de Cúcuta en pesos colombianos, con chat y panel de análisis |

## Créditos

Basado en [agentes-sas](https://github.com/aljoveza/agentes-sas), proyecto de referencia de la actividad.
