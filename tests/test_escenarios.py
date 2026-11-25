"""Pruebas de los escenarios de negocio: cada una recorre el flujo completo de los siete agentes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentes import Orquestador  # noqa: E402
from empresa import Empresa  # noqa: E402


def comprar(cliente, carrito, descuento=0, pago=None, repetir=False):
    e = Empresa()
    o = Orquestador(e)
    lineas = [{"producto": p, "cantidad": c} for p, c in carrito.items()]
    subtotal = e.subtotal(lineas)
    pago = round(subtotal * (1 - descuento / 100)) if pago is None else pago
    o.recibir_pedido("TN-TEST-001", cliente, lineas, descuento, pago)
    if repetir:
        o.recibir_pedido("TN-TEST-001", cliente, lineas, descuento, pago)
    return e, e.pedidos["TN-TEST-001"]


def tipos(e):
    return [ev["tipo"] for ev in e.eventos]


def test_compra_normal_se_despacha():
    e, p = comprar("CLI-NORTE", {"PORTATIL-PRO": 3})
    assert p.estado == "DESPACHADO" and p.pago_estado == "RECIBIDO" and p.factura and p.envio
    assert e.productos["PORTATIL-PRO"]["disponible"] == 7
    assert "DecisionSolicitada" not in tipos(e)


def test_descuento_mayor_al_10_lo_aprueba_la_ceo_si_hay_margen():
    e, p = comprar("CLI-NORTE", {"PORTATIL-PRO": 3}, descuento=25)
    assert "DecisionSolicitada" in tipos(e) and "DecisionAprobada" in tipos(e)
    assert p.estado == "DESPACHADO" and p.descuento_aprobado == 25


def test_ceo_rechaza_descuento_que_deja_perdida():
    e, p = comprar("CLI-CLINICA", {"CAMARA-4K": 10}, descuento=30)
    assert "DecisionRechazada" in tipos(e)
    assert p.estado == "CANCELADO" and p.pago_estado == "PENDIENTE"


def test_sin_stock_cancela_y_reembolsa():
    e, p = comprar("CLI-CAFE", {"DOCK-USBC": 3})
    assert p.estado == "CANCELADO" and p.reembolso["valor"] == p.total
    assert e.productos["DOCK-USBC"]["disponible"] == 2
    assert "DecisionSolicitada" not in tipos(e)


def test_reembolso_grande_necesita_a_la_ceo():
    e, p = comprar("CLI-HOTEL", {"DOCK-USBC": 3, "PORTATIL-PRO": 2})
    assert p.estado == "CANCELADO" and p.pago_estado == "REEMBOLSADO"
    assert any(d["tipo"] == "REEMBOLSO" and d["estado"] == "APROBADA" for d in e.decisiones.values())


def test_cliente_bloqueado_no_compra():
    e, p = comprar("CLI-FRONTERA", {"TECLADO-MX": 2})
    assert p.estado == "CANCELADO" and "bloqueado" in p.motivo_cancelacion


def test_cupo_excedido_no_compra():
    e, p = comprar("CLI-CAFE", {"PORTATIL-PRO": 3})
    assert p.estado == "CANCELADO" and "cupo" in p.motivo_cancelacion


def test_pago_incorrecto_cancela_y_libera_stock():
    e, p = comprar("CLI-NORTE", {"MONITOR-27": 2}, pago=100)
    assert p.estado == "CANCELADO" and p.pago_estado == "RECHAZADO"
    assert e.productos["MONITOR-27"]["disponible"] == 25 and p.envio is None


def test_pedido_duplicado_es_idempotente():
    e, p = comprar("CLI-COLEGIO", {"MONITOR-27": 2}, descuento=5, repetir=True)
    assert len(e.pedidos) == 1 and "PedidoDuplicado" in tipos(e)
    assert e.productos["MONITOR-27"]["disponible"] == 23
    assert tipos(e).count("PagoRecibido") == 1


def test_nada_se_despacha_sin_pago():
    from empresa import ErrorNegocio
    e = Empresa()
    e.crear_pedido("X", "CLI-NORTE", [{"producto": "TECLADO-MX", "cantidad": 1}], 0, 360000)
    e.validar_pedido("X", 0)
    try:
        e.crear_envio("X")
        assert False, "no debió despachar"
    except ErrorNegocio as err:
        assert err.codigo == "PAYMENT_PENDING"
