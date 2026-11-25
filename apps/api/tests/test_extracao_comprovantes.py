"""Extração de campos de comprovantes (S5-02 / #96). Só dados fictícios."""
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from io import BytesIO
import os
import random
import shutil
from unittest import mock, skipUnless

from django.test import Client, SimpleTestCase, override_settings
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pydantic import ValidationError

from comprovantes.extracao import Campo, CamposExtraidos, ExtracaoOut, Leitura, Linha, OCRIndisponivel
from comprovantes.extracao.interpretacao import (
    _DATA,
    _DINHEIRO,
    _DINHEIRO_PONTO,
    _decimal_de,
    extrair_data,
    extrair_estabelecimento,
    extrair_valor_total,
    interpretar,
)
from comprovantes.extracao.ocr import MotorTesseract, preparar

from .test_comprovantes import BaseComprovantes, URL

HOJE = date(2026, 11, 18)
RECIBO = [
    "PADARIA PAO QUENTE LTDA",
    "CNPJ 12.345.678/0001-90",
    "Rua das Flores, 100 - Centro",
    "CUPOM FISCAL ELETRONICO",
    "03/10/2026 14:32",
    "PAO FRANCES 12,50",
    "LEITE INTEGRAL 6,90",
    "TOTAL R$ 19,40",
    "Valor aprox. dos tributos R$ 2,10",
]


def leitura(*linhas, confianca=95.0) -> Leitura:
    return Leitura([Linha(l, confianca) for l in linhas])


class MotorFixo:
    nome = "fixo"

    def __init__(self, resultado):
        self.resultado = resultado
        self.chamadas = 0

    def ler(self, imagem):
        self.chamadas += 1
        if isinstance(self.resultado, Exception):
            raise self.resultado
        return self.resultado


# --------------------------------------------------------------------------
# Critério 1: contrato diferencia presentes, ausentes e ambíguos
# --------------------------------------------------------------------------


class ContratoTests(SimpleTestCase):
    def test_estados_validos(self):
        Campo(estado="presente", valor="19.40", trecho="TOTAL R$ 19,40")
        Campo(estado="ausente")
        Campo(estado="ambiguo", candidatos=["19.40", "21.00"], motivo="dois totais")
        Campo(estado="ambiguo", motivo="leitura com baixa confiança")

    def test_estados_incoerentes_sao_recusados(self):
        invalidos = [
            dict(estado="presente", valor="19.40"),  # sem trecho
            dict(estado="presente", trecho="TOTAL"),  # sem valor
            dict(estado="presente", valor="19.40", trecho="TOTAL", candidatos=["21.00"]),
            dict(estado="ausente", valor="19.40"),
            dict(estado="ausente", candidatos=["19.40"]),
            dict(estado="ambiguo", valor="19.40", candidatos=["19.40", "21.00"]),  # ambíguo não escolhe
            dict(estado="ambiguo"),  # sem candidatos nem motivo
            dict(estado="lido"),
        ]
        for dados in invalidos:
            with self.subTest(dados=dados), self.assertRaises(ValidationError):
                Campo(**dados)

    def test_formatos_dos_campos_presentes(self):
        ok = Campo(estado="presente", valor="x", trecho="x")
        with self.assertRaises(ValidationError):
            CamposExtraidos(valor_total=Campo(estado="presente", valor="dezenove", trecho="t"), data=ok, estabelecimento=ok)
        with self.assertRaises(ValidationError):
            CamposExtraidos(valor_total=Campo(estado="presente", valor="0.00", trecho="t"), data=ok, estabelecimento=ok)
        with self.assertRaises(ValidationError):
            CamposExtraidos(valor_total=Campo(estado="ausente"), data=Campo(estado="presente", valor="03/10/2026", trecho="t"),
                            estabelecimento=ok)

    def test_status_coerente_com_os_campos(self):
        presente = Campo(estado="presente", valor="19.40", trecho="TOTAL 19,40")
        data = Campo(estado="presente", valor="2026-10-03", trecho="03/10/2026")
        campos = CamposExtraidos(valor_total=presente, data=data, estabelecimento=Campo(estado="ausente"))
        uuid = "00000000-0000-4000-8000-000000000000"
        with self.assertRaises(ValidationError):
            ExtracaoOut(comprovante_id=uuid, status="completa", campos=campos, motor="x")
        with self.assertRaises(ValidationError):
            ExtracaoOut(comprovante_id=uuid, status="ilegivel", campos=campos, motor="x")
        ExtracaoOut(comprovante_id=uuid, status="parcial", campos=campos, motor="x")


