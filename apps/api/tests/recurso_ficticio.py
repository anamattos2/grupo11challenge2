"""Recurso usado só nos testes para exercitar o isolamento por HTTP.

Segue o padrão esperado das rotas financeiras, que chegam nas próximas issues.
"""
from django.db import models
from django.urls import path
from ninja import NinjaAPI, Schema

from autenticacao.api import sessao
from autenticacao.isolamento import RegistroDaUsuaria, obter_da_usuaria_ou_404


class AnotacaoFicticia(RegistroDaUsuaria):
    titulo = models.CharField(max_length=80)

    class Meta:
        app_label = "tests"


class AnotacaoIn(Schema):
    titulo: str


class AnotacaoOut(Schema):
    id: int
    titulo: str
    usuaria_id: int


api = NinjaAPI(auth=sessao, urls_namespace="recurso-ficticio")


@api.get("/anotacoes", response=list[AnotacaoOut])
def listar(request):
    return AnotacaoFicticia.objects.da_usuaria(request.auth)


@api.post("/anotacoes", response={201: AnotacaoOut})
def criar(request, dados: AnotacaoIn):
    return 201, AnotacaoFicticia.objects.create(usuaria=request.auth, titulo=dados.titulo)


@api.get("/anotacoes/{anotacao_id}", response=AnotacaoOut)
def consultar(request, anotacao_id: int):
    return obter_da_usuaria_ou_404(AnotacaoFicticia, request.auth, id=anotacao_id)


@api.put("/anotacoes/{anotacao_id}", response=AnotacaoOut)
def alterar(request, anotacao_id: int, dados: AnotacaoIn):
    anotacao = obter_da_usuaria_ou_404(AnotacaoFicticia, request.auth, id=anotacao_id)
    anotacao.titulo = dados.titulo
    anotacao.save(update_fields=["titulo"])
    return anotacao


@api.delete("/anotacoes/{anotacao_id}", response={204: None})
def excluir(request, anotacao_id: int):
    obter_da_usuaria_ou_404(AnotacaoFicticia, request.auth, id=anotacao_id).delete()
    return 204, None


urlpatterns = [path("api/", api.urls)]
