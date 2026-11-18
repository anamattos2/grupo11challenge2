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
em outubro e por que devo ter uma reserva de emergência?".

| Arquivo | Descrição |
|---|---|
| [`ContextoAutorizado.requisicao_chat.json`](exemplos/validos/ContextoAutorizado.requisicao_chat.json) | Contexto montado pelo backend a partir da sessão |
| [`EntradaPesquisa.pergunta_mista.json`](exemplos/validos/EntradaPesquisa.pergunta_mista.json) | Pergunta com parte pessoal e parte educativa |
| [`ChamadaFerramenta.busca_documental.json`](exemplos/validos/ChamadaFerramenta.busca_documental.json) | Busca no corpus educativo |
| [`ChamadaFerramenta.consulta_financeira.json`](exemplos/validos/ChamadaFerramenta.consulta_financeira.json) | Resumo de despesas essenciais de outubro |
| [`SaidaPesquisa.concluida.json`](exemplos/validos/SaidaPesquisa.concluida.json) | Uma evidência financeira e uma documental |
| [`SaidaPesquisa.parcial.json`](exemplos/validos/SaidaPesquisa.parcial.json) | Consulta financeira negada; documento recuperado |
| [`SaidaPesquisa.sem_evidencias.json`](exemplos/validos/SaidaPesquisa.sem_evidencias.json) | Nenhum trecho acima do limiar |
| [`EntradaAnalise.apos_pesquisa.json`](exemplos/validos/EntradaAnalise.apos_pesquisa.json) | Entrada da Analysis com a pesquisa concluída |
| [`SaidaAnalise.analisada.json`](exemplos/validos/SaidaAnalise.analisada.json) | Duas afirmações, cada uma com sua evidência |
| [`SaidaAnalise.dados_insuficientes.json`](exemplos/validos/SaidaAnalise.dados_insuficientes.json) | Falta marcar categorias essenciais |
| [`EntradaValidacao.apos_analise.json`](exemplos/validos/EntradaValidacao.apos_analise.json) | Entrada da Validation |
| [`SaidaValidacao.aprovada.json`](exemplos/validos/SaidaValidacao.aprovada.json) | Todas as regras passaram |
| [`SaidaValidacao.aprovada_com_alertas.json`](exemplos/validos/SaidaValidacao.aprovada_com_alertas.json) | Aprovada, com alerta de fonte sintética |
| [`SaidaValidacao.reprovada.json`](exemplos/validos/SaidaValidacao.reprovada.json) | Número do texto diverge da ferramenta |
| [`EntradaComunicacao.apos_aprovacao.json`](exemplos/validos/EntradaComunicacao.apos_aprovacao.json) | Entrada da Communication |
| [`SaidaComunicacao.resposta_citada.json`](exemplos/validos/SaidaComunicacao.resposta_citada.json) | Resposta com fontes e ligações |
| [`RespostaFinal.respondida.json`](exemplos/validos/RespostaFinal.respondida.json) | Resposta aprovada entregue à PWA |
| [`RespostaFinal.abstencao.json`](exemplos/validos/RespostaFinal.abstencao.json) | Sem evidências: o sistema prefere não responder |
| [`RespostaFinal.pedido_complemento.json`](exemplos/validos/RespostaFinal.pedido_complemento.json) | Pede à usuária o dado que falta |
| [`RespostaFinal.falha.json`](exemplos/validos/RespostaFinal.falha.json) | Tempo esgotado na Analysis |

## Exemplos inválidos

| Arquivo | Por que é recusado | Erro |
|---|---|---|
| [`ContextoAutorizado.permissao_de_escrita.json`](exemplos/invalidos/ContextoAutorizado.permissao_de_escrita.json) | Não existe permissão de escrita para agentes | `enum` |
| [`ContextoAutorizado.memoria_ilimitada.json`](exemplos/invalidos/ContextoAutorizado.memoria_ilimitada.json) | Memória limitada a 5 itens | `too_long` |
| [`ChamadaFerramenta.usuaria_injetada.json`](exemplos/invalidos/ChamadaFerramenta.usuaria_injetada.json) | O planejador tentou escolher a usuária: campo proibido | `extra_forbidden` |
| [`ChamadaFerramenta.operacao_fora_da_lista.json`](exemplos/invalidos/ChamadaFerramenta.operacao_fora_da_lista.json) | Só operações da lista fechada; nada de SQL livre | `enum` |
| [`ChamadaFerramenta.busca_com_operacao.json`](exemplos/invalidos/ChamadaFerramenta.busca_com_operacao.json) | Busca documental não aceita operação financeira | `value_error` |
| [`SaidaPesquisa.evidencia_sem_localizacao.json`](exemplos/invalidos/SaidaPesquisa.evidencia_sem_localizacao.json) | Toda evidência precisa de localização | `missing` |
| [`SaidaPesquisa.valor_como_float.json`](exemplos/invalidos/SaidaPesquisa.valor_como_float.json) | Valor monetário deve ser texto decimal | `string_type` |
| [`SaidaPesquisa.concluida_sem_evidencias.json`](exemplos/invalidos/SaidaPesquisa.concluida_sem_evidencias.json) | `concluida` exige evidência | `value_error` |
| [`SaidaPesquisa.integrado_com_fixture.json`](exemplos/invalidos/SaidaPesquisa.integrado_com_fixture.json) | Modo integrado não pode esconder dado sintético | `value_error` |
| [`SaidaPesquisa.evidencia_sem_chamada.json`](exemplos/invalidos/SaidaPesquisa.evidencia_sem_chamada.json) | Evidência que nenhuma chamada produziu | `value_error` |
| [`SaidaAnalise.afirmacao_sem_evidencia.json`](exemplos/invalidos/SaidaAnalise.afirmacao_sem_evidencia.json) | Toda afirmação precisa de ao menos uma evidência | `too_short` |
| [`SaidaAnalise.afirmacoes_repetidas.json`](exemplos/invalidos/SaidaAnalise.afirmacoes_repetidas.json) | IDs de afirmação únicos | `value_error` |
| [`SaidaValidacao.reprovada_sem_motivo.json`](exemplos/invalidos/SaidaValidacao.reprovada_sem_motivo.json) | Reprovação exige motivo de bloqueio | `value_error` |
| [`SaidaValidacao.aprovada_com_falha.json`](exemplos/invalidos/SaidaValidacao.aprovada_com_falha.json) | Não se aprova com verificação em falha | `value_error` |
| [`EntradaComunicacao.recebe_reprovada.json`](exemplos/invalidos/EntradaComunicacao.recebe_reprovada.json) | Communication nunca recebe conteúdo reprovado | `value_error` |
| [`SaidaComunicacao.ligacao_sem_fonte.json`](exemplos/invalidos/SaidaComunicacao.ligacao_sem_fonte.json) | Evidência usada na ligação precisa estar em `fontes` | `value_error` |
| [`RespostaFinal.abstencao_com_fontes.json`](exemplos/invalidos/RespostaFinal.abstencao_com_fontes.json) | Só resposta aprovada cita fontes | `value_error` |
| [`RespostaFinal.respondida_sem_fontes.json`](exemplos/invalidos/RespostaFinal.respondida_sem_fontes.json) | Resposta sem fonte não pode sair como respondida | `value_error` |
