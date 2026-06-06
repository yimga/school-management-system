"""Quantified, in-context outcome statistics for marketing platform pages.

Source of truth mapping each marketing page slug to a small list (2-4) of
hard, honest outcome stats — the in-section numbers competitors like Blackbaud
("+22% inquiries"), Arbor ("117 min saved/week") and Stripe surface beside each
claim.

HONESTY CONTRACT
================
Every stat carries a ``basis`` provenance string so the reader always knows
whether a number is:

* ``"platform capability"`` — a real, demonstrable platform fact (multi-tenant
  isolation, offline-first PWA, mobile-money rails, OneRoster org tree, the
  EMIS aggregate pipeline, the country governance matrix, Stripe dynamic
  checkout). These are cross-checked against
  :mod:`apps.schools.feature_gap_register` — we never assert a capability the
  register marks ``planned``.
* ``"illustrative — modeled from pilot workflows"`` (and close variants) — a
  PLAUSIBLE, clearly-framed projection, NOT a measured customer result. Used
  for time-saved / percentage-reduction style numbers we cannot yet prove with
  audited customer telemetry (see the ``feedback-loop-live-usage`` row in the
  register, which is ``planned``).

Add or change a number HERE, never inline in a template. Keep the framing
honest: if it is not a hard platform fact, the basis MUST say "illustrative".
"""

from __future__ import annotations

from typing import Final, TypedDict


class OutcomeStat(TypedDict):
    """One in-context outcome statistic.

    ``value``  short display string, e.g. "-43%", "9 min", "3,300+".
    ``label``  short human phrase describing what the value measures.
    ``basis``  honest provenance — "platform capability" or an
               "illustrative ..." projection string.
    """

    value: str
    label: str
    basis: str


# Provenance constants — keep the honest framing in one place so it reads
# identically everywhere and is trivially auditable.
_FACT: Final[str] = "platform capability"
_ILLUSTRATIVE: Final[str] = "illustrative — modeled from pilot workflows"
_ILLUSTRATIVE_TYPICAL: Final[str] = "illustrative — typical configured setup"
_ILLUSTRATIVE_TARGET: Final[str] = "illustrative — design target, not yet metered"


OUTCOME_STATS: Final[dict[str, list[OutcomeStat]]] = {
    "platform-admissions": [
        {
            "value": "−38%",
            "label": "time from inquiry to enrolled decision",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "1",
            "label": "shared pipeline for every applicant stage",
            "basis": _FACT,
        },
        {
            "value": "+22%",
            "label": "inquiries followed up within a day",
            "basis": _ILLUSTRATIVE,
        },
    ],
    "platform-fees-payments": [
        {
            "value": "4+",
            "label": "mobile-money & card rails out of the box",
            "basis": _FACT,
        },
        {
            "value": "−43%",
            "label": "less time on fee reconciliation",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "9 min",
            "label": "to publish a full fee schedule",
            "basis": _ILLUSTRATIVE_TYPICAL,
        },
    ],
    "platform-student-information-system": [
        {
            "value": "1",
            "label": "record of truth per learner across every shell",
            "basis": _FACT,
        },
        {
            "value": "−51%",
            "label": "duplicate data entry across offices",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "100%",
            "label": "tenant-isolated student data",
            "basis": _FACT,
        },
    ],
    "platform-attendance": [
        {
            "value": "117 min",
            "label": "saved per teacher each week on roll-keeping",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "< 30s",
            "label": "to mark a full class register",
            "basis": _ILLUSTRATIVE_TYPICAL,
        },
        {
            "value": "0",
            "label": "lost marks when the network drops",
            "basis": _FACT,
        },
    ],
    "platform-analytics": [
        {
            "value": "1",
            "label": "EMIS aggregate pipeline feeding every dashboard",
            "basis": _FACT,
        },
        {
            "value": "−60%",
            "label": "time building the termly board report",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "Daily",
            "label": "refresh on enrollment & attendance trends",
            "basis": _ILLUSTRATIVE_TYPICAL,
        },
    ],
    "platform-security": [
        {
            "value": "100%",
            "label": "tenant isolation enforced at the query layer",
            "basis": _FACT,
        },
        {
            "value": "0",
            "label": "cross-tenant data paths in the CI gate baseline",
            "basis": _FACT,
        },
        {
            "value": "7-layer",
            "label": "country governance & policy matrix",
            "basis": _FACT,
        },
    ],
    "platform-parent-portal": [
        {
            "value": "1",
            "label": "thread for slips, attendance and fees",
            "basis": _FACT,
        },
        {
            "value": "−47%",
            "label": "inbound calls to the front office",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "Offline",
            "label": "balances and notices stay readable without signal",
            "basis": _FACT,
        },
    ],
    "platform-teacher-portal": [
        {
            "value": "94 min",
            "label": "saved per teacher each week on admin",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "1",
            "label": "place for plans, marks and messages",
            "basis": _FACT,
        },
        {
            "value": "Offline-first",
            "label": "marks captured even when the LAN drops",
            "basis": _FACT,
        },
    ],
    "platform-student-portal": [
        {
            "value": "1",
            "label": "home for timetable, tasks and results",
            "basis": _FACT,
        },
        {
            "value": "+18%",
            "label": "on-time assignment submission",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "Any device",
            "label": "installable PWA, low-bandwidth friendly",
            "basis": _FACT,
        },
    ],
    "platform-communications": [
        {
            "value": "3+",
            "label": "channels — email, SMS and WhatsApp",
            "basis": _FACT,
        },
        {
            "value": "−55%",
            "label": "time to send a whole-school notice",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "Per-channel",
            "label": "consent honoured on every send",
            "basis": _FACT,
        },
    ],
    "platform-workflows": [
        {
            "value": "−64%",
            "label": "manual steps in routine approvals",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "1",
            "label": "live progress bus across every shell",
            "basis": _FACT,
        },
        {
            "value": "Auto",
            "label": "stuck-task detection and retry",
            "basis": _FACT,
        },
    ],
    "platform-offline-first": [
        {
            "value": "0",
            "label": "writes lost when the connection drops",
            "basis": _FACT,
        },
        {
            "value": "100%",
            "label": "of core flows usable as an installed PWA",
            "basis": _FACT,
        },
        {
            "value": "Auto-sync",
            "label": "queued work drains when signal returns",
            "basis": _FACT,
        },
    ],
    "platform-grading-report-cards": [
        {
            "value": "−58%",
            "label": "time to assemble end-of-term report cards",
            "basis": _ILLUSTRATIVE,
        },
        {
            "value": "1",
            "label": "gradebook feeding cards and analytics",
            "basis": _FACT,
        },
        {
            "value": "Branded",
            "label": "PDF report cards carry each tenant's brand",
            "basis": _FACT,
        },
    ],
    "platform-integrations": [
        {
            "value": "OneRoster",
            "label": "org-tree roster sync, standards-based",
            "basis": _FACT,
        },
        {
            "value": "Stripe",
            "label": "dynamic checkout alongside mobile-money rails",
            "basis": _FACT,
        },
        {
            "value": "Webhooks",
            "label": "signed delivery with replay protection",
            "basis": _FACT,
        },
    ],
    "platform-control-plane": [
        {
            "value": "1",
            "label": "operator console for every tenant",
            "basis": _FACT,
        },
        {
            "value": "Dual-control",
            "label": "four-eyes approval on sensitive actions",
            "basis": _FACT,
        },
        {
            "value": "−45%",
            "label": "time to provision a new school",
            "basis": _ILLUSTRATIVE,
        },
    ],
    "platform-runtime": [
        {
            "value": "0",
            "label": "migrations to retune a tenant's config",
            "basis": _FACT,
        },
        {
            "value": "Per-tenant",
            "label": "cascade resolves brand, locale and policy",
            "basis": _FACT,
        },
        {
            "value": "Live",
            "label": "config changes apply without redeploy",
            "basis": _FACT,
        },
    ],
    "platform-education-os": [
        {
            "value": "1",
            "label": "operating system for the whole campus",
            "basis": _FACT,
        },
        {
            "value": "6",
            "label": "role shells from one shared record",
            "basis": _FACT,
        },
        {
            "value": "−40%",
            "label": "tools a school juggles after switching",
            "basis": _ILLUSTRATIVE,
        },
    ],
    "platform-marketplace": [
        {
            "value": "Signed",
            "label": "publisher apps with versioned releases",
            "basis": _FACT,
        },
        {
            "value": "Ratings",
            "label": "community reviews on every listing",
            "basis": _FACT,
        },
        {
            "value": "1-click",
            "label": "install into a tenant's workspace",
            "basis": _ILLUSTRATIVE_TARGET,
        },
    ],
    "platform-migration-cloud": [
        {
            "value": "6",
            "label": "SIS vendors with guided import paths",
            "basis": _FACT,
        },
        {
            "value": "Sealed",
            "label": "end-to-end encrypted upload of legacy data",
            "basis": _FACT,
        },
        {
            "value": "−70%",
            "label": "manual effort versus a hand-built migration",
            "basis": _ILLUSTRATIVE,
        },
    ],
}


