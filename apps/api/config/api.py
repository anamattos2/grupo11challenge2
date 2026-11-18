"""Definição da API HTTP do backend financeiro."""
from django.db import DatabaseError, connection
from ninja import NinjaAPI, Schema

from autenticacao.api import router as autenticacao_router
from autenticacao.api import sessao
from financas.api import contas_router, perfil_router
from financas.api_consultas import consultas_router
from financas.api_reserva import reserva_router
from financas.api_transacoes import categorias_router, transacoes_router

# Toda rota exige sessão, salvo as marcadas explicitamente com auth=None.
api = NinjaAPI(title="Grupo 11 - API financeira", version="0.1.0", auth=sessao)
api.add_router("/auth", autenticacao_router)
api.add_router("/perfil", perfil_router)
api.add_router("/contas", contas_router)
api.add_router("/categorias", categorias_router)
api.add_router("/transacoes", transacoes_router)
api.add_router("/reserva", reserva_router)
api.add_router("/consultas", consultas_router)


class HealthOut(Schema):
    status: str
    database: str


@api.get(
    "/health",
    response={200: HealthOut, 503: HealthOut},
    tags=["operação"],
    auth=None,
)
def health(request):
    """Informa se a API está no ar e consegue consultar o PostgreSQL."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return 503, {"status": "indisponivel", "database": "erro"}
    return 200, {"status": "ok", "database": "ok"}