# --------------------------------------------------------------------------
# Critério 2: extração parcial não inventa dados
# --------------------------------------------------------------------------


class InterpretacaoTests(SimpleTestCase):
    def test_recibo_completo(self):
        status, campos = interpretar(leitura(*RECIBO), HOJE)
        self.assertEqual(status, "completa")
        self.assertEqual((campos.valor_total.valor, campos.valor_total.trecho), ("19.40", "TOTAL R$ 19,40"))
        self.assertEqual((campos.data.valor, campos.data.trecho), ("2026-10-03", "03/10/2026 14:32"))
        self.assertEqual((campos.estabelecimento.valor, campos.estabelecimento.trecho),
                         ("PADARIA PAO QUENTE LTDA", "PADARIA PAO QUENTE LTDA"))

    def test_linha_de_tributos_e_subtotal_nao_contam_como_total(self):
        campo = extrair_valor_total(leitura("SUBTOTAL 25,00", "DESCONTO 5,60", "Valor total aprox. dos tributos R$ 2,10",
                                            "TOTAL DE ITENS 2,00", "TOTAL A PAGAR 19,40", "TROCO 0,60",
                                            "Valor total recebido 20,00"))
        self.assertEqual((campo.estado, campo.valor), ("presente", "19.40"))

    def test_variantes_de_subtotal_e_descontos_nao_sao_totais(self):
        for linha in ("SUB-TOTAL 25,00", "TOTAL DESCONTOS 5,60", "TOTAL TRIBUTO 2,10",
                      "TOTAL IMPOSTO 2,10", "TOTAL DE ITEM 1,00", "TOTAL TROCOS 0,60"):
            with self.subTest(linha=linha):
                self.assertEqual(extrair_valor_total(leitura(linha)).estado, "ambiguo")
                campo = extrair_valor_total(leitura(linha, "TOTAL 30,00"))
                self.assertEqual((campo.estado, campo.valor), ("presente", "30.00"))

    def test_total_sem_valor_no_limite_do_trecho_fica_ambiguo(self):
        campo = extrair_valor_total(leitura("TOTAL " + " " * 200 + "30,00"))
        self.assertEqual((campo.estado, campo.valor, campo.trecho), ("ambiguo", None, None))

    def test_dois_totais_diferentes_sao_ambiguos_e_nada_e_escolhido(self):
        campo = extrair_valor_total(leitura("TOTAL 19,40", "VALOR TOTAL 21,00"))
        self.assertEqual((campo.estado, campo.valor, campo.candidatos), ("ambiguo", None, ["19.40", "21.00"]))

    def test_mesmo_total_repetido_continua_presente(self):
        campo = extrair_valor_total(leitura("TOTAL 19,40", "VALOR A PAGAR R$ 19,40"))
        self.assertEqual((campo.estado, campo.valor), ("presente", "19.40"))

    def test_valores_sem_rotulo_de_total_nao_viram_total(self):
        campo = extrair_valor_total(leitura("PAO FRANCES 12,50", "LEITE 6,90"))
        self.assertEqual((campo.estado, campo.valor), ("ambiguo", None))
        self.assertEqual(campo.candidatos, ["12.50", "6.90"])
        self.assertEqual(campo.motivo, "há valores, mas nenhum rotulado como total")

    def test_sem_valor_nenhum_e_ausente(self):
        self.assertEqual(extrair_valor_total(leitura("PADARIA", "OBRIGADO PELA PREFERENCIA")).estado, "ausente")

    def test_notacoes_de_valor(self):
        casos = {"TOTAL R$ 1.234,56": "1234.56", "TOTAL 19.40": "19.40", "Total: 7,00": "7.00"}
        for linha, esperado in casos.items():
            with self.subTest(linha=linha):
                self.assertEqual(extrair_valor_total(leitura(linha)).valor, esperado)

    def test_total_zerado_nao_e_presente(self):
        self.assertNotEqual(extrair_valor_total(leitura("TOTAL 0,00")).estado, "presente")

    def test_total_negativo_nao_vira_despesa_positiva(self):
        casos = (
            ("TOTAL -R$ 19,40",),
            ("TOTAL R$ −19,40",),
            ("TOTAL R$ 19,40-",),
            ("TOTAL (R$ 19,40)",),
            ("TOTAL -19.40", "TOTAL 20,00"),
        )
        for linhas in casos:
            with self.subTest(linhas=linhas):
                campo = extrair_valor_total(leitura(*linhas))
                self.assertEqual((campo.estado, campo.valor), ("ambiguo", None))
                self.assertIn("-19.40", campo.candidatos)

    def test_data_de_impressao_nao_substitui_data_de_compra(self):
        casos = (
            (("Data da compra: 31/02/2026", "Data de impressão: 03/03/2026"), "ambiguo", None),
            (("Data da compra: 03/03/2026 Data de impressão: 04/03/2026",), "presente", "2026-03-03"),
            (("Data de impressão: 03/03/2026",), "ambiguo", None),
            (("Data de impressão:", "03/03/2026"), "ambiguo", None),
            (("Impresso em 03/03/2026",), "ambiguo", None),
            (("Emissão 03/03/2026", "Impresso em 03/03/2026"), "presente", "2026-03-03"),
            (("03/10/2026", "31/02/2026"), "ambiguo", None),
        )
        for linhas, estado, valor in casos:
            with self.subTest(linhas=linhas):
                campo = extrair_data(leitura(*linhas), HOJE)
                self.assertEqual((campo.estado, campo.valor), (estado, valor))

    def test_estabelecimentos_explicitos_conflitantes_sao_ambiguos(self):
        campo = extrair_estabelecimento(leitura(
            "Estabelecimento: Padaria Primavera", "Estabelecimento: Mercado Central"))
        self.assertEqual((campo.estado, campo.valor), ("ambiguo", None))
        self.assertEqual(campo.candidatos, ["Padaria Primavera", "Mercado Central"])

        repetido = extrair_estabelecimento(leitura(
            "Estabelecimento: Farmácia Saúde", "Loja: FARMACIA SAUDE"))
        self.assertEqual((repetido.estado, repetido.valor), ("presente", "Farmácia Saúde"))

    def test_datas(self):
        casos = [
            (("03/10/26 14:32",), "presente", "2026-10-03"),
            (("Emissao: 03-10-2026",), "presente", "2026-10-03"),
            (("03/10/2026", "Validade 05/12/2025"), "ambiguo", None),
            (("31/02/2026",), "ambiguo", None),
            (("03/10/2027",), "ambiguo", None),  # futura em relação a HOJE
            (("sem data aqui",), "ausente", None),
        ]
        for linhas, estado, valor in casos:
            with self.subTest(linhas=linhas):
                campo = extrair_data(leitura(*linhas), HOJE)
                self.assertEqual((campo.estado, campo.valor), (estado, valor))

    def test_cabecalho_com_estabelecimentos_conflitantes_fica_ambiguo(self):
        campo = extrair_estabelecimento(leitura(
            "PADARIA PRIMAVERA", "MERCADO CENTRAL", "CNPJ 12.345.678/0001-90"))
        self.assertEqual((campo.estado, campo.valor), ("ambiguo", None))
        self.assertEqual(campo.candidatos, ["PADARIA PRIMAVERA", "MERCADO CENTRAL"])

    def test_estabelecimento(self):
        casos = [
            (("MERCADO BOM PRECO", "CNPJ 12.345.678/0001-90"), "presente", "MERCADO BOM PRECO"),
            (("Estabelecimento: Farmácia Saúde", "TOTAL 10,00"), "presente", "Farmácia Saúde"),
            (("CUPOM FISCAL", "CNPJ 12.345.678/0001-90", "TOTAL 10,00"), "ausente", None),
            (("CNPJ 12.345.678/0001-90", "MERCADO DEPOIS DO CNPJ"), "ausente", None),
            (("12345 678 90",), "ausente", None),
        ]
        for linhas, estado, valor in casos:
            with self.subTest(linhas=linhas):
                campo = extrair_estabelecimento(leitura(*linhas))
                self.assertEqual((campo.estado, campo.valor), (estado, valor))

    def test_baixa_confianca_vira_ambiguo(self):
        baixa = Leitura([Linha("MERCADO BOM PRECO", 40.0), Linha("03/10/2026", 35.0), Linha("TOTAL 19,40", 41.0)])
        status, campos = interpretar(baixa, HOJE)
        self.assertEqual(status, "parcial")
        for campo in (campos.valor_total, campos.data, campos.estabelecimento):
            self.assertEqual((campo.estado, campo.valor), ("ambiguo", None))
            self.assertTrue(campo.candidatos)

    def test_recibo_parcial_so_preenche_o_que_leu(self):
        status, campos = interpretar(leitura("PADARIA PAO QUENTE", "PAO FRANCES 12,50", "OBRIGADO"), HOJE)
        self.assertEqual(status, "parcial")
        self.assertEqual(campos.estabelecimento.estado, "presente")
        self.assertEqual(campos.data.estado, "ausente")
        self.assertEqual(campos.valor_total.estado, "ambiguo")


