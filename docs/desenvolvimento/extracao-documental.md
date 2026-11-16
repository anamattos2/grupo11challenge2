# Extração e limpeza documental — #64

O módulo `finance_ai.extraction` extrai texto local de PDFs preservando ID do
documento, SHA-256 e número físico de página (começando em 1). Reaproveita do
experimento `RAG/projeto-rag/teste_extracao.py` a escolha de PyMuPDF, acrescentando
percurso de todas as páginas, relatório de falhas, limpeza e testes. O experimento
original permanece intacto.

## Instalar e executar

Na raiz, com o ambiente virtual do projeto ativo:

```bash
python -m pip install --editable './packages/ai[documents]'
python -m finance_ai.extraction /caminho/para/exemplo-sintetico.pdf --document-id SYN001
python -m unittest discover -s tests
```

O caminho é um exemplo: substitua por um PDF sintético existente. O módulo imprime
JSON na saída padrão e não grava arquivos nem altera o PDF. Para guardar uma
execução de revisão, use um nome novo sob `.runtime/` (ignorado pelo Git).

`--expected-sha256 HASH` permite comparar a identidade com o catálogo antes da
extração; divergência interrompe a operação. O ID é obrigatório e deve corresponder
ao registro da fonte quando utilizado com o catálogo. O módulo não modifica nem
aprova esse registro. As fontes da #63 continuam aguardando liberação: esta entrega
usa somente PDFs fictícios em testes e não executa ingestão do corpus real.

## Contrato do relatório

- `document_id`, `source_path` e `source_sha256`: identidade e procedência local.
- `extractor` e `cleaning_version`: versões usadas para reproduzir o resultado.
- `page_count`: total físico; `null` quando não foi possível abrir o documento.
- `pages`: uma entrada por página, inclusive vazia ou com falha. Cada entrada
  repete ID e hash e contém `page_number`, `raw_text`, `text` e `status`.
- `issues`: códigos de ocorrência, número de página quando aplicável e tipo de
  exceção em falhas. Mensagens internas das exceções não são copiadas ao relatório.

As páginas têm status `ok`, `empty` ou `error`. O documento recebe `ok` quando
todas as páginas têm texto, `partial` quando alguma página está vazia/falhou e
`error` quando a leitura ou abertura é impedida. Uma falha de página não elimina
as demais páginas do resultado. Códigos de saída: **0** para `ok`, **2** para
`partial` e **1** para `error`; automações devem tratar explicitamente o código 2.

Ocorrências previstas: `read_failed`, `hash_mismatch`, `not_pdf`, `open_failed`,
`password_required`, `no_pages`, `no_text` e `page_failed`. PDFs protegidos não são
desbloqueados. A identificação considera os bytes, permitindo PDFs sem extensão.

## Limpeza e limites

A limpeza normaliza Unicode para NFC, quebras CR/LF, espaços horizontais e linhas
vazias repetidas; remove controles e caracteres de formatação invisíveis. Preserva
acentos, valores monetários, sinais, números e separação entre páginas. O texto
bruto fica disponível para comparação. Não remove cabeçalhos/rodapés nem tenta
recompor palavras hifenizadas, tabelas ou parágrafos de modo heurístico.

A ordenação usa `get_text('text', sort=True)` do PyMuPDF. Não garante leitura
semântica de múltiplas colunas ou tabelas. Páginas digitalizadas sem camada textual
são reportadas como `no_text`; isso não determina se estão em branco ou precisam
de OCR. Chunking, embeddings, OCR e validação de conteúdo pertencem às próximas
etapas. O arquivo é lido integralmente em memória; este módulo é uma ferramenta
local, não um endpoint de upload.

## Evidências e critérios de aceite

Os testes geram PDFs fictícios em diretório temporário e os removem ao terminar.
Verificam ID/hash/página, preservação do PDF, acentos e valores após limpeza,
página vazia, PDF corrompido ou ausente, senha, hash divergente, falha isolada de
página e contrato da CLI. A CI instala o extra em ambiente separado da instalação
básica e executa os testes; não baixa modelos nem processa documentos reais.

Validação local em 16/11/2026, com Python 3.14.6 e ambiente virtual novo:
instalação editável com `documents` concluída, `pip check` sem dependências
quebradas e 13 testes aprovados (oito de extração e cinco do catálogo). Os
verificadores confirmaram o catálogo e os 70 arquivos históricos preservados.
A execução da CI no GitHub ainda depende da publicação do PR.

Referências primárias de implementação:
[Page.get_text](https://pymupdf.readthedocs.io/en/latest/page.html#Page.get_text) e
[Document](https://pymupdf.readthedocs.io/en/latest/document.html).
