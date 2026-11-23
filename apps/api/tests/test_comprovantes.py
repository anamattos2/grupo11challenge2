"""Upload autenticado de comprovantes (S5-01 / #95). Só imagens geradas no teste."""
from datetime import timedelta
from io import BytesIO, StringIO
import os
from pathlib import Path
import shutil
import tempfile
import time

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from comprovantes.models import Comprovante

URL = "/api/comprovantes"
NOME_ORIGINAL = "recibo-farmacia-maria-silva.jpg"


def imagem(formato="JPEG", tamanho=(320, 480), exif_gps=False) -> bytes:
    saida = BytesIO()
    figura = Image.new("RGB", tamanho, (240, 240, 230))
    opcoes = {}
    if exif_gps:
        exif = Image.Exif()
        exif[0x010F] = "FabricanteFicticio"  # Make
        exif[0x8825] = {1: "S", 2: (15.0, 47.0, 0.0)}  # GPSInfo
        opcoes["exif"] = exif.tobytes()
    figura.save(saida, format=formato, **opcoes)
    return saida.getvalue()


def arquivo(conteudo: bytes, nome=NOME_ORIGINAL, tipo="image/jpeg"):
    return SimpleUploadedFile(nome, conteudo, content_type=tipo)


class BaseComprovantes(TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.pasta, ignore_errors=True)
        configuracao = override_settings(COMPROVANTES_DIR=self.pasta)
        configuracao.enable()
        self.addCleanup(configuracao.disable)
        usuarias = get_user_model().objects
        self.ana = usuarias.create_user("ana-ficticia", password="senha-ficticia-1")
        self.bia = usuarias.create_user("bia-ficticia", password="senha-ficticia-2")
        self.cliente_ana, self.cliente_bia = Client(), Client()
        self.cliente_ana.force_login(self.ana)
        self.cliente_bia.force_login(self.bia)

    def enviar(self, cliente=None, conteudo=None, **kwargs):
        conteudo = imagem() if conteudo is None else conteudo
        return (cliente or self.cliente_ana).post(URL, {"arquivo": arquivo(conteudo, **kwargs)})

    def arquivos_na_pasta(self):
        return sorted(p.name for p in self.pasta.iterdir() if p.is_file())