def _derivavel(nome: str, campo: Campo) -> bool:
    """O valor de um campo presente sai do próprio trecho, sem completar nada."""
    if nome == "valor_total":
        lidos = [_decimal_de(v) for v in _DINHEIRO.findall(campo.trecho) + _DINHEIRO_PONTO.findall(campo.trecho)]
        return campo.valor in lidos
    if nome == "data":
        for dia, mes, ano in _DATA.findall(campo.trecho):
            ano = int(ano) + 2000 if len(ano) == 2 else int(ano)
            if f"{ano:04d}-{int(mes):02d}-{int(dia):02d}" == campo.valor:
                return True
        return False
    return campo.valor in campo.trecho


class NaoInventaPropriedadeTest(SimpleTestCase):
    """Milhares de recibos corrompidos ao acaso: nenhum campo presente sai de fora do texto lido."""

    def test_recibos_corrompidos(self):
        sorteio = random.Random(96)
        lojas = ["PADARIA PAO QUENTE", "MERCADO BOM PRECO", "FARMACIA SAUDE", "POSTO ESTRADA", "LIVRARIA LER"]
        rotulos = ["TOTAL", "TOTAL R$", "VALOR TOTAL", "TOTAL A PAGAR", "SUBTOTAL", "TROCO", "VALOR PAGO"]
        lixo = ["@#$%", "1l1l1", "0O0O", "....", "R$", "TOTA1", "T0TAL 1,9", "25/13/2026", "00/00/0000"]
        estados = set()
        for rodada in range(3000):
            linhas = []
            if sorteio.random() < 0.8:
                linhas.append(sorteio.choice(lojas))
            if sorteio.random() < 0.5:
                linhas.append("CNPJ 12.345.678/0001-90")
            if sorteio.random() < 0.7:
                linhas.append(f"{sorteio.randint(1, 31):02d}/{sorteio.randint(1, 13):02d}/{sorteio.choice(['2026', '26', '2025', '2027'])}")
            for _ in range(sorteio.randint(0, 4)):
                linhas.append(f"ITEM {sorteio.randint(1, 99)},{sorteio.randint(0, 99):02d}")
            for _ in range(sorteio.randint(0, 2)):
                linhas.append(f"{sorteio.choice(rotulos)} {sorteio.randint(0, 999)},{sorteio.randint(0, 99):02d}")
            for _ in range(sorteio.randint(0, 3)):
                linhas.insert(sorteio.randint(0, len(linhas)), sorteio.choice(lixo))
            sorteio.shuffle(linhas) if sorteio.random() < 0.2 else None
            confianca = sorteio.choice([95.0, 70.0, 50.0, -1.0])
            lida = leitura(*linhas, confianca=confianca)
            with self.subTest(rodada=rodada):
                status, campos = interpretar(lida, HOJE)
                ExtracaoOut(comprovante_id="00000000-0000-4000-8000-000000000000", status=status, campos=campos,
                            motor="fuzz")  # revalida o contrato
                for nome in ("valor_total", "data", "estabelecimento"):
                    campo = getattr(campos, nome)
                    estados.add((nome, campo.estado))
                    if campo.estado == "presente":
                        self.assertIn(campo.trecho, lida.texto)
                        self.assertTrue(_derivavel(nome, campo), (nome, campo))
                        self.assertFalse(0 <= confianca < 60)
                    if campo.estado == "ambiguo":
                        self.assertIsNone(campo.valor)
                    if nome == "valor_total" and campo.estado == "presente":
                        self.assertGreater(Decimal(campo.valor), 0)
        for nome in ("valor_total", "data", "estabelecimento"):
            for estado in ("presente", "ausente", "ambiguo"):
                self.assertIn((nome, estado), estados)


