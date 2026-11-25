# Upload de comprovantes por imagem

Referência: [S5-01 / #95](https://github.com/anamattos2/grupo11challenge2/issues/95).
Requisitos: RF16, RNF03, RNF05 e RNF06 de
[escopo e requisitos](../definicao/escopo-requisitos.md).
Código: `apps/api/comprovantes/`.

## 1. O que esta etapa faz

A usuária envia a foto de um comprovante. O backend confere se é mesmo uma
imagem aceita, remove os metadados, guarda uma cópia numa pasta privada e
devolve um identificador. **O upload não cria despesa nem transação.** A
extração dos campos (OCR) e a prévia editável ficam para as próximas issues, e
a despesa só nasce na confirmação explícita (RF17).

## 2. Rotas

Todas exigem sessão do Django. Envio e exclusão exigem também o token CSRF
(cabeçalho `X-CSRFToken`).

| Método e rota | O que faz | Respostas |
|---|---|---|
| `POST /api/comprovantes` (multipart, campo `arquivo`) | Valida e guarda a imagem | 201, 400, 401, 403, 413, 415, 429 |
| `GET /api/comprovantes` | Lista os comprovantes vigentes da usuária | 200, 401 |
| `GET /api/comprovantes/{id}` | Metadados de um comprovante | 200, 401, 404 |
| `GET /api/comprovantes/{id}/arquivo` | Imagem (`Cache-Control: private, no-store`, `nosniff`) | 200, 401, 404 |
| `DELETE /api/comprovantes/{id}` | Exclui registro e arquivo | 204, 401, 403, 404 |

## 3. Validação de formato e tamanho

| Regra | Valor padrão | Configuração | Resposta |
|---|---|---|---|
| Formatos aceitos | JPEG, PNG, WebP | fixo | 415 `formato_nao_suportado` |
| Tamanho máximo do arquivo | 5 MB | `COMPROVANTES_TAMANHO_MAXIMO_MB` | 413 `arquivo_grande_demais` |
| Resolução máxima | 40 megapixels | `COMPROVANTES_MAXIMO_PIXELS` (settings) | 400 `imagem_grande_demais` |
| Arquivo vazio | recusado | fixo | 400 `arquivo_vazio` |
| Arquivo corrompido ou truncado | recusado | fixo | 400 `imagem_invalida` |
| Envios por usuária | 30 por hora | `COMPROVANTES_ENVIOS_POR_HORA` | 429 `limite_de_envios` |

O formato é decidido pelo **conteúdo** (assinatura dos primeiros bytes e
leitura com Pillow), nunca pela extensão nem pelo `Content-Type` do
navegador. Um PDF, HTML ou SVG renomeado para `.jpg` é recusado. A imagem é
decodificada por inteiro antes de ser aceita, e a resolução é conferida antes
da decodificação, para barrar "bombas de descompressão".

Arquivo recusado não deixa rastro: nenhum registro no banco e nenhum arquivo
na pasta.

## 4. Isolamento por usuária

- A dona vem de `request.user` (sessão). Campos como `usuaria` ou `usuaria_id`
  no formulário são ignorados.
- Toda consulta filtra por `usuaria` antes de buscar o id
  (`Comprovante.objects.da_usuaria(request.user)`).
- Comprovante de outra pessoa, inexistente ou vencido responde **o mesmo 404**,
  byte a byte. A resposta não revela se o id existe.
- Os ids são UUID, não sequenciais.
- O arquivo não fica em pasta servida diretamente. Ele só sai pela rota
  autenticada da própria dona.

Quando o BE-02 (#84) for mesclado, o modelo passa a herdar de
`RegistroDaUsuaria`, e as rotas passam a usar o autenticador `sessao` daquela
issue. O comportamento não muda, porque `django_auth` e `sessao` são o mesmo
`SessionAuth` do Django Ninja.

## 5. Armazenamento

| Item | Onde | Observação |
|---|---|---|
| Metadados | Tabela `comprovantes_comprovante` (PostgreSQL) | id, usuária, formato, tamanho, largura, altura, sha256, criado_em, expira_em |
| Imagem | `COMPROVANTES_DIR/<id>.<extensão>` | Pasta criada com permissão 0700 e arquivo com 0600; gravação atômica |
| Nome original | **Não é guardado** | Pode conter nome de pessoa, loja ou banco |
| Metadados EXIF | **Removidos** | A imagem é gravada de novo, sem localização, modelo do aparelho ou data; a orientação é aplicada antes |

O `sha256` é calculado sobre a imagem já limpa. Ele servirá para avisar sobre
uma duplicação provável na etapa de prévia.

## 6. Retenção e remoção

| Situação | O que acontece |
|---|---|
| Envio | `expira_em = criado_em + COMPROVANTES_RETENCAO_HORAS` (padrão: **72 horas**) |
| Prazo vencido | O comprovante some das rotas na hora (404), mesmo antes da limpeza |
| Limpeza periódica | `python manage.py limpar_comprovantes` apaga registros vencidos e seus arquivos, e também arquivos órfãos com mais de 1 hora; `--simular` só conta |
| Exclusão pela usuária | `DELETE /api/comprovantes/{id}` apaga registro e arquivo na hora |
| Exclusão da conta | Os comprovantes da usuária são apagados em cascata, com os arquivos |

O prazo de 72 horas cobre o fluxo previsto (enviar, revisar a prévia e
confirmar a despesa). A imagem não é necessária depois da confirmação, porque
a despesa guarda os valores, e não a foto. Na implantação, a limpeza deve
rodar por agendador (por exemplo, `cron` a cada hora):

```cron
0 * * * * cd /srv/grupo11/apps/api && /srv/grupo11/.venv-api/bin/python manage.py limpar_comprovantes
```

## 7. Logs sem conteúdo bruto

O logger `comprovantes` registra só id, id numérico da usuária, formato,
tamanho e o motivo de uma recusa. Nunca registra os bytes da imagem, o nome
original do arquivo, o nome de usuário ou os metadados EXIF.

```text
comprovante recebido id=3f1c…e2 usuaria=7 formato=jpeg tamanho=48213
comprovante recusado usuaria=7 motivo=formato_nao_suportado tamanho=1830
comprovante excluido id=3f1c…e2 usuaria=7
```

Um teste (`LogsSemConteudoTests`) envia uma imagem com EXIF e um PDF com nome
pessoal, e confere que nada disso aparece nos logs.

## 8. Limites conhecidos

- O tamanho é conferido depois que o Django recebe o upload. Na implantação, o
  proxy reverso deve limitar o corpo da requisição (por exemplo,
  `client_max_body_size 6m` no nginx).
- HEIC (padrão do iPhone) não é aceito nesta etapa. A PWA pode converter para
  JPEG antes de enviar, ou o formato entra numa issue futura.
- A extração de campos (OCR) e a prévia editável são as próximas etapas (RF16 e RF17).
