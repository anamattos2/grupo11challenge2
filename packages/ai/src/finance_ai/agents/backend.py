"""Integração da Research com as ferramentas financeiras reais (BE-06 / #88).

O backend expõe ``executar_ferramenta(usuaria, nome, parametros)`` em
``apps/api/financas/ferramentas.py``, com quatro ferramentas de leitura. Este
adaptador traduz as operações do contrato dos agentes para essas ferramentas
e o resultado delas para ``EvidenciaFinanceira``.

| Operação dos agentes | Ferramenta do backend |
|---|---|
| ``resumo_transacoes`` com ``somente_essenciais`` | ``resumo_periodo`` (campo ``despesas_essenciais``) |
| ``resumo_transacoes`` | ``totais_por_categoria`` |
| ``listar_contas`` | ``saldos_contas`` |
| ``situacao_reserva`` | ``consultar_reserva`` |

O pacote de IA não importa Django: o backend entrega duas funções.

- ``executar_ferramenta``: a função da BE-06, sem alteração;
- ``resolver_usuaria``: recebe a ``usuaria_ref`` opaca do ``ContextoAutorizado``
  e devolve o usuário da sessão, ou ``None`` se a referência não corresponder.

Uso na view de chat (S4-06)::

    fonte = FonteFinanceiraBackend(
        executar_ferramenta,
        resolver_usuaria=lambda ref: request.auth if ref == ref_da_sessao else None,
    )
    agente = ResearchAgent(retriever, fonte)
"""

from __future__ import annotations

from calendar import monthrange
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from .contratos import (
    ContextoAutorizado,
    EvidenciaFinanceira,
    LocalizacaoFinanceira,
    OperacaoFinanceira,
    OrigemFinanceira,
    ParametrosFinanceiros,
)
from .ferramentas import ErroFerramenta, id_financeiro

ROTAS = {
    "resumo_periodo": "GET /api/consultas/resumo-periodo (BE-06 / #88)",
    "totais_por_categoria": "GET /api/consultas/totais-por-categoria (BE-06 / #88)",
    "saldos_contas": "GET /api/consultas/saldos-contas (BE-06 / #88)",
    "consultar_reserva": "GET /api/consultas/reserva (BE-06 / #88)",
}

#: Códigos de exceção da BE-06 tratados como negação, e não como erro.
CODIGOS_NEGACAO = {"acesso_negado"}


def _dinheiro(valor: Any) -> str | None:
    if valor is None:
        return None
    try:
        return format(Decimal(str(valor)).quantize(Decimal("0.01")), "f")
    except InvalidOperation:
        raise ErroFerramenta("resposta_invalida") from None


def resumo_reserva(valores: dict, estado: str | None, faltando: list[str]) -> str:
    """Mesmo texto para a ferramenta real e para a fixture."""
    if estado == "calculado":
        return (f"Meta {valores['meta']} BRL; saldo declarado {valores['saldo_declarado']} BRL "
                f"({valores['progresso_percentual']}%).")
    if estado == "meta_zero":
        return f"Meta zero; saldo declarado {valores['saldo_declarado']} BRL, sem percentual."
    return f"Reserva com estado '{estado}'; falta informar: {', '.join(faltando) or 'dados'}."


def traduzir(operacao: OperacaoFinanceira, parametros: ParametrosFinanceiros,
             hoje) -> tuple[str, dict[str, Any], list[str]]:
    """Operação + parâmetros dos agentes → (ferramenta, parâmetros, observações).

    As ferramentas de período exigem datas. Sem período, usa o mês corrente da
    ``data_referencia`` e registra isso nos filtros da evidência.
    """
    avisos: list[str] = []
    operacao = OperacaoFinanceira(operacao)
    if operacao is OperacaoFinanceira.LISTAR_CONTAS:
        return "saldos_contas", {}, avisos
    if operacao is OperacaoFinanceira.SITUACAO_RESERVA:
        return "consultar_reserva", {}, avisos
    inicio, fim = parametros.periodo_inicio, parametros.periodo_fim
    if inicio is None or fim is None:
        inicio = inicio or hoje.replace(day=1)
        fim = fim or hoje.replace(day=monthrange(hoje.year, hoje.month)[1])
        avisos.append("periodo_padrao")
    periodo = {"data_inicio": inicio.isoformat(), "data_fim": fim.isoformat()}
    if parametros.somente_essenciais:
        return "resumo_periodo", periodo, avisos
    if parametros.tipo:
        periodo["tipo"] = parametros.tipo
    return "totais_por_categoria", periodo, avisos