# --------------------------------------------------------------------------
# Critério 3: imagem ilegível e indisponibilidade com tratamento explícito
# --------------------------------------------------------------------------


class IlegivelTests(SimpleTestCase):
    def test_pouco_texto_ou_confianca_muito_baixa_e_ilegivel(self):
        for lida in (leitura(), leitura("@#", "..."), leitura(*RECIBO, confianca=12.0)):
            with self.subTest(lida=lida.texto[:20]):
                status, campos = interpretar(lida, HOJE)
                self.assertEqual(status, "ilegivel")
                for campo in (campos.valor_total, campos.data, campos.estabelecimento):
                    self.assertEqual((campo.estado, campo.motivo), ("ausente", "imagem ilegível"))


class PreparacaoOCRTests(SimpleTestCase):
    @staticmethod
    def imagem(largura, altura):
        saida = BytesIO()
        Image.new("L", (largura, altura), 255).save(saida, format="PNG")
        return saida.getvalue()

    def test_ampliacao_respeita_orcamento_de_pixels(self):
        with mock.patch("comprovantes.extracao.ocr.MAXIMO_PIXELS_OCR", 100_000), mock.patch(
            "comprovantes.extracao.ocr._angulo_de_inclinacao", return_value=6.0
        ):
            figura = preparar(self.imagem(80, 400))
        self.assertIsNotNone(figura)
        self.assertGreater(figura.width, 80)
        self.assertLessEqual(figura.width * figura.height, 100_000)

    def test_motor_trata_proporcao_inadequada_sem_chamar_tesseract(self):
        with mock.patch("pytesseract.image_to_data") as ler:
            leitura_ocr = MotorTesseract().ler(self.imagem(20, 420))
        self.assertEqual(leitura_ocr.linhas, [])
        ler.assert_not_called()

    def test_preparacao_consumida_no_orcamento_interrompe_antes_do_tesseract(self):
        with mock.patch("comprovantes.extracao.ocr.monotonic", side_effect=[0, 2]), mock.patch(
            "pytesseract.image_to_data"
        ) as ler:
            with self.assertRaises(OCRIndisponivel) as erro:
                MotorTesseract(tempo_limite_s=1).ler(self.imagem(120, 120))
        self.assertEqual(erro.exception.codigo, "ocr_tempo_esgotado")
        ler.assert_not_called()

    def test_ocr_real_e_obrigatorio_na_ci(self):
        if os.environ.get("CI") == "true":
            self.assertTrue(_tesseract_com_portugues(), "A CI exige Tesseract com idioma 'por'.")


