# Como contribuir

Este guia define o fluxo de trabalho do Grupo 11. Referência:
[BASE-03 / #57](https://github.com/anamattos2/grupo11challenge2/issues/57).
Consulte também a [arquitetura](docs/arquitetura/arquitetura-inicial.md).

## 1. Preparar uma tarefa

1. Escolha uma issue, confira objetivo, critérios de aceite e dependências.
2. Defina responsável e revisor. A revisão deve ser feita por outro integrante
   com acesso de escrita, respeitando as regras de proteção da main.
3. Coloque a tarefa em andamento no Projects. O quadro não altera o estado da
   issue automaticamente, salvo quando houver automação configurada.
4. Divida mudanças grandes em PRs menores e documente o que cada PR entrega.

Os experimentos existentes são referências; uma tarefa só está concluída após
a revisão de suas evidências. Não é necessário recriar issues já cadastradas.

## 2. Conferir identidade e criar a branch

Execute na raiz do repositório e confira se há trabalho local:

```bash
git status --short --branch
git config --get user.name
git config --get user.email
```

Se necessário, configure nome e um e-mail associado à sua conta GitHub somente
neste repositório. Substitua os exemplos antes de executar:

```bash
git config --local user.name "Seu nome"
git config --local user.email "SEU_EMAIL_CADASTRADO_NO_GITHUB"
```

O e-mail privado noreply fornecido nas configurações do GitHub também pode ser
usado. A identidade do commit e a conta autenticada no push são independentes:
confira ambas. Não publique tokens ou senhas para demonstrar autenticação.

Com a árvore limpa, atualize a main e abra uma branch de tarefa:

```bash
git switch main
git pull --ff-only origin main
git switch -c chore-57-colaboracao-revisao-ci
```

O último comando é um exemplo: use número e assunto da sua issue e não recrie
uma branch que já existe. Se houver alterações locais ou o pull falhar, preserve
seu trabalho e investigue antes de mudar de branch; não use reset ou limpeza
forçada para resolver o problema.

Use nomes como `docs-55-arquitetura-inicial`, `feat-80-login` ou
`fix-90-validacao-upload`: tipo, número da issue e descrição curta em minúsculas,
sem espaços ou acentos. Preferimos hífens a barras, pois já existe uma branch
remota chamada `docs`, que conflita com nomes como `docs/55-arquitetura`.

## 3. Desenvolver e conferir

- Mantenha cada PR focado em uma entrega revisável.
- Alinhe alterações de contrato com quem produz e consome a interface.
- Execute verificações proporcionais ao impacto. Mudanças financeiras exigem
  testes de cálculo e isolamento; documentação exige links e exemplos válidos.
- Confira diffs e siga a [política de versionamento](docs/desenvolvimento/versionamento.md).
- Preserve os notebooks, fontes e resultados de pesquisa durante reorganizações.

Comandos de revisão local que não abrem o visualizador interativo:

```bash
git --no-pager diff --stat
git --no-pager diff
git diff --check
```

A CI da main valida sintaxe de arquivos Python e estrutura JSON dos notebooks,
sem executar experimentos. Não instala bibliotecas de IA nem confirma qualidade
de respostas, testes financeiros ou funcionamento da aplicação. A BASE-02 (#56)
adiciona instalação do pacote e preservação do legado em PR próprio; consulte o
workflow efetivamente integrado antes de assumir que essas verificações existem.

## 4. Fazer commit e publicar a branch

Adicione somente os arquivos da tarefa com `git add caminho/do/arquivo`.
Revise o conteúdo preparado antes de confirmar:

```bash
git --no-pager diff --cached --stat
git --no-pager diff --cached
git diff --cached --check
git status --short
```

Use mensagens no formato `tipo: mudança concreta`. Tipos sugeridos:
`docs`, `feat`, `fix`, `test`, `refactor`, `ci` e `chore`.
O commit deve descrever o resultado, sem reunir tarefas independentes.

Exemplo para a #57, após revisar os arquivos:

```bash
git commit -m "docs: definir colaboracao e revisao da equipe"
git push -u origin chore-57-colaboracao-revisao-ci
```

Um commit é local; o push publica a branch; o PR propõe sua integração.
Nenhuma dessas operações equivale a aprovar ou integrar o PR.

## 5. Abrir e revisar o pull request

Abra o PR com base `main` e compare a branch da tarefa. Use o modelo de PR,
explique resultado e validação e vincule a issue:

- `Closes #57` se esse PR conclui todos os critérios da issue após revisão.
- `Refs #57` se a entrega é parcial; mantenha a issue aberta.

Revise a aba Files changed, solicite revisão e acompanhe a CI. O modelo não
substitui conferir se o vínculo à issue aparece no PR.

O revisor deve conferir critérios de aceite, contratos afetados, testes ou
evidências, dados pessoais e preservação de pesquisa. Se estiver de acordo,
usar **Files changed → Review changes → Approve → Submit review**. Um comentário
como “Revisado” não registra aprovação. Caso haja problemas, descreva correções
ou use Request changes. Aprovar depende da análise do conteúdo, não do checklist
preenchido pelo autor.

Após novo push, confira se há necessidade de nova aprovação. A proteção da main
pode exigir aprovação de alguém diferente de quem fez o último push.
Não desative a proteção para integrar uma tarefa.

## 6. Definição de pronto

Uma issue só pode ser concluída quando:

- [ ] Todos os seus critérios de aceite têm evidências verificáveis.
- [ ] Implementação e documentação descrevem o comportamento entregue.
- [ ] Verificações pertinentes passaram; limitações estão registradas.
- [ ] Nenhum segredo ou dado pessoal real entrou em arquivos ou evidências.
- [ ] Contratos e consumidores afetados foram conferidos.
- [ ] Fontes, experimentos e resultados foram preservados ou migrados com mapa.
- [ ] Outra pessoa revisou e aprovou o PR; checks exigidos estão verdes.
- [ ] O PR foi integrado à main e a issue/Projects refletem o resultado.

A aprovação do PR não faz merge automaticamente. Quem integra deve conferir
novamente o estado do PR e usar a opção de merge permitida pelo repositório.
Após integração, confirme o fechamento da issue e mova o item para concluído
se não houver automação configurada. Atualize sua main com `git pull --ff-only`
antes de iniciar a próxima tarefa.

## 7. Proteções e CI

A configuração de proteção é administrada no GitHub, fora dos arquivos deste PR.
Recomenda-se exigir PR, pelo menos uma aprovação de outra pessoa e o check
`CI / python-and-notebooks` depois de confirmar que ele está disponível nas
regras. O nome do job existente é preservado para evitar quebrar checks exigidos.

Não afirme que a proteção está ativa apenas porque o guia existe. Confira a
regra aplicada à main. Requisitos de testes adicionais devem acompanhar as
funcionalidades, sem substituir a revisão humana por validação de sintaxe.
