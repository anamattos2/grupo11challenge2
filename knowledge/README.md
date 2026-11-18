# Conhecimento educativo

O [catálogo](catalogo.json), preparado na issue #63, registra 24 conteúdos únicos:
20 PDFs identificados, três PDFs com procedência pendente e uma planilha auxiliar.
São 39 caminhos preservados. Identificação bibliográfica não significa licença
para ingestão, nem validação científica de todas as afirmações do documento.

## Critérios e rastreabilidade

Cada registro possui ID estável, título, autoria quando identificada, origem,
SHA-256, tamanho, formato, páginas, caminho de referência, aliases e condições de
uso. Ano desconhecido permanece `null`: data de download, nome do arquivo e
metadados do programa exportador não comprovam data de publicação.

A conferência bibliográfica usa capa/expediente dos PDFs locais. URLs são
referências de origem; não implicam comparação binária com uma versão remota.
F015 corresponde à página pública da Serasa; a data da captura local é desconhecida.
F024 foi obtido diretamente da SUSEP em 16/11/2026. Nenhum dado financeiro de
usuárias ou comprovante pessoal deve entrar neste corpus.

Duplicidades foram agrupadas por SHA-256, preservando todos os nomes no catálogo.
Há sete pares de caminhos com variações Unicode NFC/NFD, além de cópias entre
`fontes/` e `RAG/projeto-rag/docs/`. O PDF F023 não tem extensão no arquivo
histórico; sua assinatura é PDF. Não renomeamos, movemos ou excluímos os originais.
O caminho canônico é uma referência, não uma migração física.

## Seleção e limites

O acervo cobre orçamento, fluxo de caixa, planejamento, comportamento financeiro,
contexto de gênero e usabilidade de aplicativos. Estudos com estudantes ou
profissionais contábeis são referências indiretas: não comprovam resultados para
mulheres em início de carreira. F024 complementa a discussão conceitual de risco
e proteção financeira; sua edição de 2006 exige revisão de atualidade e não deve
fundamentar regras, produtos ou recomendações atuais.

F006, F007 e F014 ficam fora do mínimo de 20 PDFs identificados: são exportações
sem procedência suficientemente confirmada. A grafia “Susesp” de F007 foi
preservada; não atribuímos esse documento à SUSEP. F011 é uma planilha auxiliar e
também não entra na contagem. Alegações e estatísticas exigem avaliação posterior.

A aprovação cobre páginas físicas específicas. Registre evidência de uso,
páginas revisadas e citação em `ingestion_review`, e marque
`approved_for_ingestion: true` no registro da fonte. A citação acompanha os
chunks no índice e deve aparecer junto de trechos exibidos ao público.

O primeiro lote cobre F001 (páginas 20 e 21) e F018 (páginas 4 a 6) para
fundamentos de orçamento e planejamento. F018 é um estudo com estudantes e
seus resultados não representam o público-alvo do aplicativo. A página de
contatos fica fora da seleção. F024 permanece pendente de atualização do
conteúdo. F005 e F017 têm condições específicas que ainda precisam ser
verificadas para o uso proposto. Os registros sem licença ou autorização
confirmada seguem pendentes.

## Verificar

Na raiz do repositório, sem dependências adicionais:

```bash
python3 scripts/verificar_catalogo.py
python3 -m unittest discover -s tests -p 'test_catalogo.py'
python3 scripts/verificar_legado.py
```

O verificador exige 20 PDFs identificados, detecta conteúdo alterado, IDs/hashes
repetidos, aliases inválidos e fontes históricas omitidas. Lê também os blobs do
índice Git para preservar as diferenças Unicode em sistemas que as normalizam.
Novas fontes são conferidas pelo arquivo local antes do primeiro `git add`.
A contagem valida integridade e completude do catálogo; a pertinência bibliográfica
e as condições de uso precisam de revisão humana no PR.
