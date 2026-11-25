# Evidências locais — S5-02 / #96

Verificação em 23/11/2026, branch `feat-96-extracao-comprovantes`, criada sobre
`feat-95-upload-comprovantes` (S5-01). Dados inteiramente fictícios: os textos e
as imagens de comprovante são gerados pelos próprios testes.

## O que foi entregue

- `apps/api/comprovantes/extracao/`: contrato (`contrato.py`), OCR trocável com
  Tesseract local (`ocr.py`) e interpretação por regras (`interpretacao.py`).
- Rota `POST /api/comprovantes/{id}/extracao`.
- Dependência nova: `pytesseract==0.3.13`; job `backend` da CI passa a instalar
  `tesseract-ocr` e `tesseract-ocr-por`, para os testes com OCR real rodarem lá.
- Documentação: [extração de comprovantes](../arquitetura/extracao-comprovantes.md),
  guia de instalação do backend, variáveis no guia do ambiente.

## Critérios de aceite

| Critério | Evidência |
|---|---|
| Contrato diferencia campos presentes, ausentes e ambíguos | `ContratoTests`: estados válidos e oito combinações incoerentes recusadas (ambíguo nunca escolhe valor, presente exige trecho, ausente não tem candidatos); formato de valor e data; status coerente com os campos |
| Extração parcial não inventa dados | `InterpretacaoTests` (dois totais, valores sem rótulo, tributos, troco e subtotal, datas múltiplas, impossíveis e futuras, baixa confiança, recibo parcial); `NaoInventaPropriedadeTest` (3.000 recibos corrompidos: todo campo presente tem trecho no texto lido e valor derivado do trecho); `TesseractRealTests.test_imagens_degradadas_nunca_inventam` (18 imagens borradas, giradas e com pouco contraste: valor e data presentes estão sempre certos) |
| Imagem ilegível e indisponibilidade têm tratamento explícito | `IlegivelTests`; `RotaDeExtracaoTests` (ilegível responde 200 com status `ilegivel` e orientação; OCR não instalado, desligado, tempo esgotado e falha respondem 503 com código e sem campos); `TesseractRealTests` (imagem em branco e ruído → `ilegivel`) |

Também: isolamento e CSRF na rota nova (imagem de outra usuária nem chega a ser
lida), logs só com estados dos campos e nenhum registro criado pela extração.

## Execução

PostgreSQL 17 descartável, Python 3.12, Tesseract 5.3.4 com `por`:

```text
python manage.py check / makemigrations --check / migrate --check → OK
python manage.py test → 62 testes OK (32 da extração, 30 do upload e da base)
```

## Os testes pegam erro de verdade

| Regra removida de propósito | Teste que falhou |
|---|---|
| Dois totais: escolher o maior | `test_dois_totais_diferentes_sao_ambiguos_e_nada_e_escolhido`, `test_dois_totais_na_imagem_ficam_ambiguos`, `test_recibos_corrompidos` |
| Sem rótulo: usar o último valor | `test_recibo_parcial_so_preenche_o_que_leu`, `test_recibos_corrompidos` |
| Aceitar data futura | `test_datas` |
| Ignorar a confiança do OCR | `test_baixa_confianca_vira_ambiguo`, `test_recibos_corrompidos` |
| Linhas de tributos/itens/recebido contando como total | `test_linha_de_tributos_e_subtotal_nao_contam_como_total` |

## Achado durante a implementação

Com a imagem girada 3°, o Tesseract leu "PAQ" em vez de "PAO" com confiança 90,
alta demais para ser barrada pela regra de confiança. A correção foi endireitar
a imagem antes do OCR (perfil de projeção, só com Pillow), e a leitura passou a
ficar correta entre −5° e 5°. O nome continua sendo cópia literal do OCR e é
editável na prévia; valor e data têm checagem estrita nos testes.
