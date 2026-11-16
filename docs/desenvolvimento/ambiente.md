# Monorepositório e ambiente inicial

Referência: [BASE-02 / #56](https://github.com/anamattos2/grupo11challenge2/issues/56).
Arquitetura: [BASE-01](../arquitetura/arquitetura-inicial.md).

[Evidências locais de verificação](evidencias-base-02.md).

## Escopo executável desta etapa

O comando `finance-ai` verifica que o pacote de IA está instalado. Ele informa
`estrutura_inicial` e uma lista vazia de componentes implementados. Não inicia
servidores, não importa o RAG antigo, não consulta bancos e não baixa modelos.

Frontend React/PWA, Django/PostgreSQL, RAG, OCR e agentes serão implementados
nas respectivas issues. Não existe um comando de execução completa da aplicação
nesta etapa. A preparação reproduzível aqui é a base Python do monorepositório.

## Pré-requisitos e dependências

- Python 3.12 a 3.14, com `venv` e `pip` (CI usa Python 3.12).
- Git para obter o repositório e verificar preservação dos experimentos.
- Acesso ao índice de pacotes Python na primeira instalação: o build utiliza
  `setuptools==80.9.0`, fixado em `packages/ai/pyproject.toml`.
- Nenhuma dependência de execução de terceiros, chave de API, Docker, Node,
  PostgreSQL ou Ollama é necessária para a verificação inicial.

Dependências do produto serão declaradas junto à implementação de cada frente.
Os dois `requirements.txt` históricos permanecem intactos e são específicos dos
experimentos; não são o ambiente reproduzível da base nova. Não há alegação de
reprodução dos resultados RAG anteriores nesta issue.

## Instalar em ambiente limpo

Execute na raiz do repositório. No macOS/Linux, use o executável Python compatível
disponível (por exemplo, `python3.12` no lugar de `python3`).

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install --editable ./packages/ai
.venv/bin/python -m pip check
.venv/bin/python -m finance_ai
.venv/bin/finance-ai
python3 scripts/verificar_legado.py
```

No Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.venv\\Scripts\\python.exe -m pip install --editable ./packages/ai
.venv\\Scripts\\python.exe -m pip check
.venv\\Scripts\\python.exe -m finance_ai
.venv\\Scripts\\finance-ai.exe
py -3.12 scripts/verificar_legado.py
```

A saída do pacote deve conter nome `grupo11-finance-ai`, versão `0.1.0`,
status `estrutura_inicial` e `componentes_implementados: []`. `pip check` deve
informar ausência de conflitos. O verificador do legado precisa terminar sem
erros. A primeira instalação pode usar a rede; a execução do comando não usa.

Para uma nova instalação independente, escolha outro diretório de ambiente
virtual vazio e repita os comandos com esse caminho. Não remova seu ambiente
existente como parte de uma tarefa de documentação.

## Configuração de exemplo

`.env.example` contém apenas valores locais ilustrativos. Se necessário, copie-o
para `.env`; o arquivo local é ignorado. O pacote base não carrega `.env` nem
consome essas variáveis ainda: o carregamento será implementado pelos serviços.

| Variável | Valor de exemplo | Uso reservado |
|---|---|---|
| FINANCE_ENV | development | Identificar ambiente de execução |
| FINANCE_RUNTIME_DIR | .runtime | Diretório de artefatos locais gerados |
| OLLAMA_BASE_URL | http://localhost:11434 | Endereço local se Ollama for adotado |

Não adicionar credenciais reais ao exemplo. Modelos, autenticação, configuração
PostgreSQL, retenção de imagens e cache PWA ainda dependem das decisões
registradas na arquitetura.

## Organização incremental

| Diretório | Responsabilidade |
|---|---|
| apps/web | Frontend React/PWA; somente orientação nesta etapa |
| apps/api | Backend financeiro; somente orientação nesta etapa |
| packages/ai | Pacote Python instalável para a futura implementação de IA |
| contracts | Schemas e exemplos compartilhados |
| knowledge | Catálogo e acervo canônico futuros |
| experiments/rag | Índice dos experimentos preservados nos caminhos originais |
| evaluations | Datasets e baselines revisados |
| infra | Configuração de execução e implantação |
| scripts | Verificações de suporte ao desenvolvimento |
| docs | Definição, arquitetura e instruções da equipe |

Os READMEs tornam as fronteiras visíveis sem declarar funcionalidades prontas.
Não foram criados servidores vazios ou cópias das fontes.

## Preservação e rastreabilidade

`legado-inventario.json` registra o commit de origem, cada path e o hash do blob
de todos os arquivos em `RAG/`, `fontes/`, dos dois notebooks da raiz e do
`requirements.txt` da raiz. Inclui fontes, código, resultados e bancos já
versionados. O inventário não é um catálogo curado de documentos.

`scripts/verificar_legado.py` compara os blobs com o índice Git e verifica
alterações locais dos paths inventariados. Não abre bancos, não desserializa
pickle, não executa notebooks e não altera o índice. Arquivos novos não são
tratados como perda; remoção ou alteração de um arquivo inventariado falha.

Há paths NFC/NFD equivalentes em `fontes/`. O inventário preserva a grafia exata
do índice Git, porque o macOS pode mostrar dois paths como um único arquivo.
Não renomear ou deduplicar esses paths antes da curadoria com aliases. O
verificador respeita `core.precomposeunicode` nas plataformas que o utilizam.

A configuração `.gitignore` impede novos segredos, ambientes e caches locais.
Ela não retira arquivos já rastreados. Índices Chroma, caches e outros artefatos
históricos continuam presentes; sua retirada do rastreamento exige tarefa
própria, preservação e comprovação de reconstrução.

## Verificação no CI

Além da validação de Python e notebooks existente, o CI instala o pacote em
ambiente temporário, executa `pip check`, os dois comandos de entrada e a
verificação do inventário. Não executa os experimentos nem depende de modelos.
