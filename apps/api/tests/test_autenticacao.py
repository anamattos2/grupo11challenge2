import re
from io import StringIO
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management import CommandError, call_command
from django.test import Client, TestCase

JSON = "application/json"
SENHA = "senha-ficticia-para-testes-11"
ROTAS_PUBLICAS = {
    ("GET", "/api/health"),
    ("GET", "/api/auth/csrf"),
    ("POST", "/api/auth/login"),
}


class BaseAutenticacao(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = get_user_model().objects.create_user("ana.ficticia", password=SENHA)

    def entrar(self, cliente=None, username="ana.ficticia", password=SENHA, **extra):
        return (cliente or self.client).post(
            "/api/auth/login",
            {"username": username, "password": password},
            content_type=JSON,
            **extra,
        )


class LoginTests(BaseAutenticacao):
    def test_login_valido_abre_sessao(self):
        resposta = self.entrar()

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json(), {"id": self.ana.id, "username": "ana.ficticia"})
        self.assertEqual(self.client.get("/api/auth/me").json()["id"], self.ana.id)

    def test_senha_errada_e_usuario_inexistente_tem_a_mesma_resposta(self):
        senha_errada = self.entrar(password="senha-incorreta-ficticia")
        inexistente = self.entrar(username="nao.existe")

        self.assertEqual(senha_errada.status_code, 401)
        self.assertEqual(inexistente.status_code, 401)
        self.assertEqual(senha_errada.content, inexistente.content)
        self.assertNotIn(settings.SESSION_COOKIE_NAME, self.client.cookies)

    def test_usuaria_inativa_nao_entra(self):
        get_user_model().objects.filter(id=self.ana.id).update(is_active=False)

        self.assertEqual(self.entrar().status_code, 401)

    def test_desativar_usuaria_invalida_sessao_aberta(self):
        self.entrar()
        get_user_model().objects.filter(id=self.ana.id).update(is_active=False)

        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_login_troca_identificador_da_sessao(self):
        sessao = self.client.session
        sessao["marca"] = "anonima"
        sessao.save()
        anterior = sessao.session_key

        self.entrar()

        self.assertNotEqual(self.client.session.session_key, anterior)

    def test_cookie_de_sessao_nao_fica_acessivel_ao_javascript(self):
        self.entrar()

        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

    def test_erro_de_validacao_nao_devolve_a_senha(self):
        senha_longa = "x" * 4097

        resposta = self.entrar(password=senha_longa)

        self.assertEqual(resposta.status_code, 422)
        self.assertNotIn(senha_longa, resposta.content.decode())


class LogoutTests(BaseAutenticacao):
    def test_logout_encerra_a_sessao(self):
        self.entrar()

        resposta = self.client.post("/api/auth/logout")

        self.assertEqual(resposta.status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(Session.objects.count(), 0)

    def test_cookie_antigo_nao_funciona_depois_do_logout(self):
        self.entrar()
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.client.post("/api/auth/logout")

        repetido = Client()
        repetido.cookies[settings.SESSION_COOKIE_NAME] = cookie

        self.assertEqual(repetido.get("/api/auth/me").status_code, 401)

    def test_logout_sem_sessao_e_recusado(self):
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 401)


class CsrfTests(BaseAutenticacao):
    def setUp(self):
        self.cliente = Client(enforce_csrf_checks=True)

    def token(self):
        return self.cliente.get("/api/auth/csrf").json()["csrf_token"]

    def test_login_sem_token_csrf_e_recusado(self):
        self.assertEqual(self.entrar(self.cliente).status_code, 403)
        self.assertNotIn(settings.SESSION_COOKIE_NAME, self.cliente.cookies)

    def test_fluxo_completo_com_token_csrf(self):
        entrada = self.entrar(self.cliente, headers={"X-CSRFToken": self.token()})
        self.assertEqual(entrada.status_code, 200)

        # O login renova o token; o valor atual fica no cookie.
        token = self.cliente.cookies[settings.CSRF_COOKIE_NAME].value
        saida = self.cliente.post("/api/auth/logout", headers={"X-CSRFToken": token})
        self.assertEqual(saida.status_code, 204)

    def test_logout_sem_token_csrf_mantem_a_sessao(self):
        self.entrar(self.cliente, headers={"X-CSRFToken": self.token()})

        resposta = self.cliente.post("/api/auth/logout")

        self.assertEqual(resposta.status_code, 403)
        self.assertEqual(self.cliente.get("/api/auth/me").status_code, 200)


class ProtecaoDasRotasTests(TestCase):
    """Lê o contrato publicado para cobrir também as rotas das próximas issues."""

    def operacoes(self):
        caminhos = self.client.get("/api/openapi.json").json()["paths"]
        for caminho, metodos in caminhos.items():
            for metodo, operacao in metodos.items():
                yield metodo.upper(), caminho, bool(operacao.get("security"))

    def test_toda_rota_exige_sessao_salvo_as_publicas_declaradas(self):
        publicas = {
            (metodo, caminho)
            for metodo, caminho, protegida in self.operacoes()
            if not protegida
        }

        self.assertEqual(publicas, ROTAS_PUBLICAS)

    def test_rotas_protegidas_recusam_requisicao_anonima(self):
        protegidas = [
            (metodo, re.sub(r"{[^}]+}", "1", caminho))
            for metodo, caminho, protegida in self.operacoes()
            if protegida
        ]

        self.assertTrue(protegidas)
        for metodo, caminho in protegidas:
            with self.subTest(metodo=metodo, caminho=caminho):
                self.assertEqual(self.client.generic(metodo, caminho).status_code, 401)


class CriarUsuariaTests(TestCase):
    def executar(self, *senhas):
        with mock.patch(
            "autenticacao.management.commands.criar_usuaria.getpass",
            side_effect=senhas,
        ):
            call_command("criar_usuaria", "bia.ficticia", stdout=StringIO())

    def test_cria_usuaria_comum_com_senha_protegida(self):
        self.executar(SENHA, SENHA)

        usuaria = get_user_model().objects.get(username="bia.ficticia")
        self.assertTrue(usuaria.check_password(SENHA))
        self.assertFalse(usuaria.is_staff or usuaria.is_superuser)

    def test_recusa_senha_fraca_ou_divergente(self):
        for senhas in (("123", "123"), (SENHA, "outra-senha-ficticia")):
            with self.subTest(senhas=senhas), self.assertRaises(CommandError):
                self.executar(*senhas)

        self.assertFalse(get_user_model().objects.exists())
