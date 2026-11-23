# Validation e Communication

Implementação da S4-04 ([#78](https://github.com/anamattos2/grupo11challenge2/issues/78))
e da S4-05 ([#79](https://github.com/anamattos2/grupo11challenge2/issues/79)) sobre os
[contratos dos agentes](contratos-agentes.md).

| Agente | Módulo | Chamável para `Agentes` |
|---|---|---|
| Validation | [`validation.py`](../../../packages/ai/src/finance_ai/agents/validation.py) | `ValidationAgent()` |
| Communication | [`communication.py`](../../../packages/ai/src/finance_ai/agents/communication.py) | `CommunicationAgent(redator=None)` |

Os dois são determinísticos por padrão. Nenhum vê `usuaria_ref` nem chama
ferramenta: recebem só o que o orquestrador passa pelos contratos.

## Validation

Cada afirmação passa pelas cinco regras de `RegraValidacao`. Cada checagem vira
uma `Verificacao` com `ok`, `alerta` ou `falha`.

| Regra | Falha (reprova) | Alerta (não bloqueia) |
|---|---|---|
| `referencias_existentes` | Evidência citada fora da pesquisa | Fonte sintética; pesquisa `parcial` |
| `natureza_compativel` | Dado pessoal ou cálculo sem `fin:`; orientação sem `doc:` | |
| `numeros_conferem` | Número da afirmação ausente das evidências citadas e da pergunta | |
| `suporte_documental` | Orientação com cobertura < 0,5 no trecho citado | Cobertura < 0,75 ou score < 0,85 |
| `escopo_permitido` | Ativo específico, acesso bancário, ação de escrita, evidência sem permissão no contexto | |

- **Números:** os números aceitos vêm dos valores, do resumo e do período das
  evidências financeiras, do trecho das documentais e da pergunta. A comparação
  é canônica, então `R$ 1.850,40` confere com `1850.40`.
- **Cobertura:** é a fração das palavras de conteúdo da afirmação (sem acento,
  sem palavras funcionais, com corte simples de plural) que aparecem no trecho
  ([`texto.py`](../../../packages/ai/src/finance_ai/agents/texto.py)).
- **Contexto não autorizado:** uma afirmação que cita evidência `fin:` sem
  `financeiro:ler` no `ContextoAutorizado` (ou `doc:` sem `documentos:ler`) é
  reprovada por `fora_do_escopo`.
- **Decisão:** qualquer falha reprova. As afirmações bloqueadas vão para
  `alegacoes_sem_suporte`, e o `feedback` diz, por afirmação, o que corrigir.
  O motivo de bloqueio segue a gravidade: referência inexistente, fora do
  escopo, número divergente, sem suporte. Sem falha, todas as afirmações são
  aprovadas, com `aprovada_com_alertas` se houver alerta.

**Limite conhecido:** a cobertura mede palavras, não significado. Uma paráfrase
fiel com outras palavras pode ser reprovada; nesse caso, o feedback leva a
Analysis a ficar mais perto do trecho na revisão. Avaliar pertinência de verdade
continua sendo revisão humana.

## Communication

- **Modelo (padrão):** agrupa as afirmações aprovadas em parágrafos de até 5
  afirmações e 800 caracteres. Os dados da usuária e os cálculos vêm antes das
  orientações, e o texto é o da própria afirmação.
- **Redator opcional:** `CommunicationAgent(redator=f)` aceita qualquer
  `f(prompt) -> str` (por exemplo, um LLM local) que devolva
  `{"paragrafos": [...]}`. O prompt leva só a pergunta e as afirmações
  aprovadas, sem evidências, contexto ou alegações bloqueadas. A redação só é
  usada se:
  1. o contrato `SaidaComunicacao` for válido;
  2. passar em `fluxo.inconsistencias_comunicacao` (só afirmações aprovadas,
     todas presentes e nenhum número novo);
  3. cada parágrafo tiver no máximo 40% de palavras de conteúdo fora das
     afirmações que declara. É a checagem própria do texto que pega uma frase
     nova sem números.

  Em qualquer outro caso, inclusive exceção do redator, a Communication usa o
  modelo, e o motivo fica em `ultimo_descarte`.
- **Limites:** sempre explicam o suporte (números entre colchetes). Conforme as
  evidências usadas, também mostram o aviso de valores declarados, o caráter
  educativo, os dados de demonstração, a pesquisa parcial e o suporte parcial
  apontado pela Validation.
- **Reprovação:** `EntradaComunicacao` recusa conteúdo reprovado. O orquestrador
  responde com `resposta_segura`, um texto fixo que não repete nenhuma alegação
  bloqueada (há teste de ponta a ponta no grafo).

## Testes

`tests/test_validation_communication.py` cobre cada regra (falha e alerta), a
prioridade do motivo, os limites, o redator aceito e cada motivo de descarte,
além do grafo com Validation e Communication reais: resposta redigida,
reprovação corrigida na revisão e reprovação repetida virando abstenção sem
repetir o número bloqueado.

```bash
python -m unittest tests.test_validation_communication
```
