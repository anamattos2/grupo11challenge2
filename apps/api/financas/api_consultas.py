"""Rotas somente de leitura para as telas e os agentes de IA."""
from ninja import Query, Router

from financas.api import ERROS_LEITURA, ErroValidacaoOut
from financas.api_transacoes import recusar_filtros_desconhecidos
from financas.ferramentas import (
    FerramentaOut,
    ParametrosContas,
    ParametrosPeriodo,
    ParametrosReserva,
    ParametrosTotais,
    ResultadoContasOut,
    ResultadoReservaOut,
    ResultadoResumoOut,
    ResultadoTotaisOut,
    catalogo_ferramentas,
    executar_validado,
)

consultas_router = Router(tags=["consultas financeiras"])


@consultas_router.get("/ferramentas", response={200: list[FerramentaOut], **ERROS_LEITURA})
def listar_ferramentas(request):
    """Lista as ferramentas de leitura permitidas e seus parâmetros."""
    return catalogo_ferramentas()


@consultas_router.get(
    "/totais-por-categoria",
    response={200: ResultadoTotaisOut, 422: ErroValidacaoOut, **ERROS_LEITURA},
)
def consultar_totais_por_categoria(request, parametros: Query[ParametrosTotais]):
    """Soma receitas e despesas declaradas por categoria em um período."""
    recusar_filtros_desconhecidos(request, ParametrosTotais)
    return executar_validado("totais_por_categoria", request.auth, parametros)


@consultas_router.get(
    "/resumo-periodo",
    response={200: ResultadoResumoOut, 422: ErroValidacaoOut, **ERROS_LEITURA},
)
def consultar_resumo_periodo(request, parametros: Query[ParametrosPeriodo]):
    """Resume receitas, despesas e despesas essenciais declaradas em um período."""
    recusar_filtros_desconhecidos(request, ParametrosPeriodo)
    return executar_validado("resumo_periodo", request.auth, parametros)


@consultas_router.get(
    "/reserva",
    response={200: ResultadoReservaOut, 422: ErroValidacaoOut, **ERROS_LEITURA},
)
def consultar_reserva_declarada(request, parametros: Query[ParametrosReserva]):
    """Retorna meta, saldo declarado, cobertura e progresso da reserva."""
    recusar_filtros_desconhecidos(request, ParametrosReserva)
    return executar_validado("consultar_reserva", request.auth, parametros)


@consultas_router.get(
    "/saldos-contas",
    response={200: ResultadoContasOut, 422: ErroValidacaoOut, **ERROS_LEITURA},
)
def consultar_saldos_contas(request):
    """Lista os saldos declarados das contas manuais."""
    recusar_filtros_desconhecidos(request, ParametrosContas)
    return executar_validado("saldos_contas", request.auth, ParametrosContas())
