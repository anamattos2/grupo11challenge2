# Política de versionamento e preservação de pesquisa

Referência: [BASE-03 / #57](https://github.com/anamattos2/grupo11challenge2/issues/57).
Fluxo de trabalho: [CONTRIBUTING.md](../../CONTRIBUTING.md).

## O que versionar

| Material | Política |
|---|---|
| Código, configuração de exemplo e manifests | Versionar; configuração de exemplo usa valores fictícios e nenhuma credencial real |
| Documentação, contratos e testes | Versionar junto à implementação ou em PR próprio revisável |
| Fontes educativas | Preservar origem, condições de uso e identidade/hash antes de curar ou consolidar |
| Notebooks | Preservar código e metodologia; revisar saídas antes de publicar |
| Datasets e gabaritos de avaliação | Usar dados públicos permitidos ou fictícios, registrar proveniência e revisão |
| Baselines e relatórios selecionados | Versionar resultados relevantes com modelo, parâmetros, corpus e versão de código |

Resultados não devem receber métricas de sucesso que não foram avaliadas.
Arquivos grandes só devem ser incluídos quando necessários à entrega e com
justificativa. Armazenamento externo ou Git LFS exigem decisão e instruções
de recuperação; links privados indisponíveis à equipe não bastam.

## O que manter local

Ambientes virtuais, node_modules, caches, bytecode, arquivos de sistema,
credenciais, uploads pessoais, bancos locais e índices gerados não devem entrar
como novos artefatos no Git. Configurações reais pertencem ao ambiente local;
o exemplo versionado precisa explicar nomes e valores seguros.

Relatórios completos, imagens e logs podem conter dados pessoais. Sanitizar ou
substituir por dados fictícios antes de publicar evidências. Não enviar o
conteúdo bruto a uma issue ou PR para diagnosticar falhas.

A BASE-02 (#56) adiciona `.gitignore` e `.runtime/` para novos dados gerados.
Enquanto esse PR não estiver integrado, não presuma que os padrões já existem.
Mesmo após a integração, revise a lista preparada para commit: arquivos já
rastreados não passam a ser ignorados por adicionar um padrão.

## Como tratar o legado

Já existem caches, bytecode, bancos Chroma e nomes Unicode equivalentes no
histórico. Não removê-los apenas para fazer o repositório parecer limpo.

Uma migração precisa:

1. Inventariar caminhos e conteúdo antes da mudança.
2. Preservar resultados e fontes únicos; comparar conteúdo, não somente nomes.
3. Registrar o mapa de caminhos antigos para novos e atualizar consumidores.
4. Demonstrar reconstrução dos índices antes de retirá-los do rastreamento.
5. Documentar diferenças esperadas e atualizar o inventário somente com revisão.

O verificador da BASE-02 detecta mudanças no inventário histórico. Uma mudança
legítima futura deve atualizar a referência de forma explícita, preservando
proveniência; não contornar a checagem nem editar o baseline só para deixá-la verde.
As grafias NFC/NFD podem aparecer como um único arquivo no macOS e como paths
distintos em outros sistemas. Sua normalização precisa de tarefa e revisão.

Não reescrever histórico, descartar experimentos ou retirar dados do
rastreamento como efeito colateral de outra tarefa. Usar PR próprio para esse
tipo de migração, com evidências e revisão das frentes afetadas.
