# Extração de campos de comprovantes

Referência: [S5-02 / #96](https://github.com/anamattos2/grupo11challenge2/issues/96).
Depende do upload ([S5-01 / #95](comprovantes.md)). Requisitos: RF16 e RNF06/RNF07
de [escopo e requisitos](../definicao/escopo-requisitos.md).
Código: `apps/api/comprovantes/extracao/`.

## 1. O que faz

`POST /api/comprovantes/{id}/extracao` lê a imagem de um comprovante da
própria usuária e devolve três campos: **valor total**, **data** e
**estabelecimento**. Cada campo diz se foi lido com segurança, se não está no
comprovante ou se ficou em dúvida. Nada é salvo e nenhuma despesa é criada: o
resultado alimenta a prévia editável (RF17), em que a usuária confere, corrige
e confirma.

```text
imagem (S5-01) → preparar (cinza, contraste, endireitar, ampliar)
              → OCR local (Tesseract, português)
              → interpretar (regras, sem inventar) → campos + status
```

## 2. Contrato

Cada campo (`Campo`) tem um de três estados, com regras validadas pelo Pydantic:

| Estado | Quando | `valor` | `trecho` | `candidatos` |
|---|---|---|---|---|
| `presente` | Exatamente uma leitura plausível, com boa confiança | Normalizado (`"19.40"`, `"2026-10-03"`, nome lido) | Texto lido que sustenta o valor | vazio |
| `ausente` | Nada parecido com o campo no texto lido | — | — | vazio |
| `ambiguo` | Há leitura, mas não dá para escolher com segurança | **nunca preenchido** | — | opções para a usuária, e/ou `motivo` |

A resposta (`ExtracaoOut`) tem `status`:

| `status` | Significado | HTTP |
|---|---|---|
| `completa` | Os três campos presentes | 200 |
| `parcial` | Imagem legível, mas algum campo ausente ou ambíguo (com aviso para conferir) | 200 |
| `ilegivel` | Pouco texto ou confiança muito baixa; todos os campos ausentes com motivo "imagem ilegível" e aviso para tirar outra foto | 200 |
| OCR indisponível | Motor não instalado, desligado, tempo esgotado ou falha: `{"codigo": "ocr_nao_instalado" \| "ocr_desligado" \| "ocr_tempo_esgotado" \| "ocr_falhou"}`, **sem campos** | 503 |

Indisponibilidade nunca vira "não encontrei nada": a usuária sabe que pode
preencher manualmente ou tentar de novo.

## 3. Regras de leitura (sem inventar)

| Campo | Fica `presente` quando | Fica `ambiguo` quando |
|---|---|---|
| Valor total | Uma linha com rótulo de total (`TOTAL`, `VALOR TOTAL`, `TOTAL A PAGAR`…) traz um único valor positivo; linhas de subtotal, troco, desconto, tributos, itens e valor recebido não contam | Dois totais diferentes; valores sem rótulo de total; total com baixa confiança; total zero ou negativo, com o sinal preservado |
| Data | Uma única data válida, não futura, de 2000 em diante (`dd/mm/aaaa`, `dd/mm/aa`, `dd-mm-aaaa`, `dd.mm.aaaa`). Rótulos de compra, venda, pagamento ou transação têm prioridade sobre datas auxiliares | Datas conflitantes; data impossível ou futura; apenas data auxiliar (ex.: impressão); baixa confiança |
| Estabelecimento | Rótulo explícito (`Estabelecimento:`) ou único nome plausível do cabeçalho, antes de CNPJ, data, valores e itens, que parece nome (letras, sem palavras como cupom, rua, CNPJ) | Mais de um nome distinto no contexto selecionado ou baixa confiança na linha |

Princípios:

- O código só muda a **notação** (`1.234,56` → `1234.56`, `03/10/26` → `2026-10-03`).
  Nunca completa, arredonda, corrige ou estima.
- Confiança do OCR abaixo de 60 (escala 0–100 do Tesseract) transforma um
  campo que seria presente em ambíguo.
- O `trecho` é copiado do texto lido. Se a linha do total ou da data exceder
  o limite do trecho, o campo fica ambíguo. Um teste de propriedade gera 3.000
  recibos corrompidos ao acaso e confere que todo campo presente tem trecho
  dentro do texto e valor que sai do próprio trecho.

## 4. OCR

- **Tesseract 5** com o idioma `por`, via `pytesseract`, rodando **local**: a
  imagem não sai do servidor.
- Antes do OCR: tons de cinza, contraste automático, **endireitamento** (procura o
  ângulo entre −6° e 6° que deixa as linhas de texto mais retas, só com Pillow) e
  ampliação de imagens com menos de 1000 px de largura, limitada a 8 milhões de
  pixels. Proporções acima de 20:1 retornam leitura ilegível. A preparação tem
  dimensões limitadas, e o Tesseract recebe apenas o tempo restante do orçamento
  após essa etapa.
- Motor configurável (`COMPROVANTES_OCR_MOTOR`): `tesseract` (padrão) ou
  `desligado` (responde 503). O protocolo `MotorOCR` permite trocar por outro
  motor, por exemplo um modelo de visão local, sem mudar a interpretação.

| Variável | Padrão | Uso |
|---|---|---|
| `COMPROVANTES_OCR_MOTOR` | `tesseract` | `tesseract` ou `desligado` |
| `COMPROVANTES_OCR_IDIOMA` | `por` | Idioma do Tesseract |
| `COMPROVANTES_OCR_TEMPO_LIMITE_S` | `20` | Tempo máximo de uma leitura |

## 5. Privacidade e logs

- O texto lido não é gravado, não vai para log e não é devolvido inteiro: a
  resposta só traz o trecho de cada campo presente.
- O log registra id do comprovante, id da usuária, status e o **estado** de cada
  campo (`valor=presente data=ausente…`), nunca os valores.
- A rota usa o mesmo isolamento do upload: comprovante de outra pessoa,
  inexistente ou vencido responde o mesmo 404, e a imagem dela nem chega a ser lida.

## 6. Limites conhecidos

- O nome do estabelecimento é cópia literal do OCR. Uma letra trocada com alta
  confiança (ex.: "PAQ" em vez de "PAO") é erro de leitura, não invenção, e é
  corrigida na prévia. Valor e data são conferidos pelos testes com imagens
  degradadas: quando aparecem como presentes, estão certos.
- Fotos reais (papel térmico amassado, sombra, perspectiva) não estão no
  conjunto de testes, que usa imagens sintéticas. A avaliação com fotos
  fictícias reais fica para a issue de avaliação de imagens.
- Não há detecção de duplicação nesta etapa (o `sha256` da S5-01 servirá para isso).