class FormatoETamanhoTests(BaseComprovantes):
    """Critério: formato e tamanho validados."""

    def test_aceita_jpeg_png_e_webp(self):
        for formato, mime in (("JPEG", "image/jpeg"), ("PNG", "image/png"), ("WEBP", "image/webp")):
            with self.subTest(formato=formato):
                resposta = self.enviar(conteudo=imagem(formato), tipo=mime)
                self.assertEqual(resposta.status_code, 201, resposta.content)
                corpo = resposta.json()
                self.assertEqual((corpo["tipo_mime"], corpo["largura"], corpo["altura"]), (mime, 320, 480))
        self.assertEqual(len(self.arquivos_na_pasta()), 3)

    def test_formato_vem_do_conteudo_e_nao_do_nome_nem_do_content_type(self):
        resposta = self.enviar(conteudo=imagem("PNG"), nome="foto.jpg", tipo="image/jpeg")
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.json()["formato"], "png")

    def test_recusa_formatos_nao_aceitos_mesmo_com_nome_de_imagem(self):
        casos = {
            "pdf": b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n",
            "gif": imagem("GIF"),
            "texto": b"nao sou uma imagem",
            "html": b"<html><script>alert(1)</script></html>",
            "svg": b'<svg xmlns="http://www.w3.org/2000/svg"></svg>',
        }
        for nome, conteudo in casos.items():
            with self.subTest(nome=nome):
                resposta = self.enviar(conteudo=conteudo, nome="comprovante.jpg", tipo="image/jpeg")
                self.assertEqual(resposta.status_code, 415)
                self.assertEqual(resposta.json()["codigo"], "formato_nao_suportado")
        self.assertEqual(Comprovante.objects.count(), 0)
        self.assertEqual(self.arquivos_na_pasta(), [])

    def test_recusa_arquivo_vazio(self):
        resposta = self.enviar(conteudo=b"")
        self.assertIn(resposta.status_code, (400, 422))
        self.assertEqual(Comprovante.objects.count(), 0)

    def test_recusa_imagem_corrompida_com_cabecalho_valido(self):
        truncada = imagem()[:200]
        resposta = self.enviar(conteudo=truncada)
        self.assertEqual((resposta.status_code, resposta.json()["codigo"]), (400, "imagem_invalida"))
        self.assertEqual(self.arquivos_na_pasta(), [])

    @override_settings(COMPROVANTES_TAMANHO_MAXIMO_BYTES=10 * 1024)
    def test_recusa_arquivo_acima_do_limite_sem_gravar_nada(self):
        grande = imagem("PNG", tamanho=(400, 400))
        ruido = Image.effect_noise((400, 400), 100).convert("RGB")
        saida = BytesIO()
        ruido.save(saida, format="PNG")
        grande = saida.getvalue()
        self.assertGreater(len(grande), 10 * 1024)
        resposta = self.enviar(conteudo=grande, tipo="image/png")
        self.assertEqual((resposta.status_code, resposta.json()["codigo"]), (413, "arquivo_grande_demais"))
        self.assertEqual(Comprovante.objects.count(), 0)
        self.assertEqual(self.arquivos_na_pasta(), [])

    @override_settings(COMPROVANTES_MAXIMO_PIXELS=10_000)
    def test_recusa_resolucao_exagerada(self):
        resposta = self.enviar(conteudo=imagem("PNG", tamanho=(200, 200)), tipo="image/png")
        self.assertEqual((resposta.status_code, resposta.json()["codigo"]), (400, "imagem_grande_demais"))

    def test_metadados_exif_com_localizacao_sao_removidos(self):
        original = imagem(exif_gps=True)
        self.assertIn(b"FabricanteFicticio", original)
        resposta = self.enviar(conteudo=original)
        guardado = Comprovante.objects.get(id=resposta.json()["id"]).caminho.read_bytes()
        self.assertNotIn(b"FabricanteFicticio", guardado)
        with Image.open(BytesIO(guardado)) as lida:
            self.assertEqual(len(lida.getexif()), 0)

    def test_nome_original_nao_e_guardado(self):
        resposta = self.enviar()
        comprovante = Comprovante.objects.get(id=resposta.json()["id"])
        self.assertEqual(comprovante.caminho.name, f"{comprovante.id}.jpg")
        self.assertNotIn("maria", resposta.content.decode())

    def test_arquivo_gravado_com_permissao_restrita(self):
        resposta = self.enviar()
        caminho = Comprovante.objects.get(id=resposta.json()["id"]).caminho
        self.assertEqual(oct(os.stat(caminho).st_mode & 0o777), oct(0o600))

    @override_settings(COMPROVANTES_ENVIOS_POR_HORA=2)
    def test_limite_de_envios_por_hora(self):
        self.assertEqual(self.enviar().status_code, 201)
        self.assertEqual(self.enviar().status_code, 201)
        resposta = self.enviar()
        self.assertEqual((resposta.status_code, resposta.json()["codigo"]), (429, "limite_de_envios"))
        self.assertEqual(self.enviar(cliente=self.cliente_bia).status_code, 201)  # limite é por usuária