class FonteFinanceiraBackend:
    """``FonteFinanceira`` real: chama a BE-06 com a usuária da sessão."""

    sintetico = False

    def __init__(self, executar_ferramenta: Callable[[Any, str, dict], dict],
                 resolver_usuaria: Callable[[str], Any]):
        self._executar = executar_ferramenta
        self._resolver = resolver_usuaria

    def consultar(self, contexto: ContextoAutorizado, operacao: OperacaoFinanceira,
                  parametros: ParametrosFinanceiros) -> EvidenciaFinanceira | None:
        operacao = OperacaoFinanceira(operacao)
        usuaria = self._resolver(contexto.usuaria_ref)
        if usuaria is None:
            raise ErroFerramenta("contexto_ausente")
        nome, enviados, avisos = traduzir(operacao, parametros, contexto.data_referencia)
        try:
            resultado = self._executar(usuaria, nome, enviados)
        except ErroFerramenta:
            raise
        except Exception as erro:  # exceções da BE-06 trazem ``codigo``
            codigo = getattr(erro, "codigo", None) or "ferramenta_indisponivel"
            raise ErroFerramenta("permissao_ausente" if codigo in CODIGOS_NEGACAO else codigo) from None
        if resultado.get("ferramenta") != nome or resultado.get("tipo_evidencia") != "financeira":
            raise ErroFerramenta("resposta_invalida")
        valores, registros, resumo = _converter(nome, parametros, resultado["dados"])
        periodo = resultado.get("periodo") or {}
        filtros = {"ferramenta": nome, "evidencia_backend": resultado["evidencia_id"]}
        filtros.update({k: str(v) for k, v in enviados.items() if k == "tipo"})
        if parametros.somente_essenciais:
            filtros["somente_essenciais"] = "true"
        for aviso in avisos:
            filtros[aviso] = "true"
        return EvidenciaFinanceira(
            id=id_financeiro(operacao, parametros),
            origem=OrigemFinanceira(operacao=operacao, referencia_api=ROTAS[nome], sintetica=False),
            localizacao=LocalizacaoFinanceira(
                periodo_inicio=periodo.get("inicio"), periodo_fim=periodo.get("fim"),
                filtros=filtros, registros=registros),
            valores=valores,
            resumo=resumo[:500],
        )


def _converter(nome: str, parametros: ParametrosFinanceiros, dados: dict):
    """Resultado da BE-06 → (valores, registros, resumo), no formato das fixtures."""
    if nome == "resumo_periodo":
        # Mesmo significado de ``somente_essenciais`` nas fixtures: só despesas essenciais.
        essenciais = _dinheiro(dados["despesas_essenciais"])
        valores = {"receitas": "0.00", "despesas": essenciais,
                   "resultado": _dinheiro(-Decimal(essenciais))}
        return valores, (), f"Despesas em categorias essenciais no período: {essenciais} BRL."
    if nome == "totais_por_categoria":
        valores = {"receitas": _dinheiro(dados["receitas"]), "despesas": _dinheiro(dados["despesas"]),
                   "resultado": _dinheiro(dados["resultado"])}
        resumo = (f"Transações registradas no período: {dados['quantidade']} registro(s); "
                  f"receitas {valores['receitas']}, despesas {valores['despesas']} BRL.")
        return valores, (), resumo
    if nome == "saldos_contas":
        contas = dados["contas"]
        valores = {f"conta_{c['id']}": _dinheiro(c["saldo_declarado"]) for c in contas}
        valores["saldo_total_declarado"] = _dinheiro(dados["total_declarado"])
        nomes = ", ".join(f"{c['nome']} ({_dinheiro(c['saldo_declarado'])})" for c in contas)
        resumo = f"{len(contas)} conta(s) declarada(s): {nomes}; total {valores['saldo_total_declarado']} BRL."
        return valores, tuple(str(c["id"]) for c in contas), resumo
    if nome == "consultar_reserva":
        meta, saldo = _dinheiro(dados.get("meta")), _dinheiro(dados.get("saldo_declarado"))
        falta = (_dinheiro(max(Decimal(meta) - Decimal(saldo), Decimal(0)))
                 if meta is not None and saldo is not None else None)
        valores = {"meta": meta, "saldo_declarado": saldo, "falta": falta,
                   "progresso_percentual": _dinheiro(dados.get("progresso_percentual"))}
        return valores, (), resumo_reserva(valores, dados.get("estado"), dados.get("faltando") or [])
    raise ErroFerramenta("resposta_invalida")
