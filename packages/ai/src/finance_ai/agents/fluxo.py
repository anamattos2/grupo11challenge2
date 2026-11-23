"""Política de fluxo entre os agentes: aprovação, abstenção e falha (S4-01 / #75).

Este módulo é a especificação executável que o orquestrador (S4-06 / #80) vai
seguir. Ele não chama modelos nem ferramentas: só decide, a partir da saída
de uma etapa, qual é a próxima, e monta a resposta final. Por ser
determinístico, cada regra tem teste.

Estados possíveis::

            ┌──── pedido de cálculo (1 rodada) ───┐
            ▼                                     │
    PESQUISA ─► ANALISE ─► VALIDACAO ─► COMUNICACAO ─► RESPONDIDA
       │           │           │  ▲
       │           │           └──┘ (1 revisão)
       ▼           ▼           ▼
    ABSTENCAO  PEDIDO_COMPLEMENTO  ABSTENCAO
    FALHA      ABSTENCAO, FALHA

Desfechos que não são "respondida", com significados diferentes:

- **abstenção**: o sistema funcionou, mas não há base para afirmar nada:
  busca sem resultados, consultas sem permissão, cálculo que não pôde ser
  obtido ou validação reprovada. Dizer "não sei" é correto.
- **pedido de complemento**: falta um dado que só a usuária pode informar
  (ex.: nenhuma categoria marcada como essencial).
- **falha**: algum componente quebrou (erro de ferramenta, exceção, tempo
  esgotado, contrato inválido, referência entre etapas que não bate).
  Falha nunca é apresentada como "não encontrei".
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import StrEnum
import re
from typing import TypeVar

from pydantic import ValidationError

from .contratos import (
    ChamadaFerramenta,
    Contrato,
    ContextoAutorizado,
    EtapaRastro,
    Evidencia,
    FonteCitada,
    Lacuna,
    Ligacao,
    Lista,
    MotivoEncerramento,
    Papel,
    PedidoCalculo,
    RespostaFinal,
    SaidaAnalise,
    SaidaComunicacao,
    SaidaPesquisa,
    SaidaValidacao,
    status_da_pesquisa,
)

MAX_REVISOES_PADRAO = 1
"""Quantas vezes a Analysis pode refazer o trabalho após uma reprovação."""

MAX_RODADAS_CALCULO = 1
"""Quantas vezes a Analysis pode pedir cálculos à Research numa pergunta."""


class Etapa(StrEnum):
    PESQUISA = "pesquisa"
    ANALISE = "analise"
    VALIDACAO = "validacao"
    COMUNICACAO = "comunicacao"
    RESPONDIDA = "respondida"
    ABSTENCAO = "abstencao"
    PEDIDO_COMPLEMENTO = "pedido_complemento"
    FALHA = "falha"


ETAPAS_FINAIS = frozenset({Etapa.RESPONDIDA, Etapa.ABSTENCAO, Etapa.PEDIDO_COMPLEMENTO, Etapa.FALHA})


class Transicao(Contrato):
    proxima: Etapa
    motivo: MotivoEncerramento | None = None
    feedback: Lista[str] = ()
    calculos: Lista[PedidoCalculo] = ()
    problemas: Lista[str] = ()
    """Inconsistências entre etapas que levaram a uma falha de contrato (para o rastro)."""


# --------------------------------------------------------------------------
# Leitura segura de contratos
# --------------------------------------------------------------------------

C = TypeVar("C", bound=Contrato)


class ContratoInvalido(Exception):
    """Saída de agente que não respeita o schema. Vira falha da etapa."""

    def __init__(self, modelo: str, erros: list[dict]):
        self.modelo = modelo
        self.erros = erros
        super().__init__(f"{modelo}: {len(erros)} erro(s) de contrato")


def ler_contrato(modelo: type[C], dados: object) -> C:
    """Valida ``dados`` (dict, JSON ou objeto do próprio modelo) contra ``modelo``.

    Use na fronteira de cada agente, principalmente quando a saída vem de um
    LLM: o texto gerado é não confiável até passar por aqui. Um objeto do
    modelo também é revalidado a partir de uma cópia, para que o agente que o
    produziu não guarde uma referência ao que segue no fluxo.
    """
    try:
        if isinstance(dados, (str, bytes)):
            return modelo.model_validate_json(dados)
        if isinstance(dados, Contrato):
            dados = dados.model_dump()
        return modelo.model_validate(dados)
    except ValidationError as exc:
        erros = [{"loc": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        raise ContratoInvalido(modelo.__name__, erros) from None


# --------------------------------------------------------------------------
# Pesquisa e pedidos de cálculo
# --------------------------------------------------------------------------


def apos_pesquisa(saida: SaidaPesquisa) -> Transicao:
    """Busca vazia, falta de permissão e falha de ferramenta têm destinos distintos."""
    if saida.status == "falha":
        return Transicao(proxima=Etapa.FALHA, motivo=MotivoEncerramento.FALHA_PESQUISA)
    if saida.status == "sem_permissao":
        return Transicao(proxima=Etapa.ABSTENCAO, motivo=MotivoEncerramento.SEM_PERMISSAO)
    if saida.status == "sem_evidencias":
        return Transicao(proxima=Etapa.ABSTENCAO, motivo=MotivoEncerramento.SEM_EVIDENCIAS)
    return Transicao(proxima=Etapa.ANALISE)


def chamadas_para_calculos(calculos: Lista[PedidoCalculo]) -> tuple[ChamadaFerramenta, ...]:
    return tuple(pedido.como_chamada() for pedido in calculos)


def mesclar_pesquisas(base: SaidaPesquisa, complemento: SaidaPesquisa) -> SaidaPesquisa:
    """Junta a pesquisa original com a que atendeu os pedidos de cálculo.

    Evidências repetidas entram uma vez; todas as chamadas ficam no rastro.
    O status é recalculado pela mesma regra de ``status_da_pesquisa``.
    """
    evidencias = {e.id: e for e in base.evidencias}
    for evidencia in complemento.evidencias:
        evidencias.setdefault(evidencia.id, evidencia)
    chamadas = base.chamadas + complemento.chamadas
    modo = "prototipo_fixtures" if "prototipo_fixtures" in (base.modo, complemento.modo) else "integrado"
    return SaidaPesquisa(
        status=status_da_pesquisa(bool(evidencias), chamadas),
        modo=modo,
        evidencias=tuple(evidencias.values()),
        chamadas=chamadas,
        observacoes=base.observacoes + complemento.observacoes,
    )


def inconsistencias_analise(pesquisa: SaidaPesquisa, analise: SaidaAnalise) -> list[str]:
    """A Analysis só pode citar evidências que existem na pesquisa desta pergunta.

    Os contratos validam cada saída isoladamente; esta checagem cruza duas
    etapas. Uma referência quebrada aqui é falha de contrato da Analysis.
    """
    existentes = {e.id for e in pesquisa.evidencias}
    return [f"afirmação {a.id} cita a evidência {i}, que não está na pesquisa"
            for a in analise.afirmacoes for i in a.evidencias_ids if i not in existentes]


def inconsistencias_validacao(analise: SaidaAnalise, validacao: SaidaValidacao) -> list[str]:
    """A Validation só pode aprovar, reprovar ou comentar afirmações que existem."""
    existentes = {a.id for a in analise.afirmacoes}
    citadas = [("aprovou", i) for i in validacao.afirmacoes_aprovadas]
    citadas += [("marcou sem suporte", i) for i in validacao.alegacoes_sem_suporte]
    citadas += [("verificou", v.afirmacao_id) for v in validacao.verificacoes if v.afirmacao_id]
    return [f"a Validation {acao} a afirmação {i}, que não está na análise"
            for acao, i in citadas if i not in existentes]


def apos_analise(
    saida: SaidaAnalise,
    rodadas_calculo: int = 0,
    max_rodadas: int = MAX_RODADAS_CALCULO,
    ja_pedidos: Lista[str] = (),
    pesquisa: SaidaPesquisa | None = None,
) -> Transicao:
    """Pedido de cálculo volta à Research uma vez; repetido ou além do limite, abstenção.

    Com ``pesquisa``, confere antes as referências da Analysis
    (``inconsistencias_analise``); referência quebrada é falha de contrato.
    """
    if pesquisa is not None:
        problemas = inconsistencias_analise(pesquisa, saida)
        if problemas:
            return Transicao(proxima=Etapa.FALHA, motivo=MotivoEncerramento.CONTRATO_INVALIDO,
                             problemas=problemas)
    if saida.status == "falha":
        return Transicao(proxima=Etapa.FALHA, motivo=MotivoEncerramento.FALHA_ANALISE)
    if saida.status == "dados_insuficientes":
        return Transicao(proxima=Etapa.PEDIDO_COMPLEMENTO, motivo=MotivoEncerramento.DADOS_INSUFICIENTES)
    if saida.status == "precisa_calculo":
        repetido = any(p.id in ja_pedidos for p in saida.calculos)
        if rodadas_calculo < max_rodadas and not repetido:
            return Transicao(proxima=Etapa.PESQUISA, calculos=saida.calculos)
        return Transicao(proxima=Etapa.ABSTENCAO, motivo=MotivoEncerramento.CALCULO_INDISPONIVEL)
    return Transicao(proxima=Etapa.VALIDACAO)


# --------------------------------------------------------------------------
# Validação
# --------------------------------------------------------------------------


def apos_validacao(
    saida: SaidaValidacao,
    revisoes_realizadas: int,
    max_revisoes: int = MAX_REVISOES_PADRAO,
    analise: SaidaAnalise | None = None,
) -> Transicao:
    """Reprovação devolve à Analysis uma vez com feedback; depois, abstenção.

    A análise reprovada nunca segue para a Communication. Com ``analise``,
    confere antes se a Validation só citou afirmações que existem
    (``inconsistencias_validacao``); se não, é falha de contrato.
    """
    if analise is not None:
        problemas = inconsistencias_validacao(analise, saida)
        if problemas:
            return Transicao(proxima=Etapa.FALHA, motivo=MotivoEncerramento.CONTRATO_INVALIDO,
                             problemas=problemas)
    if saida.decisao == "reprovada":
        if revisoes_realizadas < max_revisoes:
            return Transicao(proxima=Etapa.ANALISE, feedback=saida.feedback)
        return Transicao(proxima=Etapa.ABSTENCAO, motivo=MotivoEncerramento.VALIDACAO_REPROVADA)
    return Transicao(proxima=Etapa.COMUNICACAO)


# --------------------------------------------------------------------------
# Communication: checagem e montagem da resposta
# --------------------------------------------------------------------------

_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")


def _normalizar_numero(bruto: str) -> str:
    """'R$ 1.850,40', '1850.40' e '1850,4' viram '1850.4'; '6.000' vira '6000'."""
    if "." in bruto and "," in bruto:
        texto = bruto.replace(".", "").replace(",", ".")
    elif "," in bruto:
        texto = bruto.replace(",", ".") if bruto.count(",") == 1 else bruto.replace(",", "")
    elif "." in bruto:
        partes = bruto.split(".")
        milhar = len(partes) > 1 and all(len(p) == 3 for p in partes[1:])
        texto = bruto.replace(".", "") if milhar else bruto
    else:
        texto = bruto
    try:
        return format(Decimal(texto).normalize(), "f")
    except InvalidOperation:
        return bruto


def numeros(texto: str) -> set[str]:
    """Números (valores, percentuais, anos, dias) de um texto, em forma canônica."""
    return {_normalizar_numero(m.group()) for m in _NUMERO.finditer(texto)}


def inconsistencias_comunicacao(
    analise: SaidaAnalise, validacao: SaidaValidacao, saida: SaidaComunicacao
) -> list[str]:
    """Checagem determinística dos parágrafos da Communication.

    - cada parágrafo só expressa afirmações aprovadas;
    - todo número do parágrafo aparece no texto das afirmações que ele declara
      (a Communication pode reformatar "1850.40" como "R$ 1.850,40", mas não
      pode trazer um número novo, nem marcar citações por conta própria);
    - toda afirmação aprovada aparece em algum parágrafo.

    Limite conhecido: uma frase nova sem números não é detectável por regra.
    Por isso a Communication não escolhe fontes, e a implementação dela
    (S4-05) deve trazer avaliação própria do texto.
    """
    problemas: list[str] = []
    aprovadas = list(validacao.afirmacoes_aprovadas)
    por_id = {a.id: a for a in analise.afirmacoes}
    cobertas: set[str] = set()
    for indice, paragrafo in enumerate(saida.paragrafos, start=1):
        permitidos: set[str] = set()
        for afirmacao_id in paragrafo.afirmacoes_ids:
            if afirmacao_id not in aprovadas or afirmacao_id not in por_id:
                problemas.append(f"parágrafo {indice} usa a afirmação {afirmacao_id}, que não foi aprovada")
                continue
            cobertas.add(afirmacao_id)
            permitidos |= numeros(por_id[afirmacao_id].texto)
        extras = numeros(paragrafo.texto) - permitidos
        if extras:
            problemas.append(f"parágrafo {indice} traz números fora das afirmações: {sorted(extras)}")
    faltando = [a for a in aprovadas if a not in cobertas]
    if faltando:
        problemas.append(f"afirmações aprovadas fora do texto: {faltando}")
    return problemas


def rotulo_evidencia(evidencia: Evidencia) -> str:
    if evidencia.tipo == "documental":
        nome = evidencia.origem.titulo or evidencia.origem.document_id
        return f"{nome}, p. {evidencia.localizacao.pagina}"
    return evidencia.resumo


def montar_resposta(
    contexto: ContextoAutorizado,
    pesquisa: SaidaPesquisa,
    analise: SaidaAnalise,
    validacao: SaidaValidacao,
    comunicacao: SaidaComunicacao | None,
    etapas: Lista[EtapaRastro],
) -> tuple[RespostaFinal, list[str]]:
    """Monta texto, citações, fontes e ligações a partir das afirmações aprovadas.

    Usa os parágrafos da Communication quando passam na checagem; senão (ou
    se a Communication falhou), usa o texto literal das afirmações aprovadas.
    Devolve a resposta e a lista de problemas encontrados na redação.

    Lança ``ValueError`` (nunca ``KeyError``) se as etapas anteriores não
    baterem entre si; o grafo transforma isso em falha de contrato.
    """
    quebradas = inconsistencias_analise(pesquisa, analise) + inconsistencias_validacao(analise, validacao)
    if validacao.decisao == "reprovada" or not validacao.afirmacoes_aprovadas:
        quebradas.append("não há afirmações aprovadas para responder")
    if quebradas:
        raise ValueError("; ".join(quebradas))
    por_id = {a.id: a for a in analise.afirmacoes}
    evidencias = {e.id: e for e in pesquisa.evidencias}
    problemas = (inconsistencias_comunicacao(analise, validacao, comunicacao)
                 if comunicacao else ["a Communication não entregou redação"])
    literal = [((a,), por_id[a].texto) for a in validacao.afirmacoes_aprovadas]
    tentativas = [("literal", literal, ())]
    if not problemas:
        redigidos = [(p.afirmacoes_ids, p.texto) for p in comunicacao.paragrafos]
        tentativas.insert(0, ("communication", redigidos, comunicacao.limites))

    for redacao, paragrafos, limites in tentativas:
        numero: dict[str, int] = {}
        blocos: list[str] = []
        ligacoes: list[Ligacao] = []
        for afirmacoes_ids, texto in paragrafos:
            marcas = []
            for afirmacao_id in afirmacoes_ids:
                ids = por_id[afirmacao_id].evidencias_ids
                if afirmacao_id not in {l.afirmacao_id for l in ligacoes}:
                    ligacoes.append(Ligacao(afirmacao_id=afirmacao_id, evidencias_ids=ids))
                for evidencia_id in ids:
                    if evidencia_id not in evidencias:
                        raise ValueError(f"evidência {evidencia_id} não existe na pesquisa")
                    numero.setdefault(evidencia_id, len(numero) + 1)
                    if numero[evidencia_id] not in marcas:
                        marcas.append(numero[evidencia_id])
            blocos.append(texto.rstrip() + " " + "".join(f"[{n}]" for n in sorted(marcas)))
        fontes = [FonteCitada(evidencia_id=i, rotulo=f"[{n}] {rotulo_evidencia(evidencias[i])}"[:300])
                  for i, n in numero.items()]
        try:
            resposta = RespostaFinal(
                correlation_id=contexto.correlation_id, estado="respondida", texto="\n\n".join(blocos),
                redacao=redacao, fontes=fontes, ligacoes=ligacoes,
                limites=tuple(limites) or (LIMITE_PADRAO,), etapas=etapas,
            )
        except ValidationError:
            problemas = problemas + [f"redação {redacao} não cabe na resposta final"]
            continue
        return resposta, problemas
    raise ValueError("não foi possível montar a resposta nem com a redação literal")


def falha_de_etapa(papel: Papel, *, tempo_esgotado: bool = False, contrato: bool = False) -> Transicao:
    """Exceção, timeout ou contrato inválido em qualquer agente."""
    if tempo_esgotado:
        motivo = MotivoEncerramento.TEMPO_ESGOTADO
    elif contrato:
        motivo = MotivoEncerramento.CONTRATO_INVALIDO
    else:
        motivo = {
            Papel.RESEARCH: MotivoEncerramento.FALHA_PESQUISA,
            Papel.ANALYSIS: MotivoEncerramento.FALHA_ANALISE,
            Papel.VALIDATION: MotivoEncerramento.FALHA_VALIDACAO,
            Papel.COMMUNICATION: MotivoEncerramento.FALHA_COMUNICACAO,
        }.get(papel, MotivoEncerramento.CONTRATO_INVALIDO)
    return Transicao(proxima=Etapa.FALHA, motivo=motivo)


# --------------------------------------------------------------------------
# Respostas seguras
# --------------------------------------------------------------------------

LIMITE_PADRAO = (
    "Valores financeiros são os declarados por você no aplicativo, sem conexão com bancos."
)

MENSAGENS_SEGURAS: dict[MotivoEncerramento, str] = {
    MotivoEncerramento.SEM_EVIDENCIAS: (
        "Não encontrei informações suficientes nos documentos e nos dados cadastrados "
        "para responder com segurança. Você pode reformular a pergunta?"
    ),
    MotivoEncerramento.SEM_PERMISSAO: (
        "Esta conversa não tem permissão para consultar todas as informações necessárias "
        "para responder, e o que pude consultar não foi suficiente."
    ),
    MotivoEncerramento.CALCULO_INDISPONIVEL: (
        "Não consegui obter, a partir dos dados cadastrados, os cálculos necessários "
        "para responder com segurança."
    ),
    MotivoEncerramento.VALIDACAO_REPROVADA: (
        "Não consegui confirmar a resposta com as fontes disponíveis, então prefiro "
        "não afirmar algo que possa estar errado."
    ),
    MotivoEncerramento.DADOS_INSUFICIENTES: (
        "Para responder, preciso de mais algumas informações."
    ),
}
MENSAGEM_FALHA = (
    "Não foi possível concluir sua pergunta agora. Nenhum dado seu foi alterado. "
    "Tente novamente em instantes."
)


def resposta_segura(
    contexto: ContextoAutorizado,
    final: Etapa,
    motivo: MotivoEncerramento,
    etapas: Lista[EtapaRastro],
    lacunas: Lista[Lacuna] = (),
) -> RespostaFinal:
    """Texto fixo, sem LLM, para abstenção, pedido de complemento ou falha.

    Não reaproveita nenhum texto da análise reprovada.
    """
    if final not in (Etapa.ABSTENCAO, Etapa.PEDIDO_COMPLEMENTO, Etapa.FALHA):
        raise ValueError("resposta_segura não se aplica a respostas aprovadas")
    perguntas = ()
    if final is Etapa.PEDIDO_COMPLEMENTO:
        perguntas = tuple(l.pergunta_complemento or l.descricao for l in lacunas)
    texto = MENSAGEM_FALHA if final is Etapa.FALHA else MENSAGENS_SEGURAS[motivo]
    return RespostaFinal(
        correlation_id=contexto.correlation_id,
        estado=final.value,
        texto=texto,
        perguntas_complemento=perguntas,
        motivo=motivo,
        limites=(LIMITE_PADRAO,),
        etapas=etapas,
    )