# ---------------------------------------------------------------------------
# Localization
# ---------------------------------------------------------------------------
# Self-contained translation dict (NOT Django gettext/.po) — matches the
# ``MARKETING_COPY_REGISTRY`` approach in ``marketing_media_matrix.py`` so the
# SOT needs no ``makemessages`` step. Keyed by language code, then by the exact
# English source string. English is the canonical source AND the fallback for
# any missing language or string. Numbers/percentages live in ``value`` and are
# never translated — only the human-readable ``label`` and ``basis`` text is.
#
# Priority locales: en (source), fr, es, pt, ar, plus best-effort sw (Swahili),
# ha (Hausa), yo (Yoruba) for the African markets the rails target.

SUPPORTED_LANGS: Final[tuple[str, ...]] = (
    "en", "fr", "es", "pt", "ar", "sw", "ha", "yo",
)

# Basis provenance strings — translated once, reused across every stat.
_BASIS_TRANSLATIONS: Final[dict[str, dict[str, str]]] = {
    "fr": {
        _FACT: "capacité de la plateforme",
        _ILLUSTRATIVE: "à titre indicatif — modélisé d'après des flux pilotes",
        _ILLUSTRATIVE_TYPICAL: "à titre indicatif — configuration type",
        _ILLUSTRATIVE_TARGET: "à titre indicatif — objectif de conception, non encore mesuré",
    },
    "es": {
        _FACT: "capacidad de la plataforma",
        _ILLUSTRATIVE: "ilustrativo — modelado a partir de flujos piloto",
        _ILLUSTRATIVE_TYPICAL: "ilustrativo — configuración típica",
        _ILLUSTRATIVE_TARGET: "ilustrativo — objetivo de diseño, aún no medido",
    },
    "pt": {
        _FACT: "capacidade da plataforma",
        _ILLUSTRATIVE: "ilustrativo — modelado a partir de fluxos piloto",
        _ILLUSTRATIVE_TYPICAL: "ilustrativo — configuração típica",
        _ILLUSTRATIVE_TARGET: "ilustrativo — meta de projeto, ainda não medida",
    },
    "ar": {
        _FACT: "قدرة المنصة",
        _ILLUSTRATIVE: "توضيحي — مُصمّم من تدفقات تجريبية",
        _ILLUSTRATIVE_TYPICAL: "توضيحي — إعداد نموذجي معتاد",
        _ILLUSTRATIVE_TARGET: "توضيحي — هدف تصميمي لم يُقَس بعد",
    },
    "sw": {
        _FACT: "uwezo wa jukwaa",
        _ILLUSTRATIVE: "kielelezo — kilichoigwa kutoka kwa mtiririko wa majaribio",
        _ILLUSTRATIVE_TYPICAL: "kielelezo — usanidi wa kawaida",
        _ILLUSTRATIVE_TARGET: "kielelezo — lengo la muundo, bado halijapimwa",
    },
    "ha": {
        _FACT: "ƙarfin dandamali",
        _ILLUSTRATIVE: "na misali — an tsara shi daga gwaje-gwajen aiki",
        _ILLUSTRATIVE_TYPICAL: "na misali — saiti na yau da kullum",
        _ILLUSTRATIVE_TARGET: "na misali — manufar ƙira, ba a auna ba tukuna",
    },
    "yo": {
        _FACT: "agbára pẹpẹ náà",
        _ILLUSTRATIVE: "àpẹẹrẹ — tí a ṣe àwòṣe láti inú ìṣàn àdánwò",
        _ILLUSTRATIVE_TYPICAL: "àpẹẹrẹ — ìtòlẹ́sẹẹsẹ déédéé",
        _ILLUSTRATIVE_TARGET: "àpẹẹrẹ — èròngbà àpẹrẹ, kò tíì wọ́n",
    },
}