class RotaDeExtracaoTests(BaseComprovantes):
    def setUp(self):
        super().setUp()
        self.id_da_ana = self.enviar().json()["id"]
        self.url = f"{URL}/{self.id_da_ana}/extracao"

    def com_motor(self, resultado):
        motor = MotorFixo(resultado)
        return motor, mock.patch("comprovantes.extracao.motor_configurado", return_value=motor)

    def test_dona_recebe_os_campos(self):
        _, troca = self.com_motor(leitura(*RECIBO))
        with troca:
            resposta = self.cliente_ana.post(self.url)
        self.assertEqual(resposta.status_code, 200)
        corpo = resposta.json()
        self.assertEqual(corpo["status"], "completa")
        self.assertEqual(corpo["campos"]["valor_total"]["valor"], "19.40")
        self.assertNotIn("texto", corpo)  # o texto lido inteiro nunca é devolvido
        self.assertNotIn("Rua das Flores", resposta.content.decode())

    def test_parcial_avisa_para_conferir(self):
        _, troca = self.com_motor(leitura("PADARIA PAO QUENTE", "PAO 12,50"))
        with troca:
            corpo = self.cliente_ana.post(self.url).json()
        self.assertEqual(corpo["status"], "parcial")
        self.assertTrue(corpo["avisos"])

    def test_ilegivel_responde_200_com_orientacao(self):
        _, troca = self.com_motor(leitura("@#"))
        with troca:
            resposta = self.cliente_ana.post(self.url)
        self.assertEqual((resposta.status_code, resposta.json()["status"]), (200, "ilegivel"))
        self.assertIn("foto mais nítida", resposta.json()["avisos"][0])

    def test_indisponibilidade_responde_503_e_nao_finge_resultado(self):
        for codigo in ("ocr_nao_instalado", "ocr_tempo_esgotado", "ocr_falhou"):
            with self.subTest(codigo=codigo):
                _, troca = self.com_motor(OCRIndisponivel(codigo))
                with troca:
                    resposta = self.cliente_ana.post(self.url)
                self.assertEqual(resposta.status_code, 503)
                self.assertEqual(resposta.json()["codigo"], codigo)
                self.assertNotIn("campos", resposta.json())

    @override_settings(COMPROVANTES_OCR_MOTOR="desligado")
    def test_motor_desligado_por_configuracao(self):
        resposta = self.cliente_ana.post(self.url)
        self.assertEqual((resposta.status_code, resposta.json()["codigo"]), (503, "ocr_desligado"))

    def test_tesseract_ausente_vira_indisponivel(self):
        import pytesseract
        with mock.patch.object(pytesseract.pytesseract, "tesseract_cmd", "/caminho/que/nao/existe/tesseract"):
            resposta = self.cliente_ana.post(self.url)
        self.assertEqual((resposta.status_code, resposta.json()["codigo"]), (503, "ocr_nao_instalado"))

    def test_tempo_esgotado_do_tesseract_vira_indisponivel(self):
        import pytesseract
        with mock.patch.object(pytesseract, "image_to_data", side_effect=RuntimeError("Tesseract process timeout")):
            with self.assertRaises(OCRIndisponivel) as erro:
                MotorTesseract().ler(Path_bytes(self))
        self.assertEqual(erro.exception.codigo, "ocr_tempo_esgotado")

    def test_isolamento_e_csrf(self):
        motor, troca = self.com_motor(leitura(*RECIBO))
        with troca:
            alheio = self.cliente_bia.post(self.url)
            inexistente = self.cliente_bia.post(f"{URL}/00000000-0000-4000-8000-000000000000/extracao")
            anonimo = Client().post(self.url)
            sem_csrf = Client(enforce_csrf_checks=True)
            sem_csrf.force_login(self.ana)
            recusado = sem_csrf.post(self.url)
        self.assertEqual((alheio.status_code, alheio.content), (404, inexistente.content))
        self.assertEqual(anonimo.status_code, 401)
        self.assertEqual(recusado.status_code, 403)
        self.assertEqual(motor.chamadas, 0)  # nem chega a ler a imagem de outra pessoa

    def test_logs_sem_texto_lido(self):
        _, troca = self.com_motor(leitura(*RECIBO))
        with troca, self.assertLogs("comprovantes", level="INFO") as registro:
            self.cliente_ana.post(self.url)
        texto = "\n".join(registro.output)
        self.assertIn("status=completa valor=presente data=presente estabelecimento=presente", texto)
        for proibido in ("PADARIA", "19,40", "19.40", "12.345.678", "Flores", "2026-10-03"):
            self.assertNotIn(proibido, texto)

    def test_extracao_nao_cria_registros(self):
        from django.apps import apps
        antes = {m._meta.label: m.objects.count() for m in apps.get_models()}
        _, troca = self.com_motor(leitura(*RECIBO))
        with troca:
            self.cliente_ana.post(self.url)
        self.assertEqual(antes, {m._meta.label: m.objects.count() for m in apps.get_models()})


