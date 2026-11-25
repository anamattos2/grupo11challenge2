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
| `numeros_conferem` | Número ausente das evidências citadas; valor atribuído ao campo errado | |
| `suporte_documental` | Orientação com cobertura < 0,5 no trecho citado ou com a negação invertida | Cobertura < 0,75 ou score < 0,85 |
| `escopo_permitido` | Ativo específico, acesso bancário, ação de escrita (exceto quando negados), evidência sem permissão no contexto | |

- **Números:** os números aceitos vêm dos valores, do resumo e do período das
  evidências financeiras e do trecho das documentais. A comparação é canônica,
  então `R$ 1.850,40` confere com `1850.40`. Os números da pergunta só valem em
  orientação educativa: em dado pessoal ou cálculo, um valor que só a pergunta
  traz ("gastei R$ 3.000?") nunca é confirmado como registro da usuária.
- **Campo de cada valor:** quando o texto liga um valor a um campo ("R$ 0,00 de
  receitas", "o resultado do mês foi R$ ..."), o valor precisa ser o desse campo
  nas evidências citadas. Trocar receitas por despesas reprova, mesmo com os dois
  números presentes na evidência. Números sem campo nomeado, datas e
  percentuais ficam só com a checagem anterior.
- **Cobertura:** é a fração das palavras de conteúdo da afirmação (sem acento,
  sem palavras funcionais, com corte simples de plural) que aparecem no trecho
  ([`texto.py`](../../../packages/ai/src/finance_ai/agents/texto.py)).
- **Negação:** a cobertura ignora "não", "nunca", "nem" e "jamais". Por isso a
  polaridade é conferida à parte: uma palavra negada na afirmação e só afirmada
  no trecho (ou o contrário) reprova por `sem_suporte`. A mesma regra deixa
  passar orientações de segurança na checagem de escopo ("nunca compartilhe sua
  senha", "não recomendo comprar ações").
- **Contexto não autorizado:** uma afirmação que cita evidência `fin:` sem
  `financeiro:ler` no `ContextoAutorizado` (ou `doc:` sem `documentos:ler`) é
  reprovada por `fora_do_escopo`.
- **Decisão:** qualquer falha reprova. As afirmações bloqueadas vão para
  `alegacoes_sem_suporte`, e o `feedback` diz, por afirmação, o que corrigir.
  O motivo de bloqueio segue a gravidade: referência inexistente, fora do
  escopo, número divergente, sem suporte. Sem falha, todas as afirmações são
  aprovadas, com `aprovada_com_alertas` se houver alerta.

**Limite conhecido:** a cobertura mede palavras e a polaridade delas, não
significado. Uma inversão sem negação explícita ("serve" x "não é indicada" com
outras palavras) ainda pode passar. Uma paráfrase
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
     nova sem números;
  4. nenhuma palavra das afirmações aparecer com a polaridade trocada
     ("você registrou" virando "você não registrou").

  Em qualquer outro caso, inclusive exceção do redator, a Communication usa o
  modelo, com o texto literal das afirmações aprovadas, e o motivo fica em
  `ultimo_descarte`.
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
reprovação corrigida na revisão, reprovação repetida virando abstenção sem
repetir o número bloqueado e redator que inverte o sentido descartado antes da
resposta final. Os casos da revisão do PR (valores trocados entre campos,
orientação negada, número vindo da pergunta e negações na checagem de escopo)
têm testes de regressão.

```bash
python -m unittest tests.test_validation_communication
```
