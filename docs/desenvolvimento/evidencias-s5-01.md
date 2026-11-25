# Evidências locais — S5-01 / #95

Verificação em 23/11/2026, branch `feat-95-upload-comprovantes`, criada a partir
da `main` em `b6b0a6a`. Dados inteiramente fictícios: as imagens são geradas
pelos próprios testes. Este registro não substitui revisão e merge do PR.

## O que foi entregue

- App Django `comprovantes`: modelo, migração, rotas Django Ninja, validação
  com Pillow, armazenamento privado e comando `limpar_comprovantes`.
- Documentação: [upload de comprovantes](../arquitetura/comprovantes.md),
  variáveis no [guia do ambiente](ambiente.md) e seção no README da API.
- Dependência nova: `pillow==12.3.0` (também será usada pelo OCR).

## Critérios de aceite

| Critério | Evidência |
|---|---|
| Formato e tamanho validados | `FormatoETamanhoTests`: aceita JPEG, PNG e WebP; formato decidido pelo conteúdo; recusa PDF, GIF, texto, HTML e SVG com nome `.jpg` (415); vazio e corrompido (400); acima do limite (413) sem gravar nada; resolução exagerada (400); limite de envios por hora (429) |
| Upload isolado por usuária | `IsolamentoTests`: outra usuária não lista, não vê, não baixa e não apaga, e recebe o mesmo 404 de um id inexistente; dona vem da sessão, não do formulário; sem sessão, todas as rotas respondem 401; escrita sem CSRF responde 403; todas as rotas exigem autenticação no OpenAPI |
| Retenção e remoção documentadas, sem conteúdo bruto em logs | `RetencaoERemocaoTests` (prazo aplicado, exclusão apaga o arquivo, vencido some das rotas, limpeza apaga vencidos e órfãos e preserva vigentes, excluir a conta apaga os comprovantes); `LogsSemConteudoTests` (logs sem bytes, nome original, EXIF ou nome de usuário; upload não cria nenhum outro registro); política na seção 6 de `comprovantes.md` |

Além disso: metadados EXIF (inclusive localização) são removidos, o nome
original não é guardado e o arquivo é gravado com permissão 0600.

## Execução (equivalente ao job `backend` da CI)

PostgreSQL 17 descartável, Python 3.12:

```text
python -m pip install -r requirements.txt && python -m pip check   → OK
python manage.py check                                             → OK
python manage.py makemigrations --check --dry-run                  → No changes detected
python manage.py migrate --noinput && python manage.py migrate --check → OK
python manage.py test                                              → 30 testes OK (25 de comprovantes)
```

## Os testes pegam erro de verdade

Cada proteção foi removida de propósito, e o teste correspondente falhou:

| Proteção removida | Teste que falhou |
|---|---|
| Filtro por usuária na busca | `test_outra_usuaria_nao_lista_nao_ve_nao_baixa_e_nao_apaga` |
| Regravação sem metadados | `test_metadados_exif_com_localizacao_sao_removidos` |
| Conferência da assinatura do arquivo | `test_recusa_formatos_nao_aceitos_mesmo_com_nome_de_imagem` |
| Nome original fora do log | `test_logs_de_envio_recusa_e_exclusao_nao_trazem_conteudo_nem_nome` |
| Autenticação no router | `test_sem_sessao_nenhuma_rota_responde` |

## Relação com o BE-02 (#84)

Esta branch não depende do PR #123: usa a sessão nativa do Django
(`django_auth` do Django Ninja). A junção com o branch do #84 foi testada
localmente; o resultado está na seção "Compatibilidade" do PR. Depois do merge
do #84, um ajuste pequeno troca para `RegistroDaUsuaria` e o autenticador
`sessao`.
