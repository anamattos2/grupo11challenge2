"""Definição da API HTTP do backend financeiro."""
from django.db import DatabaseError, connection
from ninja import NinjaAPI, Schema

from comprovantes.api import router as comprovantes_router

api = NinjaAPI(title="Grupo 11 - API financeira", version="0.1.0")
api.add_router("/comprovantes", comprovantes_router)


class HealthOut(Schema):
    status: str
    database: str


@api.get("/health", response={200: HealthOut, 503: HealthOut}, tags=["operação"])
def health(request):
    """Informa se a API está no ar e consegue consultar o PostgreSQL."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return 503, {"status": "indisponivel", "database": "erro"}
    return 200, {"status": "ok", "database": "ok"}