class IsolamentoTests(BaseComprovantes):
    """Critério: upload isolado por usuária."""

    def setUp(self):
        super().setUp()
        self.id_da_ana = self.enviar().json()["id"]
        self.id_inexistente = "00000000-0000-4000-8000-000000000000"

    def test_a_dona_lista_ve_e_baixa_o_proprio_comprovante(self):
        self.assertEqual([c["id"] for c in self.cliente_ana.get(URL).json()], [self.id_da_ana])
        self.assertEqual(self.cliente_ana.get(f"{URL}/{self.id_da_ana}").status_code, 200)
        download = self.cliente_ana.get(f"{URL}/{self.id_da_ana}/arquivo")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "image/jpeg")
        self.assertEqual(download["Cache-Control"], "private, no-store")
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("maria", download["Content-Disposition"])

    def test_outra_usuaria_nao_lista_nao_ve_nao_baixa_e_nao_apaga(self):
        self.assertEqual(self.cliente_bia.get(URL).json(), [])
        for metodo, sufixo in (("get", ""), ("get", "/arquivo"), ("delete", "")):
            with self.subTest(metodo=metodo, sufixo=sufixo):
                alheio = getattr(self.cliente_bia, metodo)(f"{URL}/{self.id_da_ana}{sufixo}")
                inexistente = getattr(self.cliente_bia, metodo)(f"{URL}/{self.id_inexistente}{sufixo}")
                self.assertEqual(alheio.status_code, 404)
                self.assertEqual(alheio.content, inexistente.content)  # não revela que o id existe
        self.assertTrue(Comprovante.objects.filter(id=self.id_da_ana).exists())

    def test_dona_vem_da_sessao_e_nao_do_formulario(self):
        resposta = self.cliente_bia.post(URL, {"arquivo": arquivo(imagem()), "usuaria": self.ana.pk,
                                               "usuaria_id": self.ana.pk})
        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(Comprovante.objects.get(id=resposta.json()["id"]).usuaria, self.bia)

    def test_sem_sessao_nenhuma_rota_responde(self):
        anonimo = Client()
        chamadas = [("post", URL), ("get", URL), ("get", f"{URL}/{self.id_da_ana}"),
                    ("get", f"{URL}/{self.id_da_ana}/arquivo"), ("delete", f"{URL}/{self.id_da_ana}")]
        for metodo, url in chamadas:
            with self.subTest(metodo=metodo, url=url):
                self.assertEqual(getattr(anonimo, metodo)(url).status_code, 401)

    def test_escrita_sem_token_csrf_e_recusada(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.ana)
        self.assertEqual(cliente.post(URL, {"arquivo": arquivo(imagem())}).status_code, 403)
        self.assertEqual(cliente.delete(f"{URL}/{self.id_da_ana}").status_code, 403)
        self.assertEqual(Comprovante.objects.count(), 1)

    def test_escrita_com_token_csrf_funciona(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.ana)
        cliente.get(URL)  # garante o cookie de sessão
        from django.middleware.csrf import _get_new_csrf_string
        token = _get_new_csrf_string()
        cliente.cookies["csrftoken"] = token
        resposta = cliente.post(URL, {"arquivo": arquivo(imagem())}, HTTP_X_CSRFTOKEN=token)
        self.assertEqual(resposta.status_code, 201)

    def test_todas_as_rotas_de_comprovantes_exigem_autenticacao_no_openapi(self):
        contrato = self.cliente_ana.get("/api/openapi.json").json()
        rotas = {caminho: operacoes for caminho, operacoes in contrato["paths"].items() if "comprovantes" in caminho}
        self.assertEqual(len(rotas), 4)  # inclui /{id}/extracao (S5-02)
        for caminho, operacoes in rotas.items():
            for metodo, operacao in operacoes.items():
                with self.subTest(rota=f"{metodo.upper()} {caminho}"):
                    self.assertTrue(operacao.get("security"))