def Path_bytes(teste):
    from comprovantes.models import Comprovante
    return Comprovante.objects.get(id=teste.id_da_ana).caminho.read_bytes()


# --------------------------------------------------------------------------
# OCR de verdade (Tesseract), com imagens sintéticas
# --------------------------------------------------------------------------

FONTE = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def _tesseract_com_portugues() -> bool:
    try:
        import pytesseract
        return shutil.which("tesseract") is not None and "por" in pytesseract.get_languages(config="")
    except Exception:  # noqa: BLE001
        return False


def recibo_em_imagem(linhas, *, borrar=0.0, girar=0.0, contraste=1.0) -> bytes:
    try:
        fonte = ImageFont.truetype(FONTE, 28)
    except OSError:
        fonte = ImageFont.load_default(28)
    figura = Image.new("L", (760, 70 + 44 * len(linhas)), 255)
    desenho = ImageDraw.Draw(figura)
    for i, linha in enumerate(linhas):
        desenho.text((30, 30 + 44 * i), linha, font=fonte, fill=int(255 * (1 - contraste)))
    if girar:
        figura = figura.rotate(girar, expand=True, fillcolor=255)
    if borrar:
        figura = figura.filter(ImageFilter.GaussianBlur(borrar))
    saida = BytesIO()
    figura.convert("RGB").save(saida, format="PNG")
    return saida.getvalue()


