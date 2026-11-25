# Contratos dos agentes

Referência: [S4-01 / #75](https://github.com/anamattos2/grupo11challenge2/issues/75).
Explicação dos papéis e do fluxo: [contratos-agentes.md](../../docs/arquitetura/agentes/contratos-agentes.md).

- `schemas/`: JSON Schema (draft 2020-12), **gerados** a partir de
  `packages/ai/src/finance_ai/agents/contratos.py`. Não edite à mão; rode
  `python scripts/exportar_schemas_agentes.py`.
- `exemplos/validos/` e `exemplos/invalidos/`: casos fictícios usados nos testes.
- `fluxo.mmd`: diagrama Mermaid gerado pelo LangGraph a partir de `grafo.py`.

Cada exemplo é um envelope:

```jsonc
{
  "schema": "SaidaPesquisa",
  "caso": "concluida",
  "descricao": "...",          // em exemplos inválidos: "motivo" e "erro_esperado"
  "documento": { ... }          // o payload que é validado contra o schema
}
```

`erro_esperado` é o tipo de erro do Pydantic que a recusa precisa conter
(`extra_forbidden`, `enum`, `missing`, `value_error`...). O teste confere que
o exemplo falha **por esse motivo**, e não por um erro acidental.

Para validar um payload no Python:

```python
from finance_ai.agents.contratos import SaidaPesquisa
SaidaPesquisa.model_validate_json(texto)
```

## Exemplos válidos

Um único caso fictício atravessa o fluxo: "Quanto gastei com despesas essenciais
em outubro e por que devo ter uma reserva de emergência?". A `RespostaFinal`
de exemplo é gerada pela própria `fluxo.montar_resposta`.

| Arquivo | Descrição |
|---|---|
| [`ChamadaFerramenta.busca_documental.json`](exemplos/validos/ChamadaFerramenta.busca_documental.json) | Busca no corpus educativo. |
| [`ChamadaFerramenta.consulta_financeira.json`](exemplos/validos/ChamadaFerramenta.consulta_financeira.json) | Resumo de despesas essenciais de outubro. |
| [`ContextoAutorizado.requisicao_chat.json`](exemplos/validos/ContextoAutorizado.requisicao_chat.json) | Contexto montado pelo backend a partir da sessão. |
| [`EntradaAnalise.apos_pesquisa.json`](exemplos/validos/EntradaAnalise.apos_pesquisa.json) | Entrada da Analysis com a pesquisa concluída. |
| [`EntradaComunicacao.apos_aprovacao.json`](exemplos/validos/EntradaComunicacao.apos_aprovacao.json) | Entrada da Communication. |
| [`EntradaPesquisa.calculo_solicitado.json`](exemplos/validos/EntradaPesquisa.calculo_solicitado.json) | Research executa o cálculo pedido pela Analysis, sem planejar. |
| [`EntradaPesquisa.pergunta_mista.json`](exemplos/validos/EntradaPesquisa.pergunta_mista.json) | Pergunta com parte pessoal e parte educativa. |
| [`EntradaValidacao.apos_analise.json`](exemplos/validos/EntradaValidacao.apos_analise.json) | Entrada da Validation. |
| [`RespostaFinal.abstencao.json`](exemplos/validos/RespostaFinal.abstencao.json) | Sem evidências: o sistema prefere não responder. |
| [`RespostaFinal.falha.json`](exemplos/validos/RespostaFinal.falha.json) | Tempo esgotado na Analysis. |
| [`RespostaFinal.pedido_complemento.json`](exemplos/validos/RespostaFinal.pedido_complemento.json) | Pede à usuária o dado que falta. |
| [`RespostaFinal.respondida.json`](exemplos/validos/RespostaFinal.respondida.json) | Texto, citações, fontes e ligações montados pelo orquestrador. |
| [`RespostaFinal.respondida_literal.json`](exemplos/validos/RespostaFinal.respondida_literal.json) | Redação trouxe número inexistente; saiu o texto literal das afirmações. |
| [`SaidaAnalise.analisada.json`](exemplos/validos/SaidaAnalise.analisada.json) | Duas afirmações, cada uma com sua evidência. |
| [`SaidaAnalise.dados_insuficientes.json`](exemplos/validos/SaidaAnalise.dados_insuficientes.json) | Falta marcar categorias essenciais. |
| [`SaidaAnalise.precisa_calculo.json`](exemplos/validos/SaidaAnalise.precisa_calculo.json) | Analysis pede ao backend o total de setembro. |
| [`SaidaComunicacao.paragrafos.json`](exemplos/validos/SaidaComunicacao.paragrafos.json) | Parágrafos ligados a afirmações aprovadas; sem fontes próprias. |
| [`SaidaPesquisa.concluida.json`](exemplos/validos/SaidaPesquisa.concluida.json) | Uma evidência financeira e uma documental. |
| [`SaidaPesquisa.falha.json`](exemplos/validos/SaidaPesquisa.falha.json) | Ferramenta com erro e nada recuperado: falha, nunca 'não encontrei'. |
| [`SaidaPesquisa.parcial.json`](exemplos/validos/SaidaPesquisa.parcial.json) | Consulta financeira negada; documento recuperado. |
| [`SaidaPesquisa.sem_evidencias.json`](exemplos/validos/SaidaPesquisa.sem_evidencias.json) | Busca respondeu sem resultados: busca vazia de fato. |
| [`SaidaPesquisa.sem_permissao.json`](exemplos/validos/SaidaPesquisa.sem_permissao.json) | Todas as chamadas negadas: diferente de busca vazia. |
| [`SaidaValidacao.aprovada.json`](exemplos/validos/SaidaValidacao.aprovada.json) | Todas as regras passaram. |
| [`SaidaValidacao.aprovada_com_alertas.json`](exemplos/validos/SaidaValidacao.aprovada_com_alertas.json) | Aprovada, com alerta de fonte sintética. |
| [`SaidaValidacao.reprovada.json`](exemplos/validos/SaidaValidacao.reprovada.json) | Número do texto diverge da ferramenta. |

## Exemplos inválidos

| Arquivo | Por que é recusado | Erro |
|---|---|---|
| [`ChamadaFerramenta.busca_com_operacao.json`](exemplos/invalidos/ChamadaFerramenta.busca_com_operacao.json) | Busca documental não aceita operação financeira. | `value_error` |
| [`ChamadaFerramenta.operacao_fora_da_lista.json`](exemplos/invalidos/ChamadaFerramenta.operacao_fora_da_lista.json) | Só operações da lista fechada; nada de SQL livre. | `enum` |
| [`ChamadaFerramenta.usuaria_injetada.json`](exemplos/invalidos/ChamadaFerramenta.usuaria_injetada.json) | O planejador tentou escolher a usuária: campo proibido. | `extra_forbidden` |
| [`ContextoAutorizado.memoria_ilimitada.json`](exemplos/invalidos/ContextoAutorizado.memoria_ilimitada.json) | Memória limitada a 5 itens. | `too_long` |
| [`ContextoAutorizado.permissao_de_escrita.json`](exemplos/invalidos/ContextoAutorizado.permissao_de_escrita.json) | Não existe permissão de escrita para agentes. | `enum` |
| [`EntradaComunicacao.recebe_reprovada.json`](exemplos/invalidos/EntradaComunicacao.recebe_reprovada.json) | Communication nunca recebe conteúdo reprovado. | `value_error` |
| [`EntradaPesquisa.solicitada_sem_pedido.json`](exemplos/invalidos/EntradaPesquisa.solicitada_sem_pedido.json) | Chamada solicitada precisa do pedido_id que atende. | `value_error` |
| [`RespostaFinal.abstencao_com_fontes.json`](exemplos/invalidos/RespostaFinal.abstencao_com_fontes.json) | Só resposta aprovada cita fontes. | `value_error` |
| [`RespostaFinal.respondida_sem_fontes.json`](exemplos/invalidos/RespostaFinal.respondida_sem_fontes.json) | Resposta sem fonte não pode sair como respondida. | `value_error` |
| [`RespostaFinal.respondida_sem_ligacoes.json`](exemplos/invalidos/RespostaFinal.respondida_sem_ligacoes.json) | Resposta aprovada mostra qual evidência sustenta cada afirmação. | `value_error` |
| [`SaidaAnalise.afirmacao_sem_evidencia.json`](exemplos/invalidos/SaidaAnalise.afirmacao_sem_evidencia.json) | Toda afirmação precisa de ao menos uma evidência. | `too_short` |
| [`SaidaAnalise.afirmacoes_repetidas.json`](exemplos/invalidos/SaidaAnalise.afirmacoes_repetidas.json) | IDs de afirmação únicos. | `value_error` |
| [`SaidaAnalise.precisa_calculo_sem_pedido.json`](exemplos/invalidos/SaidaAnalise.precisa_calculo_sem_pedido.json) | 'precisa_calculo' exige pedidos. | `value_error` |
| [`SaidaComunicacao.fontes_pela_communication.json`](exemplos/invalidos/SaidaComunicacao.fontes_pela_communication.json) | Fontes e ligações são montadas pelo orquestrador. | `extra_forbidden` |
| [`SaidaComunicacao.paragrafo_sem_afirmacao.json`](exemplos/invalidos/SaidaComunicacao.paragrafo_sem_afirmacao.json) | Todo parágrafo declara as afirmações que expressa. | `too_short` |
| [`SaidaPesquisa.concluida_sem_evidencias.json`](exemplos/invalidos/SaidaPesquisa.concluida_sem_evidencias.json) | 'concluida' exige evidência. | `value_error` |
| [`SaidaPesquisa.evidencia_sem_chamada.json`](exemplos/invalidos/SaidaPesquisa.evidencia_sem_chamada.json) | Evidência que nenhuma chamada produziu. | `value_error` |
| [`SaidaPesquisa.evidencia_sem_localizacao.json`](exemplos/invalidos/SaidaPesquisa.evidencia_sem_localizacao.json) | Toda evidência precisa de localização. | `missing` |
| [`SaidaPesquisa.integrado_com_fixture.json`](exemplos/invalidos/SaidaPesquisa.integrado_com_fixture.json) | Modo integrado não pode esconder dado sintético. | `value_error` |
| [`SaidaPesquisa.sem_chamadas.json`](exemplos/invalidos/SaidaPesquisa.sem_chamadas.json) | Toda pesquisa registra ao menos uma chamada. | `too_short` |
| [`SaidaPesquisa.sem_evidencias_com_erro.json`](exemplos/invalidos/SaidaPesquisa.sem_evidencias_com_erro.json) | Erro de ferramenta não pode virar busca vazia. | `value_error` |
| [`SaidaPesquisa.sem_evidencias_tudo_negado.json`](exemplos/invalidos/SaidaPesquisa.sem_evidencias_tudo_negado.json) | Tudo negado é falta de permissão, não busca vazia. | `value_error` |
| [`SaidaPesquisa.valor_como_float.json`](exemplos/invalidos/SaidaPesquisa.valor_como_float.json) | Valor monetário deve ser texto decimal. | `string_type` |
| [`SaidaValidacao.aprovada_com_falha.json`](exemplos/invalidos/SaidaValidacao.aprovada_com_falha.json) | Não se aprova com verificação em falha. | `value_error` |
| [`SaidaValidacao.reprovada_sem_motivo.json`](exemplos/invalidos/SaidaValidacao.reprovada_sem_motivo.json) | Reprovação exige motivo de bloqueio. | `value_error` |