class RetencaoERemocaoTests(BaseComprovantes):
    """Critério: retenção e remoção documentadas e verificadas."""

    @override_settings(COMPROVANTES_RETENCAO_HORAS=72)
    def test_prazo_de_retencao_e_aplicado_no_envio(self):
        antes = timezone.now()
        corpo = self.enviar().json()
        comprovante = Comprovante.objects.get(id=corpo["id"])
        self.assertAlmostEqual((comprovante.expira_em - antes).total_seconds(), 72 * 3600, delta=60)

    def test_excluir_remove_registro_e_arquivo(self):
        comprovante = Comprovante.objects.get(id=self.enviar().json()["id"])
        self.assertTrue(comprovante.caminho.exists())
        self.assertEqual(self.cliente_ana.delete(f"{URL}/{comprovante.id}").status_code, 204)
        self.assertFalse(Comprovante.objects.filter(id=comprovante.id).exists())
        self.assertFalse(comprovante.caminho.exists())

    def test_vencido_some_das_rotas_antes_mesmo_da_limpeza(self):
        comprovante = Comprovante.objects.get(id=self.enviar().json()["id"])
        Comprovante.objects.filter(id=comprovante.id).update(expira_em=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.cliente_ana.get(URL).json(), [])
        self.assertEqual(self.cliente_ana.get(f"{URL}/{comprovante.id}").status_code, 404)
        self.assertEqual(self.cliente_ana.get(f"{URL}/{comprovante.id}/arquivo").status_code, 404)

    def test_comando_de_limpeza_apaga_vencidos_e_orfaos_e_preserva_vigentes(self):
        vencido = Comprovante.objects.get(id=self.enviar().json()["id"])
        vigente = Comprovante.objects.get(id=self.enviar().json()["id"])
        Comprovante.objects.filter(id=vencido.id).update(expira_em=timezone.now() - timedelta(hours=1))
        orfao_antigo = self.pasta / "orfao-antigo.jpg"
        orfao_recente = self.pasta / "envio-em-andamento.jpg"
        for caminho in (orfao_antigo, orfao_recente):
            caminho.write_bytes(b"x")
        duas_horas = time.time() - 2 * 3600
        os.utime(orfao_antigo, (duas_horas, duas_horas))

        simulacao = StringIO()
        call_command("limpar_comprovantes", "--simular", stdout=simulacao)
        self.assertIn("Seriam apagados: 1 comprovante(s) vencido(s), 1 arquivo(s) órfão(s).", simulacao.getvalue())
        self.assertTrue(vencido.caminho.exists())

        saida = StringIO()
        call_command("limpar_comprovantes", stdout=saida)
        self.assertIn("Apagados: 1 comprovante(s) vencido(s), 1 arquivo(s) órfão(s).", saida.getvalue())
        self.assertFalse(Comprovante.objects.filter(id=vencido.id).exists())
        self.assertFalse(vencido.caminho.exists())
        self.assertFalse(orfao_antigo.exists())
        self.assertTrue(orfao_recente.exists())
        self.assertTrue(vigente.caminho.exists())

    def test_excluir_a_usuaria_apaga_os_comprovantes_dela(self):
        comprovante = Comprovante.objects.get(id=self.enviar().json()["id"])
        do_bia = Comprovante.objects.get(id=self.enviar(cliente=self.cliente_bia).json()["id"])
        self.ana.delete()
        self.assertFalse(comprovante.caminho.exists())
        self.assertTrue(do_bia.caminho.exists())


class LogsSemConteudoTests(BaseComprovantes):
    """Critério: sem conteúdo bruto em logs."""

    def test_logs_de_envio_recusa_e_exclusao_nao_trazem_conteudo_nem_nome(self):
        conteudo = imagem(exif_gps=True)
        with self.assertLogs("comprovantes", level="INFO") as registro:
            corpo = self.enviar(conteudo=conteudo).json()
            self.enviar(conteudo=b"%PDF-1.7 conteudo ficticio", nome="extrato-banco-maria.pdf")
            self.cliente_ana.delete(f"{URL}/{corpo['id']}")
        texto = "\n".join(registro.output)
        self.assertIn(f"comprovante recebido id={corpo['id']}", texto)
        self.assertIn("motivo=formato_nao_suportado", texto)
        self.assertIn(f"comprovante excluido id={corpo['id']}", texto)
        for proibido in ("maria", "recibo", "extrato", "PDF", "FabricanteFicticio", "ana-ficticia"):
            self.assertNotIn(proibido, texto)
        self.assertNotIn(repr(conteudo[:20])[2:-1], texto)

    def test_upload_nao_cria_outros_registros(self):
        from django.apps import apps
        antes = {m._meta.label: m.objects.count() for m in apps.get_models() if m is not Comprovante}
        self.enviar()
        depois = {m._meta.label: m.objects.count() for m in apps.get_models() if m is not Comprovante}
        self.assertEqual(antes, depois)  # nenhuma despesa ou transação nasce do upload