@skipUnless(_tesseract_com_portugues(), "Tesseract com idioma 'por' não está instalado")
class TesseractRealTests(BaseComprovantes):
    def extrair_imagem(self, conteudo):
        resposta = self.enviar(conteudo=conteudo, tipo="image/png")
        self.assertEqual(resposta.status_code, 201, resposta.content)
        return self.cliente_ana.post(f"{URL}/{resposta.json()['id']}/extracao").json()

    def test_recibo_nitido_e_lido_por_completo(self):
        corpo = self.extrair_imagem(recibo_em_imagem(RECIBO))
        campos = corpo["campos"]
        self.assertEqual(corpo["motor"], "tesseract")
        self.assertEqual(campos["valor_total"]["valor"], "19.40")
        self.assertEqual(campos["data"]["valor"], "2026-10-03")
        self.assertEqual(campos["estabelecimento"]["valor"], "PADARIA PAO QUENTE LTDA")

    def test_imagem_em_branco_e_ruido_sao_ilegiveis(self):
        branco = BytesIO()
        Image.new("RGB", (600, 800), "white").save(branco, format="PNG")
        ruido = BytesIO()
        Image.effect_noise((600, 800), 120).convert("RGB").save(ruido, format="PNG")
        for nome, conteudo in (("branco", branco.getvalue()), ("ruido", ruido.getvalue())):
            with self.subTest(nome=nome):
                self.assertEqual(self.extrair_imagem(conteudo)["status"], "ilegivel")

    def test_dois_totais_na_imagem_ficam_ambiguos(self):
        linhas = RECIBO[:7] + ["TOTAL R$ 19,40", "VALOR TOTAL R$ 21,00"]
        campo = self.extrair_imagem(recibo_em_imagem(linhas))["campos"]["valor_total"]
        self.assertEqual((campo["estado"], campo["valor"]), ("ambiguo", None))

    def test_imagens_degradadas_nunca_inventam(self):
        verdade = {"valor_total": "19.40", "data": "2026-10-03", "estabelecimento": "PADARIA PAO QUENTE LTDA"}
        variacoes = [dict(borrar=b, girar=g, contraste=c) for b in (0, 1.2, 2.5) for g in (0, 1.5, -3) for c in (1.0, 0.35)]
        lidos = 0
        for variacao in variacoes:
            with self.subTest(**variacao):
                campos = self.extrair_imagem(recibo_em_imagem(RECIBO, **variacao))["campos"]
                for nome, esperado in verdade.items():
                    if campos[nome]["estado"] == "presente":
                        lidos += 1
                        if nome == "estabelecimento":
                            # Nome é cópia literal do OCR (editável na prévia); uma letra trocada é leitura, não invenção.
                            self.assertGreaterEqual(SequenceMatcher(None, campos[nome]["valor"], esperado).ratio(), 0.85)
                        else:
                            self.assertEqual(campos[nome]["valor"], esperado)  # valor e data: leu, leu certo
        self.assertGreater(lidos, len(variacoes))  # e leu boa parte
