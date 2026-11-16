# Pacote de definição — #62

- [Fonte editável](pacote-definicao.md)
- [PDF para revisão, quatro páginas A4](pacote-definicao.pdf)

A fonte contém quatro seções com quebras explícitas. O gerador usa um subconjunto
de Markdown: títulos, parágrafos e listas simples. Não suporta tabelas ou links
Markdown; referências detalhadas ficam nesta orientação e nos documentos abaixo.

## Referências

- [Cenário e problema](cenario-problema.md), #58.
- [Stakeholders e personas](stakeholders-personas.md), #59.
- [Escopo e requisitos](escopo-requisitos.md), #60.
- [Riscos e métricas / #61](https://github.com/anamattos2/grupo11challenge2/issues/61),
  sintetizado a partir do commit 8e52704, ainda em revisão ao preparar este pacote.
- [Issue #62](https://github.com/anamattos2/grupo11challenge2/issues/62).

O pacote é uma síntese do PRD v1.1 e do cronograma fornecidos na conversa, não
o PRD completo nem evidência de funcionalidades concluídas. Antes do merge,
conferir ajustes e aprovação das dependências #58–61. A #61 ainda pendente impede
tratar esta versão como entrega final revisada.

## Regenerar

Na raiz, com Python 3.12 a 3.14:

```bash
python3 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r docs/definicao/requirements-pdf.txt
.venv-docs/bin/python scripts/gerar_pacote_definicao.py
```

No Windows, substituir `.venv-docs/bin/python` por
`.venv-docs\\Scripts\\python.exe`. O ambiente virtual é local e não deve ser
adicionado ao Git. A primeira instalação requer rede; a geração é local.

Após qualquer edição, regenerar o PDF e revisar as quatro páginas; o gerador
rejeita quantidade diferente. Verificar conteúdo completo, sem cortes,
e registrar a revisão no PR. Fonte e PDF devem ser publicados juntos.

## Critérios de revisão

- Página 1: cenário, público, problema, objetivo e Essential Question.
- Página 2: mapa de relações, stakeholders e três personas fictícias.
- Página 3: requisitos funcionais/não funcionais, arquitetura e exclusões.
- Página 4: riscos, premissas, métricas, marcos e referências.
- Vínculo do PR à #62 e revisão das dependências antes do fechamento.

Não fechar esta issue apenas por gerar o PDF. A versão revisada será a aprovada
e integrada pelo PR; usar `Closes #62` na descrição ao concluir todos os critérios.
