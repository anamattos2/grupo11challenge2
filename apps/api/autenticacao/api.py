"""Rotas de sessão da API. A autenticação é interna e não envolve bancos."""
from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from ninja import Field, Router, Schema
from ninja.errors import HttpError
from ninja.security import SessionAuth
from ninja.utils import check_csrf

# Exige sessão válida e, em métodos de escrita, token CSRF.
sessao = SessionAuth()

router = Router(tags=["autenticação"])


class CredenciaisIn(Schema):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=4096)


class UsuariaOut(Schema):
    id: int
    username: str


class CsrfOut(Schema):
    csrf_token: str


class ErroOut(Schema):
    detail: str


@router.get("/csrf", response=CsrfOut, auth=None)
def obter_csrf(request):
    """Entrega o token CSRF exigido no login e nas demais escritas."""
    return {"csrf_token": get_token(request)}


@router.post("/login", response={200: UsuariaOut, 401: ErroOut}, auth=None)
def entrar(request, credenciais: CredenciaisIn):
    """Abre a sessão. A resposta não revela se o usuário existe."""
    # Rota pública: sem autenticador, o CSRF precisa ser conferido aqui.
    if check_csrf(request):
        raise HttpError(403, "CSRF check Failed")

    usuaria = authenticate(
        request,
        username=credenciais.username,
        password=credenciais.password,
    )
    if usuaria is None:
        return 401, {"detail": "Usuário ou senha inválidos."}

    login(request, usuaria)
    return 200, usuaria


@router.post("/logout", response={204: None})
def sair(request):
    """Encerra a sessão atual e apaga seus dados no servidor."""
    logout(request)
    return 204, None


@router.get("/me", response=UsuariaOut)
def usuaria_atual(request):
    """Retorna a usuária identificada pela sessão."""
    return request.auth
