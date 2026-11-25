"""Extração de valor, data e estabelecimento de comprovantes (S5-02 / #96).

``extrair`` lê a imagem já validada do comprovante (S5-01), passa pelo OCR e
interpreta o texto. O texto lido nunca sai daqui: não é gravado, não vai para
log e não é devolvido inteiro pela API, só os trechos que sustentam cada campo.
"""
from django.utils import timezone

from .contrato import Campo, CamposExtraidos, ExtracaoOut
from .interpretacao import interpretar
from .ocr import Leitura, Linha, MotorOCR, OCRIndisponivel, motor_configurado

__all__ = ["Campo", "CamposExtraidos", "ExtracaoOut", "Leitura", "Linha", "MotorOCR", "OCRIndisponivel",
           "extrair", "motor_configurado"]


def extrair(comprovante, motor: MotorOCR | None = None, hoje=None) -> ExtracaoOut:
    """Lança ``OCRIndisponivel`` quando o motor não responde; nunca devolve campos inventados."""
    motor = motor or motor_configurado()
    leitura = motor.ler(comprovante.caminho.read_bytes())
    status, campos = interpretar(leitura, hoje or timezone.localdate())
    avisos = []
    if status == "ilegivel":
        avisos.append("Não consegui ler o comprovante. Tente uma foto mais nítida, de frente e com boa luz.")
    elif status == "parcial":
        avisos.append("Alguns campos não foram lidos com segurança; confira e complete antes de salvar.")
    return ExtracaoOut(comprovante_id=comprovante.id, status=status, campos=campos, motor=motor.nome, avisos=avisos)