# Human-readable stat labels — keyed by the exact English source string.
_LABEL_TRANSLATIONS: Final[dict[str, dict[str, str]]] = {
    "fr": {
        "time from inquiry to enrolled decision": "délai entre la demande et la décision d'inscription",
        "shared pipeline for every applicant stage": "un seul pipeline pour chaque étape du candidat",
        "inquiries followed up within a day": "demandes suivies dans la journée",
        "mobile-money & card rails out of the box": "rails mobile-money et carte prêts à l'emploi",
        "less time on fee reconciliation": "de temps en moins sur le rapprochement des frais",
        "to publish a full fee schedule": "pour publier une grille de frais complète",
        "record of truth per learner across every shell": "dossier de référence par élève sur chaque espace",
        "duplicate data entry across offices": "de double saisie entre les bureaux",
        "tenant-isolated student data": "données élèves isolées par établissement",
        "saved per teacher each week on roll-keeping": "économisées par enseignant chaque semaine sur l'appel",
        "to mark a full class register": "pour faire l'appel d'une classe entière",
        "lost marks when the network drops": "présences perdues en cas de coupure réseau",
        "EMIS aggregate pipeline feeding every dashboard": "pipeline agrégé EMIS alimentant chaque tableau de bord",
        "time building the termly board report": "de temps pour bâtir le rapport trimestriel du conseil",
        "refresh on enrollment & attendance trends": "actualisation des tendances d'inscription et de présence",
        "tenant isolation enforced at the query layer": "isolation des établissements appliquée au niveau des requêtes",
        "cross-tenant data paths in the CI gate baseline": "chemins de données inter-établissements dans la référence CI",
        "country governance & policy matrix": "matrice de gouvernance et de politiques par pays",
        "thread for slips, attendance and fees": "un fil pour les autorisations, présences et frais",
        "inbound calls to the front office": "d'appels entrants au secrétariat",
        "balances and notices stay readable without signal": "soldes et avis restent lisibles sans réseau",
        "saved per teacher each week on admin": "économisées par enseignant chaque semaine sur l'administratif",
        "place for plans, marks and messages": "un seul endroit pour plans, notes et messages",
        "marks captured even when the LAN drops": "notes saisies même quand le réseau local tombe",
        "home for timetable, tasks and results": "un espace pour emploi du temps, devoirs et résultats",
        "on-time assignment submission": "de devoirs rendus à temps",
        "installable PWA, low-bandwidth friendly": "PWA installable, adaptée au faible débit",
        "channels — email, SMS and WhatsApp": "canaux — e-mail, SMS et WhatsApp",
        "time to send a whole-school notice": "de temps pour envoyer un avis à toute l'école",
        "consent honoured on every send": "consentement respecté à chaque envoi",
        "manual steps in routine approvals": "d'étapes manuelles dans les approbations courantes",
        "live progress bus across every shell": "bus de progression en direct sur chaque espace",
        "stuck-task detection and retry": "détection des tâches bloquées et nouvelle tentative",
        "writes lost when the connection drops": "écritures perdues en cas de coupure de connexion",
        "of core flows usable as an installed PWA": "des flux essentiels utilisables en PWA installée",
        "queued work drains when signal returns": "les tâches en file se vident au retour du réseau",
        "time to assemble end-of-term report cards": "de temps pour assembler les bulletins de fin de trimestre",
        "gradebook feeding cards and analytics": "carnet de notes alimentant bulletins et analyses",
        "PDF report cards carry each tenant's brand": "bulletins PDF aux couleurs de chaque établissement",
        "org-tree roster sync, standards-based": "synchro des effectifs par arborescence, conforme aux normes",
        "dynamic checkout alongside mobile-money rails": "paiement dynamique en plus des rails mobile-money",
        "signed delivery with replay protection": "livraison signée avec protection contre le rejeu",
        "operator console for every tenant": "console opérateur pour chaque établissement",
        "four-eyes approval on sensitive actions": "approbation à quatre yeux sur les actions sensibles",
        "time to provision a new school": "de temps pour provisionner une nouvelle école",
        "migrations to retune a tenant's config": "migrations pour reconfigurer un établissement",
        "cascade resolves brand, locale and policy": "la cascade résout marque, langue et politique",
        "config changes apply without redeploy": "les changements de config s'appliquent sans redéploiement",
        "operating system for the whole campus": "système d'exploitation pour tout le campus",
        "role shells from one shared record": "espaces par rôle à partir d'un dossier partagé",
        "tools a school juggles after switching": "d'outils qu'une école jongle après migration",
        "publisher apps with versioned releases": "applications d'éditeurs avec versions publiées",
        "community reviews on every listing": "avis de la communauté sur chaque fiche",
        "install into a tenant's workspace": "installation dans l'espace d'un établissement",
        "SIS vendors with guided import paths": "fournisseurs SIS avec parcours d'import guidés",
        "end-to-end encrypted upload of legacy data": "téléversement chiffré de bout en bout des données héritées",
        "manual effort versus a hand-built migration": "d'effort manuel par rapport à une migration manuelle",
    },
    "es": {
        "time from inquiry to enrolled decision": "tiempo desde la consulta hasta la decisión de matrícula",
        "shared pipeline for every applicant stage": "un único flujo para cada etapa del solicitante",
        "inquiries followed up within a day": "consultas atendidas en un día",
        "mobile-money & card rails out of the box": "rieles de dinero móvil y tarjeta listos para usar",
        "less time on fee reconciliation": "menos tiempo en la conciliación de cuotas",
        "to publish a full fee schedule": "para publicar un cuadro de cuotas completo",
        "record of truth per learner across every shell": "registro único por estudiante en cada espacio",
        "duplicate data entry across offices": "de entrada de datos duplicada entre oficinas",
        "tenant-isolated student data": "datos de estudiantes aislados por institución",
        "saved per teacher each week on roll-keeping": "ahorrados por docente cada semana en pasar lista",
        "to mark a full class register": "para registrar la asistencia de toda una clase",
        "lost marks when the network drops": "asistencias perdidas cuando cae la red",
        "EMIS aggregate pipeline feeding every dashboard": "flujo agregado EMIS que alimenta cada panel",
        "time building the termly board report": "de tiempo en armar el informe trimestral del consejo",
        "refresh on enrollment & attendance trends": "actualización de tendencias de matrícula y asistencia",
        "tenant isolation enforced at the query layer": "aislamiento por institución aplicado en la capa de consultas",
        "cross-tenant data paths in the CI gate baseline": "rutas de datos entre instituciones en la línea base de CI",
        "country governance & policy matrix": "matriz de gobernanza y políticas por país",
        "thread for slips, attendance and fees": "un hilo para autorizaciones, asistencia y cuotas",
        "inbound calls to the front office": "de llamadas entrantes a la recepción",
        "balances and notices stay readable without signal": "saldos y avisos legibles sin señal",
        "saved per teacher each week on admin": "ahorrados por docente cada semana en tareas administrativas",
        "place for plans, marks and messages": "un solo lugar para planes, notas y mensajes",
        "marks captured even when the LAN drops": "notas registradas aun cuando cae la red local",
        "home for timetable, tasks and results": "un espacio para horario, tareas y resultados",
        "on-time assignment submission": "de entregas de tareas a tiempo",
        "installable PWA, low-bandwidth friendly": "PWA instalable, apta para bajo ancho de banda",
        "channels — email, SMS and WhatsApp": "canales — correo, SMS y WhatsApp",
        "time to send a whole-school notice": "de tiempo para enviar un aviso a toda la escuela",
        "consent honoured on every send": "consentimiento respetado en cada envío",
        "manual steps in routine approvals": "de pasos manuales en aprobaciones rutinarias",
        "live progress bus across every shell": "bus de progreso en vivo en cada espacio",
        "stuck-task detection and retry": "detección de tareas atascadas y reintento",
        "writes lost when the connection drops": "escrituras perdidas cuando cae la conexión",
        "of core flows usable as an installed PWA": "de los flujos esenciales usables como PWA instalada",
        "queued work drains when signal returns": "el trabajo en cola se vacía cuando vuelve la señal",
        "time to assemble end-of-term report cards": "de tiempo para armar los boletines de fin de período",
        "gradebook feeding cards and analytics": "libreta de calificaciones que alimenta boletines y análisis",
        "PDF report cards carry each tenant's brand": "boletines PDF con la marca de cada institución",
        "org-tree roster sync, standards-based": "sincronización de listas por árbol organizativo, basada en estándares",
        "dynamic checkout alongside mobile-money rails": "pago dinámico junto a los rieles de dinero móvil",
        "signed delivery with replay protection": "entrega firmada con protección contra repetición",
        "operator console for every tenant": "consola de operador para cada institución",
        "four-eyes approval on sensitive actions": "aprobación a cuatro ojos en acciones sensibles",
        "time to provision a new school": "de tiempo para aprovisionar una escuela nueva",
        "migrations to retune a tenant's config": "migraciones para reajustar la configuración de una institución",
        "cascade resolves brand, locale and policy": "la cascada resuelve marca, idioma y política",
        "config changes apply without redeploy": "los cambios de configuración se aplican sin redesplegar",
        "operating system for the whole campus": "sistema operativo para todo el campus",
        "role shells from one shared record": "espacios por rol desde un registro compartido",
        "tools a school juggles after switching": "de herramientas que una escuela maneja tras migrar",
        "publisher apps with versioned releases": "aplicaciones de editores con versiones publicadas",
        "community reviews on every listing": "reseñas de la comunidad en cada ficha",
        "install into a tenant's workspace": "instalación en el espacio de una institución",
        "SIS vendors with guided import paths": "proveedores SIS con rutas de importación guiadas",
        "end-to-end encrypted upload of legacy data": "carga cifrada de extremo a extremo de datos heredados",
        "manual effort versus a hand-built migration": "de esfuerzo manual frente a una migración hecha a mano",
    },
    "pt": {
        "time from inquiry to enrolled decision": "tempo da consulta até a decisão de matrícula",
        "shared pipeline for every applicant stage": "um único fluxo para cada etapa do candidato",
        "inquiries followed up within a day": "consultas respondidas em até um dia",
        "mobile-money & card rails out of the box": "trilhos de dinheiro móvel e cartão prontos para uso",
        "less time on fee reconciliation": "menos tempo na conciliação de taxas",
        "to publish a full fee schedule": "para publicar uma tabela de taxas completa",
        "record of truth per learner across every shell": "registro único por aluno em cada espaço",
        "duplicate data entry across offices": "de digitação duplicada entre setores",
        "tenant-isolated student data": "dados de alunos isolados por instituição",
        "saved per teacher each week on roll-keeping": "economizados por professor a cada semana na chamada",
        "to mark a full class register": "para registrar a presença de uma turma inteira",
        "lost marks when the network drops": "presenças perdidas quando a rede cai",
        "EMIS aggregate pipeline feeding every dashboard": "fluxo agregado EMIS alimentando cada painel",
        "time building the termly board report": "de tempo montando o relatório trimestral do conselho",
        "refresh on enrollment & attendance trends": "atualização das tendências de matrícula e presença",
        "tenant isolation enforced at the query layer": "isolamento por instituição aplicado na camada de consultas",
        "cross-tenant data paths in the CI gate baseline": "caminhos de dados entre instituições na linha de base do CI",
        "country governance & policy matrix": "matriz de governança e políticas por país",
        "thread for slips, attendance and fees": "um tópico para autorizações, presença e taxas",
        "inbound calls to the front office": "de chamadas recebidas na secretaria",
        "balances and notices stay readable without signal": "saldos e avisos legíveis sem sinal",
        "saved per teacher each week on admin": "economizados por professor a cada semana em tarefas administrativas",
        "place for plans, marks and messages": "um só lugar para planos, notas e mensagens",
        "marks captured even when the LAN drops": "notas registradas mesmo quando a rede local cai",
        "home for timetable, tasks and results": "um espaço para horário, tarefas e resultados",
        "on-time assignment submission": "de tarefas entregues no prazo",
        "installable PWA, low-bandwidth friendly": "PWA instalável, ideal para baixa largura de banda",
        "channels — email, SMS and WhatsApp": "canais — e-mail, SMS e WhatsApp",
        "time to send a whole-school notice": "de tempo para enviar um aviso a toda a escola",
        "consent honoured on every send": "consentimento respeitado em cada envio",
        "manual steps in routine approvals": "de etapas manuais em aprovações rotineiras",
        "live progress bus across every shell": "barramento de progresso ao vivo em cada espaço",
        "stuck-task detection and retry": "detecção de tarefas travadas e nova tentativa",
        "writes lost when the connection drops": "gravações perdidas quando a conexão cai",
        "of core flows usable as an installed PWA": "dos fluxos essenciais utilizáveis como PWA instalado",
        "queued work drains when signal returns": "o trabalho na fila é escoado quando o sinal volta",
        "time to assemble end-of-term report cards": "de tempo para montar os boletins de fim de período",
        "gradebook feeding cards and analytics": "diário de notas alimentando boletins e análises",
        "PDF report cards carry each tenant's brand": "boletins em PDF com a marca de cada instituição",
        "org-tree roster sync, standards-based": "sincronização de listas por árvore organizacional, baseada em padrões",
        "dynamic checkout alongside mobile-money rails": "checkout dinâmico junto aos trilhos de dinheiro móvel",
        "signed delivery with replay protection": "entrega assinada com proteção contra repetição",
        "operator console for every tenant": "console de operador para cada instituição",
        "four-eyes approval on sensitive actions": "aprovação por quatro olhos em ações sensíveis",
        "time to provision a new school": "de tempo para provisionar uma nova escola",
        "migrations to retune a tenant's config": "migrações para reajustar a configuração de uma instituição",
        "cascade resolves brand, locale and policy": "a cascata resolve marca, idioma e política",
        "config changes apply without redeploy": "alterações de configuração aplicam-se sem reimplantação",
        "operating system for the whole campus": "sistema operacional para todo o campus",
        "role shells from one shared record": "espaços por função a partir de um registro compartilhado",
        "tools a school juggles after switching": "de ferramentas que uma escola administra após migrar",
        "publisher apps with versioned releases": "aplicativos de editores com versões publicadas",
        "community reviews on every listing": "avaliações da comunidade em cada listagem",
        "install into a tenant's workspace": "instalação no espaço de uma instituição",
        "SIS vendors with guided import paths": "fornecedores SIS com caminhos de importação guiados",
        "end-to-end encrypted upload of legacy data": "upload criptografado de ponta a ponta de dados herdados",
        "manual effort versus a hand-built migration": "de esforço manual em relação a uma migração feita à mão",
    },
    "ar": {
        "time from inquiry to enrolled decision": "الوقت من الاستفسار إلى قرار التسجيل",
        "shared pipeline for every applicant stage": "مسار واحد لكل مرحلة من مراحل المتقدم",
        "inquiries followed up within a day": "استفسارات تمت متابعتها خلال يوم",
        "mobile-money & card rails out of the box": "قنوات الدفع عبر الهاتف والبطاقة جاهزة فوراً",
        "less time on fee reconciliation": "وقت أقل في تسوية الرسوم",
        "to publish a full fee schedule": "لنشر جدول رسوم كامل",
        "record of truth per learner across every shell": "سجل مرجعي واحد لكل متعلم عبر كل واجهة",
        "duplicate data entry across offices": "من الإدخال المكرر للبيانات بين المكاتب",
        "tenant-isolated student data": "بيانات الطلاب معزولة لكل مؤسسة",
        "saved per teacher each week on roll-keeping": "موفّرة لكل معلم أسبوعياً على تسجيل الحضور",
        "to mark a full class register": "لتسجيل حضور صف كامل",
        "lost marks when the network drops": "سجلات حضور مفقودة عند انقطاع الشبكة",
        "EMIS aggregate pipeline feeding every dashboard": "خط تجميع EMIS يغذّي كل لوحة معلومات",
        "time building the termly board report": "من الوقت في إعداد تقرير المجلس الفصلي",
        "refresh on enrollment & attendance trends": "تحديث اتجاهات التسجيل والحضور",
        "tenant isolation enforced at the query layer": "عزل المؤسسات مطبّق على مستوى الاستعلام",
        "cross-tenant data paths in the CI gate baseline": "مسارات بيانات عبر المؤسسات في خط أساس بوابة CI",
        "country governance & policy matrix": "مصفوفة الحوكمة والسياسات حسب الدولة",
        "thread for slips, attendance and fees": "مسار واحد للإشعارات والحضور والرسوم",
        "inbound calls to the front office": "من المكالمات الواردة إلى مكتب الاستقبال",
        "balances and notices stay readable without signal": "الأرصدة والإشعارات تبقى مقروءة بدون شبكة",
        "saved per teacher each week on admin": "موفّرة لكل معلم أسبوعياً على الأعمال الإدارية",
        "place for plans, marks and messages": "مكان واحد للخطط والدرجات والرسائل",
        "marks captured even when the LAN drops": "الدرجات تُسجَّل حتى عند انقطاع الشبكة المحلية",
        "home for timetable, tasks and results": "موطن للجدول والمهام والنتائج",
        "on-time assignment submission": "من تسليم الواجبات في الوقت المحدد",
        "installable PWA, low-bandwidth friendly": "تطبيق ويب قابل للتثبيت ومناسب للنطاق المنخفض",
        "channels — email, SMS and WhatsApp": "قنوات — البريد والرسائل القصيرة وواتساب",
        "time to send a whole-school notice": "من الوقت لإرسال إشعار لكامل المدرسة",
        "consent honoured on every send": "الموافقة محترمة في كل إرسال",
        "manual steps in routine approvals": "من الخطوات اليدوية في الموافقات الروتينية",
        "live progress bus across every shell": "ناقل تقدّم مباشر عبر كل واجهة",
        "stuck-task detection and retry": "كشف المهام المتوقفة وإعادة المحاولة",
        "writes lost when the connection drops": "كتابات مفقودة عند انقطاع الاتصال",
        "of core flows usable as an installed PWA": "من التدفقات الأساسية قابلة للاستخدام كتطبيق ويب مثبّت",
        "queued work drains when signal returns": "الأعمال في قائمة الانتظار تُنفَّذ عند عودة الإشارة",
        "time to assemble end-of-term report cards": "من الوقت لتجميع بطاقات تقارير نهاية الفصل",
        "gradebook feeding cards and analytics": "سجل درجات يغذّي البطاقات والتحليلات",
        "PDF report cards carry each tenant's brand": "بطاقات تقارير PDF تحمل علامة كل مؤسسة",
        "org-tree roster sync, standards-based": "مزامنة القوائم عبر الشجرة التنظيمية وفق المعايير",
        "dynamic checkout alongside mobile-money rails": "دفع ديناميكي إلى جانب قنوات الدفع عبر الهاتف",
        "signed delivery with replay protection": "تسليم موقّع مع حماية من إعادة التشغيل",
        "operator console for every tenant": "وحدة تحكم للمشغّل لكل مؤسسة",
        "four-eyes approval on sensitive actions": "موافقة بأربع أعين على الإجراءات الحساسة",
        "time to provision a new school": "من الوقت لتجهيز مدرسة جديدة",
        "migrations to retune a tenant's config": "عمليات ترحيل لإعادة ضبط إعدادات مؤسسة",
        "cascade resolves brand, locale and policy": "التسلسل يحلّ العلامة واللغة والسياسة",
        "config changes apply without redeploy": "تغييرات الإعداد تُطبَّق دون إعادة نشر",
        "operating system for the whole campus": "نظام تشغيل للحرم بأكمله",
        "role shells from one shared record": "واجهات حسب الدور من سجل مشترك واحد",
        "tools a school juggles after switching": "من الأدوات التي تتعامل معها المدرسة بعد الانتقال",
        "publisher apps with versioned releases": "تطبيقات الناشرين بإصدارات منشورة",
        "community reviews on every listing": "تقييمات المجتمع على كل قائمة",
        "install into a tenant's workspace": "التثبيت في مساحة عمل المؤسسة",
        "SIS vendors with guided import paths": "موردو أنظمة معلومات الطلاب بمسارات استيراد موجّهة",
        "end-to-end encrypted upload of legacy data": "رفع مشفّر من طرف إلى طرف للبيانات القديمة",
        "manual effort versus a hand-built migration": "من الجهد اليدوي مقابل ترحيل يدوي",
    },
    "sw": {
        "time from inquiry to enrolled decision": "muda kutoka ulizo hadi uamuzi wa kujiandikisha",
        "shared pipeline for every applicant stage": "mfumo mmoja kwa kila hatua ya mwombaji",
        "inquiries followed up within a day": "maulizo yaliyofuatiliwa ndani ya siku moja",
        "mobile-money & card rails out of the box": "njia za pesa za simu na kadi tayari bila usanidi",
        "less time on fee reconciliation": "muda mdogo zaidi katika usuluhishi wa ada",
        "to publish a full fee schedule": "kuchapisha ratiba kamili ya ada",
        "record of truth per learner across every shell": "kumbukumbu moja ya ukweli kwa kila mwanafunzi katika kila eneo",
        "duplicate data entry across offices": "ya uingizaji wa data mara mbili kati ya ofisi",
        "tenant-isolated student data": "data za wanafunzi zilizotengwa kwa kila taasisi",
        "saved per teacher each week on roll-keeping": "zilizookolewa kwa kila mwalimu kila wiki kwenye kuweka mahudhurio",
        "to mark a full class register": "kuweka mahudhurio ya darasa zima",
        "lost marks when the network drops": "mahudhurio yaliyopotea wakati mtandao unapokatika",
        "EMIS aggregate pipeline feeding every dashboard": "mfumo wa jumla wa EMIS unaolisha kila dashibodi",
        "time building the termly board report": "ya muda wa kuandaa ripoti ya muhula ya bodi",
        "refresh on enrollment & attendance trends": "kuonyesha upya mwenendo wa uandikishaji na mahudhurio",
        "tenant isolation enforced at the query layer": "utengaji wa taasisi unatekelezwa kwenye safu ya hoja",
        "cross-tenant data paths in the CI gate baseline": "njia za data kati ya taasisi katika msingi wa lango la CI",
        "country governance & policy matrix": "matrix ya utawala na sera kwa kila nchi",
        "thread for slips, attendance and fees": "mfululizo mmoja wa vibali, mahudhurio na ada",
        "inbound calls to the front office": "ya simu zinazoingia kwenye ofisi ya mapokezi",
        "balances and notices stay readable without signal": "salio na taarifa hubaki kusomeka bila mtandao",
        "saved per teacher each week on admin": "zilizookolewa kwa kila mwalimu kila wiki kwenye kazi za kiutawala",
        "place for plans, marks and messages": "sehemu moja ya mipango, alama na ujumbe",
        "marks captured even when the LAN drops": "alama zinarekodiwa hata wakati mtandao wa ndani unapokatika",
        "home for timetable, tasks and results": "eneo la ratiba, kazi na matokeo",
        "on-time assignment submission": "ya kuwasilisha kazi kwa wakati",
        "installable PWA, low-bandwidth friendly": "PWA inayoweza kusakinishwa, rafiki kwa mtandao mdogo",
        "channels — email, SMS and WhatsApp": "njia — barua pepe, SMS na WhatsApp",
        "time to send a whole-school notice": "ya muda wa kutuma taarifa kwa shule nzima",
        "consent honoured on every send": "ridhaa inaheshimiwa kila inapotumwa",
        "manual steps in routine approvals": "ya hatua za mikono katika idhini za kawaida",
        "live progress bus across every shell": "njia ya maendeleo ya moja kwa moja katika kila eneo",
        "stuck-task detection and retry": "kugundua kazi zilizokwama na kujaribu tena",
        "writes lost when the connection drops": "maandishi yaliyopotea wakati muunganisho unapokatika",
        "of core flows usable as an installed PWA": "ya mtiririko muhimu inayoweza kutumika kama PWA iliyosakinishwa",
        "queued work drains when signal returns": "kazi za foleni hukamilika mtandao unaporejea",
        "time to assemble end-of-term report cards": "ya muda wa kuandaa kadi za ripoti za mwisho wa muhula",
        "gradebook feeding cards and analytics": "kitabu cha alama kinacholisha kadi na uchanganuzi",
        "PDF report cards carry each tenant's brand": "kadi za ripoti za PDF zinabeba chapa ya kila taasisi",
        "org-tree roster sync, standards-based": "ulandanishaji wa orodha kwa mti wa shirika, kwa viwango",
        "dynamic checkout alongside mobile-money rails": "malipo yenye nguvu pamoja na njia za pesa za simu",
        "signed delivery with replay protection": "uwasilishaji uliosainiwa na ulinzi dhidi ya kurudiwa",
        "operator console for every tenant": "kibodi ya mwendeshaji kwa kila taasisi",
        "four-eyes approval on sensitive actions": "idhini ya macho manne kwa vitendo nyeti",
        "time to provision a new school": "ya muda wa kuandaa shule mpya",
        "migrations to retune a tenant's config": "uhamishaji wa kurekebisha usanidi wa taasisi",
        "cascade resolves brand, locale and policy": "mtiririko hutatua chapa, lugha na sera",
        "config changes apply without redeploy": "mabadiliko ya usanidi hutumika bila kupeleka upya",
        "operating system for the whole campus": "mfumo wa uendeshaji kwa kampasi nzima",
        "role shells from one shared record": "maeneo kwa majukumu kutoka kumbukumbu moja ya pamoja",
        "tools a school juggles after switching": "ya zana ambazo shule hushughulikia baada ya kuhama",
        "publisher apps with versioned releases": "programu za wachapishaji zenye matoleo yaliyoorodheshwa",
        "community reviews on every listing": "mapitio ya jamii kwa kila orodha",
        "install into a tenant's workspace": "sakinisha katika eneo la kazi la taasisi",
        "SIS vendors with guided import paths": "wauzaji wa SIS wenye njia za uingizaji zilizoongozwa",
        "end-to-end encrypted upload of legacy data": "upakiaji uliosimbwa mwanzo hadi mwisho wa data za zamani",
        "manual effort versus a hand-built migration": "ya juhudi za mikono dhidi ya uhamishaji uliotengenezwa kwa mkono",
    },
    "ha": {
        "time from inquiry to enrolled decision": "lokaci daga tambaya zuwa shawarar shiga",
        "shared pipeline for every applicant stage": "tafarki guda ɗaya don kowane mataki na mai nema",
        "inquiries followed up within a day": "tambayoyin da aka biyo baya cikin rana ɗaya",
        "mobile-money & card rails out of the box": "hanyoyin kuɗin waya da kati a shirye nan take",
        "less time on fee reconciliation": "ƙarancin lokaci kan daidaita kuɗin makaranta",
        "to publish a full fee schedule": "don buga cikakken jadawalin kuɗi",
        "record of truth per learner across every shell": "rikodi guda ɗaya na gaskiya ga kowane ɗalibi a kowane fili",
        "duplicate data entry across offices": "na shigar da bayanai sau biyu tsakanin ofisoshi",
        "tenant-isolated student data": "bayanan ɗalibai keɓaɓɓu ga kowace cibiya",
        "saved per teacher each week on roll-keeping": "da aka ajiye ga kowane malami kowane mako kan ɗaukar halarta",
        "to mark a full class register": "don ɗaukar halartar aji gabaki ɗaya",
        "lost marks when the network drops": "halartar da ta ɓace lokacin da hanyar sadarwa ta yanke",
        "EMIS aggregate pipeline feeding every dashboard": "tafarkin tara EMIS da ke ciyar da kowane dashboard",
        "time building the termly board report": "na lokacin gina rahoton kwamiti na wa'adi",
        "refresh on enrollment & attendance trends": "sabunta yanayin shiga da halarta",
        "tenant isolation enforced at the query layer": "keɓance cibiyoyi ana aiwatar da shi a matakin tambaya",
        "cross-tenant data paths in the CI gate baseline": "hanyoyin bayanai tsakanin cibiyoyi a tushen ƙofar CI",
        "country governance & policy matrix": "tsarin shugabanci da manufofi na ƙasa",
        "thread for slips, attendance and fees": "zare guda ɗaya na takardun izini, halarta da kuɗi",
        "inbound calls to the front office": "na kiran shigowa zuwa ofishin gaba",
        "balances and notices stay readable without signal": "ma'auni da sanarwa suna nan a karanta ba tare da sigina ba",
        "saved per teacher each week on admin": "da aka ajiye ga kowane malami kowane mako kan ayyukan gudanarwa",
        "place for plans, marks and messages": "wuri guda na tsare-tsare, maki da saƙonni",
        "marks captured even when the LAN drops": "an ɗauki maki ko da hanyar sadarwa ta cikin gida ta yanke",
        "home for timetable, tasks and results": "gida na jadawalin lokaci, ayyuka da sakamako",
        "on-time assignment submission": "na ƙaddamar da aikin gida cikin lokaci",
        "installable PWA, low-bandwidth friendly": "PWA mai sakawa, mai dacewa da ƙaramin bandwidth",
        "channels — email, SMS and WhatsApp": "tashoshi — imel, SMS da WhatsApp",
        "time to send a whole-school notice": "na lokacin aika sanarwa ga makaranta gabaki ɗaya",
        "consent honoured on every send": "ana girmama izini a kowane aikawa",
        "manual steps in routine approvals": "na matakan hannu a cikin amincewar yau da kullum",
        "live progress bus across every shell": "bas ɗin ci gaba kai tsaye a kowane fili",
        "stuck-task detection and retry": "gano ayyukan da suka makale da sake gwadawa",
        "writes lost when the connection drops": "rubuce-rubucen da suka ɓace lokacin da haɗin ya yanke",
        "of core flows usable as an installed PWA": "na muhimman tafarki masu amfani a matsayin PWA da aka saka",
        "queued work drains when signal returns": "aikin layi yana kammaluwa lokacin da sigina ya dawo",
        "time to assemble end-of-term report cards": "na lokacin tara katunan rahoton ƙarshen wa'adi",
        "gradebook feeding cards and analytics": "littafin maki da ke ciyar da katuna da bincike",
        "PDF report cards carry each tenant's brand": "katunan rahoto na PDF suna ɗauke da alamar kowace cibiya",
        "org-tree roster sync, standards-based": "daidaita jerin sunaye ta bishiyar ƙungiya, bisa ƙa'idoji",
        "dynamic checkout alongside mobile-money rails": "biyan kuɗi mai ƙarfi tare da hanyoyin kuɗin waya",
        "signed delivery with replay protection": "isar da sako mai sa hannu tare da kariya daga maimaitawa",
        "operator console for every tenant": "na'urar mai aiki ga kowace cibiya",
        "four-eyes approval on sensitive actions": "amincewar idanu huɗu kan ayyuka masu mahimmanci",
        "time to provision a new school": "na lokacin shirya sabuwar makaranta",
        "migrations to retune a tenant's config": "ƙaura don sake daidaita saitin cibiya",
        "cascade resolves brand, locale and policy": "jerin yana warware alama, harshe da manufa",
        "config changes apply without redeploy": "canje-canjen saiti suna aiki ba tare da sake turawa ba",
        "operating system for the whole campus": "tsarin aiki ga dukan harabar",
        "role shells from one shared record": "filaye bisa matsayi daga rikodi ɗaya da aka raba",
        "tools a school juggles after switching": "na kayan aikin da makaranta ke sarrafawa bayan canjawa",
        "publisher apps with versioned releases": "manhajojin masu bugawa tare da fitarwa masu sigogi",
        "community reviews on every listing": "sharhin al'umma kan kowane jeri",
        "install into a tenant's workspace": "saka cikin filin aikin cibiya",
        "SIS vendors with guided import paths": "masu sayar da SIS tare da hanyoyin shigarwa masu jagora",
        "end-to-end encrypted upload of legacy data": "loda bayanan tsofaffi cikin ɓoye daga ƙarshe zuwa ƙarshe",
        "manual effort versus a hand-built migration": "na ƙoƙarin hannu game da ƙaura da aka gina da hannu",
    },
    "yo": {
        "time from inquiry to enrolled decision": "àkókò láti ìbéèrè dé ìpinnu ìforúkọsílẹ̀",
        "shared pipeline for every applicant stage": "ọ̀nà kan ṣoṣo fún gbogbo ìpele olùbéèrè",
        "inquiries followed up within a day": "àwọn ìbéèrè tí a tẹ̀lé láàrin ọjọ́ kan",
        "mobile-money & card rails out of the box": "àwọn ọ̀nà owó fóònù àti káàdì tí ó ti ṣetán",
        "less time on fee reconciliation": "àkókò díẹ̀ sí i lórí ìbámu owó ilé-ìwé",
        "to publish a full fee schedule": "láti tẹ àkójọ owó ní kíkún jáde",
        "record of truth per learner across every shell": "àkọsílẹ̀ òtítọ́ kan fún akẹ́kọ̀ọ́ kọ̀ọ̀kan ní gbogbo ojú-ìwé",
        "duplicate data entry across offices": "ti ìtẹ̀wọlé dátà lẹ́ẹ̀mejì láàrin àwọn ọ́fíìsì",
        "tenant-isolated student data": "dátà akẹ́kọ̀ọ́ tí a yà sọ́tọ̀ fún ilé-ẹ̀kọ́ kọ̀ọ̀kan",
        "saved per teacher each week on roll-keeping": "tí a fipamọ́ fún olùkọ́ kọ̀ọ̀kan lọ́sọ̀ọ̀sẹ̀ lórí ìpàdé wíwà",
        "to mark a full class register": "láti ṣàmì sí ìwé ìpàdé kíláàsì kíkún",
        "lost marks when the network drops": "ìpàdé tí ó sọnù nígbà tí nẹ́tíwọ́kì bá já",
        "EMIS aggregate pipeline feeding every dashboard": "ọ̀nà àkójọpọ̀ EMIS tí ń bọ́ gbogbo pátákó",
        "time building the termly board report": "ti àkókò kíkọ ìròyìn ìgbìmọ̀ ní oṣù mẹ́ta",
        "refresh on enrollment & attendance trends": "ìmúdojúìwọn lórí àṣà ìforúkọsílẹ̀ àti wíwà",
        "tenant isolation enforced at the query layer": "ìyàsọ́tọ̀ ilé-ẹ̀kọ́ tí a fi múlẹ̀ ní ìpele ìbéèrè",
        "cross-tenant data paths in the CI gate baseline": "àwọn ọ̀nà dátà láàrin ilé-ẹ̀kọ́ ní ìpìlẹ̀ ẹnubodè CI",
        "country governance & policy matrix": "matrix ìṣàkóso àti ìlànà orílẹ̀-èdè",
        "thread for slips, attendance and fees": "ìtẹ̀lé kan fún àwọn ìwé àṣẹ, wíwà àti owó",
        "inbound calls to the front office": "ti àwọn ìpè tí ń wọlé sí ọ́fíìsì iwájú",
        "balances and notices stay readable without signal": "ìyókù àti ìkìlọ̀ wà ní kíkà láìsí sígínà",
        "saved per teacher each week on admin": "tí a fipamọ́ fún olùkọ́ kọ̀ọ̀kan lọ́sọ̀ọ̀sẹ̀ lórí iṣẹ́ àkóso",
        "place for plans, marks and messages": "ibì kan fún àwọn ètò, àmì àti ìránṣẹ́",
        "marks captured even when the LAN drops": "a kọ àmì sílẹ̀ kódà nígbà tí nẹ́tíwọ́kì agbègbè bá já",
        "home for timetable, tasks and results": "ilé fún àkókò-ìṣe, iṣẹ́ àti àbájáde",
        "on-time assignment submission": "ti ìfisílẹ̀ iṣẹ́-àyànfúnni lákòókò",
        "installable PWA, low-bandwidth friendly": "PWA tí a lè fi sórí ẹrọ, ó bá bandiwidi kékeré mu",
        "channels — email, SMS and WhatsApp": "àwọn ọ̀nà — ímeèlì, SMS àti WhatsApp",
        "time to send a whole-school notice": "ti àkókò láti fi ìkìlọ̀ ránṣẹ́ sí gbogbo ilé-ìwé",
        "consent honoured on every send": "a bọ̀wọ̀ fún ìfọwọ́sí ní gbogbo ìfiránṣẹ́",
        "manual steps in routine approvals": "ti àwọn ìgbésẹ̀ ọwọ́ nínú àwọn ìfọwọ́sí déédéé",
        "live progress bus across every shell": "ọ̀nà ìtẹ̀síwájú tààrà ní gbogbo ojú-ìwé",
        "stuck-task detection and retry": "ṣíṣàwárí iṣẹ́ tí ó dí àti ìgbìyànjú lẹ́ẹ̀kansí",
        "writes lost when the connection drops": "àwọn àkọsílẹ̀ tí ó sọnù nígbà tí ìsopọ̀ bá já",
        "of core flows usable as an installed PWA": "ti àwọn ọ̀nà pàtàkì tí a lè lò gẹ́gẹ́ bí PWA tí a fi sórí ẹrọ",
        "queued work drains when signal returns": "iṣẹ́ tí ó wà ní ìlà ń parí nígbà tí sígínà bá padà",
        "time to assemble end-of-term report cards": "ti àkókò láti kó àwọn káàdì ìròyìn òpin-ìgbà jọ",
        "gradebook feeding cards and analytics": "ìwé àmì tí ń bọ́ àwọn káàdì àti ìtúpalẹ̀",
        "PDF report cards carry each tenant's brand": "àwọn káàdì ìròyìn PDF gbé àmì ilé-ẹ̀kọ́ kọ̀ọ̀kan",
        "org-tree roster sync, standards-based": "ìmúṣiṣẹ́pọ̀ àkójọ nípa igi-àjọ, lórí àwọn ìlànà",
        "dynamic checkout alongside mobile-money rails": "ìsanwó alágbára pẹ̀lú àwọn ọ̀nà owó fóònù",
        "signed delivery with replay protection": "ìfijíṣẹ́ tí a fọwọ́sí pẹ̀lú ààbò lòdì sí ìṣàtúnṣe",
        "operator console for every tenant": "ìkáwé olùṣiṣẹ́ fún ilé-ẹ̀kọ́ kọ̀ọ̀kan",
        "four-eyes approval on sensitive actions": "ìfọwọ́sí ojú mẹ́rin lórí àwọn ìṣe ìfàmọ́ra",
        "time to provision a new school": "ti àkókò láti pèsè ilé-ìwé tuntun",
        "migrations to retune a tenant's config": "àwọn ìṣílọ́ láti tún ìtò ilé-ẹ̀kọ́ ṣe",
        "cascade resolves brand, locale and policy": "ìṣàn yanjú àmì, èdè àti ìlànà",
        "config changes apply without redeploy": "àwọn ìyípadà ìtò ń ṣiṣẹ́ láìsí ìtúngbé-jáde",
        "operating system for the whole campus": "ètò ìṣiṣẹ́ fún gbogbo ọgbà-ẹ̀kọ́",
        "role shells from one shared record": "àwọn ojú-ìwé ipa láti inú àkọsílẹ̀ pínpín kan",
        "tools a school juggles after switching": "ti àwọn irinṣẹ́ tí ilé-ìwé ń ṣàkóso lẹ́yìn ìyípadà",
        "publisher apps with versioned releases": "àwọn ohun-èlò akéde pẹ̀lú àwọn ìtújáde onírúurú",
        "community reviews on every listing": "àwọn àgbéyẹ̀wò àwùjọ lórí àkójọ kọ̀ọ̀kan",
        "install into a tenant's workspace": "fi sórí ẹrọ sínú àyè-iṣẹ́ ilé-ẹ̀kọ́",
        "SIS vendors with guided import paths": "àwọn olùtà SIS pẹ̀lú àwọn ọ̀nà àgbéwọlé aṣáájú",
        "end-to-end encrypted upload of legacy data": "ìgbéwọlé dátà àtijọ́ tí a fi pamọ́ láti ìbẹ̀rẹ̀ dé òpin",
        "manual effort versus a hand-built migration": "ti ìsapá ọwọ́ ní ìfiwéra pẹ̀lú ìṣílọ́ tí a kọ́ ní ọwọ́",
    },
}


def _normalize_lang(lang: str | None) -> str:
    """Normalize a language code to a supported base code, defaulting to ``en``.

    Tolerates ``None``, regional variants (``pt-BR`` → ``pt``), and case.
    Unknown languages fall back to ``en``.
    """
    base = (lang or "en").strip().lower().replace("_", "-").split("-")[0]
    return base if base in SUPPORTED_LANGS else "en"


def _t_label(label: str, lang: str) -> str:
    """Translate a stat ``label`` for ``lang``, English-fallback on miss."""
    if lang == "en":
        return label
    return _LABEL_TRANSLATIONS.get(lang, {}).get(label, label)


def _t_basis(basis: str, lang: str) -> str:
    """Translate a ``basis`` provenance string for ``lang``, English-fallback."""
    if lang == "en":
        return basis
    return _BASIS_TRANSLATIONS.get(lang, {}).get(basis, basis)


def outcome_stats_for_slug(slug: str, lang: str = "en") -> list[OutcomeStat]:
    """Return the outcome stats for ``slug`` (case-insensitive).

    ``lang`` is an optional language code (``en``/``fr``/``es``/``pt``/``ar``
    plus best-effort ``sw``/``ha``/``yo``). The ``value`` (numbers/percentages)
    is never translated; only the human-readable ``label`` and ``basis`` text
    is localized, with English as the fallback for any missing translation or
    unknown language.

    Returns an empty list when the slug is unknown or falsy.
    """

    if not slug:
        return []
    stats = OUTCOME_STATS.get(slug.strip().lower(), [])
    norm_lang = _normalize_lang(lang)
    if norm_lang == "en":
        # Return copies so callers can never mutate the registry.
        return [dict(stat) for stat in stats]  # type: ignore[misc]
    return [
        {
            "value": stat["value"],
            "label": _t_label(stat["label"], norm_lang),
            "basis": _t_basis(stat["basis"], norm_lang),
        }
        for stat in stats
    ]
