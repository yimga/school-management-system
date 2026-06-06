"""Single source of truth for marketing product tours.

A product tour is an ordered list of "frames" that, played back in the
``_product_tour.html`` component, walk a marketing visitor through a faithful
mock of the real RunMyCampus workspace for a given platform feature. Each frame
declares a stable ``key``, a human ``caption``, a focusing ``tooltip`` callout,
and a ``ui_kind`` enum string that the template switches on to render the
matching faithful ``.rmc-*`` UI block (a roster data-table, an attendance grid,
a fee ledger, a message composer, an admissions pipeline, a gradebook).

This module is pure data + a single lookup helper — no Django imports — so it is
trivially unit-testable with ``SimpleTestCase`` and importable from the
marketing view without side effects.
"""

from __future__ import annotations

from typing import Optional, TypedDict


class TourFrame(TypedDict):
    """One step in a guided product tour."""

    key: str
    caption: str
    tooltip: str
    ui_kind: str


class ProductTour(TypedDict):
    """A resolved tour: the slug plus its ordered frames."""

    slug: str
    frames: list[TourFrame]


# Stable ``ui_kind`` enum values the template partial switches on. Keeping them
# centralised means the SOT and the renderer can never drift on a typo.
UI_KIND_ROSTER_TABLE = "roster_table"
UI_KIND_ATTENDANCE_GRID = "attendance_grid"
UI_KIND_FEE_LEDGER = "fee_ledger"
UI_KIND_MESSAGE_COMPOSER = "message_composer"
UI_KIND_ADMISSIONS_PIPELINE = "admissions_pipeline"
UI_KIND_GRADEBOOK = "gradebook"
UI_KIND_METRIC_OVERVIEW = "metric_overview"


# Flagship platform slugs → ordered tour frames. 3–5 frames each.
_PRODUCT_TOURS: dict[str, list[TourFrame]] = {
    "platform-student-information-system": [
        {
            "key": "sis-overview",
            "caption": "The student information dashboard the moment you sign in.",
            "tooltip": "Live enrolment, attendance and standing — one glance.",
            "ui_kind": UI_KIND_METRIC_OVERVIEW,
        },
        {
            "key": "sis-roster",
            "caption": "Every learner in a sortable, filterable roster.",
            "tooltip": "Click any row to open the full student record.",
            "ui_kind": UI_KIND_ROSTER_TABLE,
        },
        {
            "key": "sis-attendance",
            "caption": "Daily attendance captured against the same roster.",
            "tooltip": "Mark a whole class present in two taps.",
            "ui_kind": UI_KIND_ATTENDANCE_GRID,
        },
        {
            "key": "sis-grades",
            "caption": "Academic standing rolls up into report cards.",
            "tooltip": "Grades flow straight to guardians.",
            "ui_kind": UI_KIND_GRADEBOOK,
        },
    ],
    "platform-attendance": [
        {
            "key": "att-grid",
            "caption": "The class attendance grid for today's register.",
            "tooltip": "Tap a cell to cycle present, absent or late.",
            "ui_kind": UI_KIND_ATTENDANCE_GRID,
        },
        {
            "key": "att-roster",
            "caption": "Attendance is anchored to the live class roster.",
            "tooltip": "No re-keying — the roster is the source of truth.",
            "ui_kind": UI_KIND_ROSTER_TABLE,
        },
        {
            "key": "att-summary",
            "caption": "Attendance rates summarise into a daily snapshot.",
            "tooltip": "Spot at-risk learners before they fall behind.",
            "ui_kind": UI_KIND_METRIC_OVERVIEW,
        },
    ],
    "platform-fees-payments": [
        {
            "key": "fees-overview",
            "caption": "Collections and outstanding balances at a glance.",
            "tooltip": "Know exactly what's billed, paid and overdue.",
            "ui_kind": UI_KIND_METRIC_OVERVIEW,
        },
        {
            "key": "fees-ledger",
            "caption": "A per-student fee ledger with every line item.",
            "tooltip": "Decimal-accurate — no rounding surprises.",
            "ui_kind": UI_KIND_FEE_LEDGER,
        },
        {
            "key": "fees-reminder",
            "caption": "Send a payment reminder without leaving the ledger.",
            "tooltip": "Reminders go by the family's preferred channel.",
            "ui_kind": UI_KIND_MESSAGE_COMPOSER,
        },
    ],
    "platform-communications": [
        {
            "key": "comms-composer",
            "caption": "Compose a message to a class, year group or whole school.",
            "tooltip": "One composer, every channel — email, SMS, push.",
            "ui_kind": UI_KIND_MESSAGE_COMPOSER,
        },
        {
            "key": "comms-audience",
            "caption": "Pick the audience straight from the live roster.",
            "tooltip": "Target by class, role or custom segment.",
            "ui_kind": UI_KIND_ROSTER_TABLE,
        },
        {
            "key": "comms-delivery",
            "caption": "Track delivery and open rates after you send.",
            "tooltip": "See who received and read each message.",
            "ui_kind": UI_KIND_METRIC_OVERVIEW,
        },
    ],
    "platform-admissions": [
        {
            "key": "adm-pipeline",
            "caption": "The admissions pipeline from enquiry to enrolled.",
            "tooltip": "Drag an applicant to advance their stage.",
            "ui_kind": UI_KIND_ADMISSIONS_PIPELINE,
        },
        {
            "key": "adm-applicants",
            "caption": "Every applicant in a reviewable list.",
            "tooltip": "Open a record to see documents and decisions.",
            "ui_kind": UI_KIND_ROSTER_TABLE,
        },
        {
            "key": "adm-offer",
            "caption": "Send an offer or decision email in one click.",
            "tooltip": "Templated, branded, and logged automatically.",
            "ui_kind": UI_KIND_MESSAGE_COMPOSER,
        },
        {
            "key": "adm-funnel",
            "caption": "Conversion across the funnel, stage by stage.",
            "tooltip": "See where applicants drop off.",
            "ui_kind": UI_KIND_METRIC_OVERVIEW,
        },
    ],
    "platform-grading-report-cards": [
        {
            "key": "grade-book",
            "caption": "The gradebook for a class and assessment.",
            "tooltip": "Enter marks; weighted totals compute live.",
            "ui_kind": UI_KIND_GRADEBOOK,
        },
        {
            "key": "grade-roster",
            "caption": "Grades sit against the same enrolled roster.",
            "tooltip": "One learner, one continuous academic record.",
            "ui_kind": UI_KIND_ROSTER_TABLE,
        },
        {
            "key": "grade-distribution",
            "caption": "Grade distribution and cohort averages.",
            "tooltip": "Spot the assessment that needs a re-teach.",
            "ui_kind": UI_KIND_METRIC_OVERVIEW,
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
# any missing language or string. Only the human-readable ``caption`` and
# ``tooltip`` text is translated; ``key`` and ``ui_kind`` are stable enums and
# are never translated.
#
# Priority locales: en (source), fr, es, pt, ar, plus best-effort sw (Swahili),
# ha (Hausa), yo (Yoruba) for the African markets the rails target.

SUPPORTED_LANGS: tuple[str, ...] = ("en", "fr", "es", "pt", "ar", "sw", "ha", "yo")

# caption + tooltip English source strings → per-language translation.
_TOUR_TEXT_TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {
        "The student information dashboard the moment you sign in.": "Le tableau de bord des informations élèves dès votre connexion.",
        "Live enrolment, attendance and standing — one glance.": "Inscriptions, présences et situation en direct — d'un coup d'œil.",
        "Every learner in a sortable, filterable roster.": "Chaque élève dans une liste triable et filtrable.",
        "Click any row to open the full student record.": "Cliquez sur une ligne pour ouvrir le dossier complet.",
        "Daily attendance captured against the same roster.": "Présences quotidiennes saisies sur la même liste.",
        "Mark a whole class present in two taps.": "Marquez toute une classe présente en deux clics.",
        "Academic standing rolls up into report cards.": "La situation scolaire se reporte sur les bulletins.",
        "Grades flow straight to guardians.": "Les notes parviennent directement aux responsables.",
        "The class attendance grid for today's register.": "La grille de présence de la classe pour l'appel du jour.",
        "Tap a cell to cycle present, absent or late.": "Touchez une cellule pour basculer présent, absent ou en retard.",
        "Attendance is anchored to the live class roster.": "La présence est ancrée à la liste de classe en direct.",
        "No re-keying — the roster is the source of truth.": "Aucune ressaisie — la liste est la source de vérité.",
        "Attendance rates summarise into a daily snapshot.": "Les taux de présence se résument en un instantané quotidien.",
        "Spot at-risk learners before they fall behind.": "Repérez les élèves à risque avant qu'ils ne décrochent.",
        "Collections and outstanding balances at a glance.": "Recouvrements et soldes dus en un coup d'œil.",
        "Know exactly what's billed, paid and overdue.": "Sachez exactement ce qui est facturé, payé et en retard.",
        "A per-student fee ledger with every line item.": "Un grand livre de frais par élève avec chaque ligne.",
        "Decimal-accurate — no rounding surprises.": "Précision décimale — aucune surprise d'arrondi.",
        "Send a payment reminder without leaving the ledger.": "Envoyez un rappel de paiement sans quitter le grand livre.",
        "Reminders go by the family's preferred channel.": "Les rappels passent par le canal préféré de la famille.",
        "Compose a message to a class, year group or whole school.": "Composez un message pour une classe, un niveau ou toute l'école.",
        "One composer, every channel — email, SMS, push.": "Un seul éditeur, tous les canaux — e-mail, SMS, notification.",
        "Pick the audience straight from the live roster.": "Choisissez l'audience directement dans la liste en direct.",
        "Target by class, role or custom segment.": "Ciblez par classe, rôle ou segment personnalisé.",
        "Track delivery and open rates after you send.": "Suivez la livraison et les taux d'ouverture après l'envoi.",
        "See who received and read each message.": "Voyez qui a reçu et lu chaque message.",
        "The admissions pipeline from enquiry to enrolled.": "Le pipeline d'admissions, de la demande à l'inscription.",
        "Drag an applicant to advance their stage.": "Glissez un candidat pour faire avancer son étape.",
        "Every applicant in a reviewable list.": "Chaque candidat dans une liste à examiner.",
        "Open a record to see documents and decisions.": "Ouvrez un dossier pour voir documents et décisions.",
        "Send an offer or decision email in one click.": "Envoyez un e-mail d'offre ou de décision en un clic.",
        "Templated, branded, and logged automatically.": "Avec modèle, à votre marque, et journalisé automatiquement.",
        "Conversion across the funnel, stage by stage.": "La conversion tout au long de l'entonnoir, étape par étape.",
        "See where applicants drop off.": "Voyez où les candidats abandonnent.",
        "The gradebook for a class and assessment.": "Le carnet de notes pour une classe et une évaluation.",
        "Enter marks; weighted totals compute live.": "Saisissez les notes ; les totaux pondérés se calculent en direct.",
        "Grades sit against the same enrolled roster.": "Les notes reposent sur la même liste d'inscrits.",
        "One learner, one continuous academic record.": "Un élève, un dossier scolaire continu.",
        "Grade distribution and cohort averages.": "Répartition des notes et moyennes de cohorte.",
        "Spot the assessment that needs a re-teach.": "Repérez l'évaluation à reprendre en classe.",
    },
    "es": {
        "The student information dashboard the moment you sign in.": "El panel de información del estudiante en cuanto inicias sesión.",
        "Live enrolment, attendance and standing — one glance.": "Matrícula, asistencia y situación en vivo — de un vistazo.",
        "Every learner in a sortable, filterable roster.": "Cada estudiante en una lista ordenable y filtrable.",
        "Click any row to open the full student record.": "Haz clic en una fila para abrir el expediente completo.",
        "Daily attendance captured against the same roster.": "Asistencia diaria registrada sobre la misma lista.",
        "Mark a whole class present in two taps.": "Marca a toda una clase presente en dos toques.",
        "Academic standing rolls up into report cards.": "La situación académica se refleja en los boletines.",
        "Grades flow straight to guardians.": "Las calificaciones llegan directo a los tutores.",
        "The class attendance grid for today's register.": "La cuadrícula de asistencia de la clase para el pase de hoy.",
        "Tap a cell to cycle present, absent or late.": "Toca una celda para alternar presente, ausente o tarde.",
        "Attendance is anchored to the live class roster.": "La asistencia se ancla a la lista de clase en vivo.",
        "No re-keying — the roster is the source of truth.": "Sin volver a teclear — la lista es la fuente de verdad.",
        "Attendance rates summarise into a daily snapshot.": "Las tasas de asistencia se resumen en una vista diaria.",
        "Spot at-risk learners before they fall behind.": "Detecta a los estudiantes en riesgo antes de que se atrasen.",
        "Collections and outstanding balances at a glance.": "Cobros y saldos pendientes de un vistazo.",
        "Know exactly what's billed, paid and overdue.": "Sabe exactamente qué está facturado, pagado y vencido.",
        "A per-student fee ledger with every line item.": "Un libro de cuotas por estudiante con cada partida.",
        "Decimal-accurate — no rounding surprises.": "Precisión decimal — sin sorpresas de redondeo.",
        "Send a payment reminder without leaving the ledger.": "Envía un recordatorio de pago sin salir del libro.",
        "Reminders go by the family's preferred channel.": "Los recordatorios van por el canal preferido de la familia.",
        "Compose a message to a class, year group or whole school.": "Redacta un mensaje para una clase, un curso o toda la escuela.",
        "One composer, every channel — email, SMS, push.": "Un solo editor, todos los canales — correo, SMS, notificación.",
        "Pick the audience straight from the live roster.": "Elige la audiencia directo desde la lista en vivo.",
        "Target by class, role or custom segment.": "Segmenta por clase, rol o segmento personalizado.",
        "Track delivery and open rates after you send.": "Rastrea la entrega y las tasas de apertura tras enviar.",
        "See who received and read each message.": "Ve quién recibió y leyó cada mensaje.",
        "The admissions pipeline from enquiry to enrolled.": "El flujo de admisiones, de la consulta a la matrícula.",
        "Drag an applicant to advance their stage.": "Arrastra a un solicitante para avanzar su etapa.",
        "Every applicant in a reviewable list.": "Cada solicitante en una lista para revisar.",
        "Open a record to see documents and decisions.": "Abre un expediente para ver documentos y decisiones.",
        "Send an offer or decision email in one click.": "Envía un correo de oferta o decisión con un clic.",
        "Templated, branded, and logged automatically.": "Con plantilla, con tu marca y registrado automáticamente.",
        "Conversion across the funnel, stage by stage.": "Conversión a lo largo del embudo, etapa por etapa.",
        "See where applicants drop off.": "Ve dónde abandonan los solicitantes.",
        "The gradebook for a class and assessment.": "La libreta de calificaciones para una clase y evaluación.",
        "Enter marks; weighted totals compute live.": "Ingresa notas; los totales ponderados se calculan en vivo.",
        "Grades sit against the same enrolled roster.": "Las notas se asientan sobre la misma lista de matriculados.",
        "One learner, one continuous academic record.": "Un estudiante, un expediente académico continuo.",
        "Grade distribution and cohort averages.": "Distribución de notas y promedios de cohorte.",
        "Spot the assessment that needs a re-teach.": "Detecta la evaluación que necesita repaso.",
    },
    "pt": {
        "The student information dashboard the moment you sign in.": "O painel de informações do aluno assim que você entra.",
        "Live enrolment, attendance and standing — one glance.": "Matrícula, presença e situação ao vivo — num relance.",
        "Every learner in a sortable, filterable roster.": "Cada aluno em uma lista ordenável e filtrável.",
        "Click any row to open the full student record.": "Clique em qualquer linha para abrir o registro completo.",
        "Daily attendance captured against the same roster.": "Presença diária registrada sobre a mesma lista.",
        "Mark a whole class present in two taps.": "Marque uma turma inteira como presente em dois toques.",
        "Academic standing rolls up into report cards.": "A situação acadêmica se reflete nos boletins.",
        "Grades flow straight to guardians.": "As notas chegam direto aos responsáveis.",
        "The class attendance grid for today's register.": "A grade de presença da turma para a chamada de hoje.",
        "Tap a cell to cycle present, absent or late.": "Toque numa célula para alternar presente, ausente ou atrasado.",
        "Attendance is anchored to the live class roster.": "A presença está ancorada na lista de turma ao vivo.",
        "No re-keying — the roster is the source of truth.": "Sem redigitar — a lista é a fonte da verdade.",
        "Attendance rates summarise into a daily snapshot.": "As taxas de presença se resumem num panorama diário.",
        "Spot at-risk learners before they fall behind.": "Identifique alunos em risco antes que fiquem para trás.",
        "Collections and outstanding balances at a glance.": "Cobranças e saldos em aberto num relance.",
        "Know exactly what's billed, paid and overdue.": "Saiba exatamente o que está faturado, pago e vencido.",
        "A per-student fee ledger with every line item.": "Um livro de taxas por aluno com cada item.",
        "Decimal-accurate — no rounding surprises.": "Precisão decimal — sem surpresas de arredondamento.",
        "Send a payment reminder without leaving the ledger.": "Envie um lembrete de pagamento sem sair do livro.",
        "Reminders go by the family's preferred channel.": "Os lembretes vão pelo canal preferido da família.",
        "Compose a message to a class, year group or whole school.": "Escreva uma mensagem para uma turma, série ou toda a escola.",
        "One composer, every channel — email, SMS, push.": "Um editor, todos os canais — e-mail, SMS, notificação.",
        "Pick the audience straight from the live roster.": "Escolha o público direto da lista ao vivo.",
        "Target by class, role or custom segment.": "Segmente por turma, função ou segmento personalizado.",
        "Track delivery and open rates after you send.": "Acompanhe entrega e taxas de abertura após enviar.",
        "See who received and read each message.": "Veja quem recebeu e leu cada mensagem.",
        "The admissions pipeline from enquiry to enrolled.": "O funil de admissões, da consulta à matrícula.",
        "Drag an applicant to advance their stage.": "Arraste um candidato para avançar sua etapa.",
        "Every applicant in a reviewable list.": "Cada candidato em uma lista para revisão.",
        "Open a record to see documents and decisions.": "Abra um registro para ver documentos e decisões.",
        "Send an offer or decision email in one click.": "Envie um e-mail de oferta ou decisão com um clique.",
        "Templated, branded, and logged automatically.": "Com modelo, com sua marca e registrado automaticamente.",
        "Conversion across the funnel, stage by stage.": "Conversão ao longo do funil, etapa por etapa.",
        "See where applicants drop off.": "Veja onde os candidatos desistem.",
        "The gradebook for a class and assessment.": "O diário de notas para uma turma e avaliação.",
        "Enter marks; weighted totals compute live.": "Insira notas; os totais ponderados calculam ao vivo.",
        "Grades sit against the same enrolled roster.": "As notas ficam sobre a mesma lista de matriculados.",
        "One learner, one continuous academic record.": "Um aluno, um registro acadêmico contínuo.",
        "Grade distribution and cohort averages.": "Distribuição de notas e médias da turma.",
        "Spot the assessment that needs a re-teach.": "Identifique a avaliação que precisa ser revista.",
    },
    "ar": {
        "The student information dashboard the moment you sign in.": "لوحة معلومات الطالب لحظة تسجيل دخولك.",
        "Live enrolment, attendance and standing — one glance.": "التسجيل والحضور والوضع مباشرةً — بنظرة واحدة.",
        "Every learner in a sortable, filterable roster.": "كل متعلم في قائمة قابلة للفرز والتصفية.",
        "Click any row to open the full student record.": "انقر أي صف لفتح سجل الطالب الكامل.",
        "Daily attendance captured against the same roster.": "الحضور اليومي يُسجَّل على القائمة نفسها.",
        "Mark a whole class present in two taps.": "سجّل حضور صف كامل بنقرتين.",
        "Academic standing rolls up into report cards.": "الوضع الأكاديمي يُجمَّع في بطاقات التقارير.",
        "Grades flow straight to guardians.": "تصل الدرجات مباشرةً إلى أولياء الأمور.",
        "The class attendance grid for today's register.": "شبكة حضور الصف لتسجيل اليوم.",
        "Tap a cell to cycle present, absent or late.": "انقر خلية للتبديل بين حاضر وغائب ومتأخر.",
        "Attendance is anchored to the live class roster.": "الحضور مرتبط بقائمة الصف المباشرة.",
        "No re-keying — the roster is the source of truth.": "لا إعادة إدخال — القائمة هي مصدر الحقيقة.",
        "Attendance rates summarise into a daily snapshot.": "معدلات الحضور تتلخّص في لمحة يومية.",
        "Spot at-risk learners before they fall behind.": "اكتشف المتعلمين المعرّضين للخطر قبل تأخرهم.",
        "Collections and outstanding balances at a glance.": "التحصيلات والأرصدة المستحقة بنظرة واحدة.",
        "Know exactly what's billed, paid and overdue.": "اعرف بالضبط ما هو مفوتر ومدفوع ومتأخر.",
        "A per-student fee ledger with every line item.": "دفتر رسوم لكل طالب بكل بند.",
        "Decimal-accurate — no rounding surprises.": "دقة عشرية — بلا مفاجآت تقريب.",
        "Send a payment reminder without leaving the ledger.": "أرسل تذكير دفع دون مغادرة الدفتر.",
        "Reminders go by the family's preferred channel.": "تُرسَل التذكيرات عبر القناة المفضّلة للأسرة.",
        "Compose a message to a class, year group or whole school.": "اكتب رسالة لصف أو دفعة أو المدرسة كاملةً.",
        "One composer, every channel — email, SMS, push.": "محرّر واحد، كل القنوات — بريد ورسائل قصيرة وإشعارات.",
        "Pick the audience straight from the live roster.": "اختر الجمهور مباشرةً من القائمة المباشرة.",
        "Target by class, role or custom segment.": "استهدف حسب الصف أو الدور أو شريحة مخصّصة.",
        "Track delivery and open rates after you send.": "تتبّع التسليم ومعدلات الفتح بعد الإرسال.",
        "See who received and read each message.": "اطّلع على من استلم وقرأ كل رسالة.",
        "The admissions pipeline from enquiry to enrolled.": "مسار القبول من الاستفسار إلى التسجيل.",
        "Drag an applicant to advance their stage.": "اسحب متقدماً لتقديم مرحلته.",
        "Every applicant in a reviewable list.": "كل متقدم في قائمة قابلة للمراجعة.",
        "Open a record to see documents and decisions.": "افتح سجلاً لرؤية المستندات والقرارات.",
        "Send an offer or decision email in one click.": "أرسل بريد عرض أو قرار بنقرة واحدة.",
        "Templated, branded, and logged automatically.": "بقالب وبعلامتك ومُسجَّل تلقائياً.",
        "Conversion across the funnel, stage by stage.": "التحويل عبر المسار، مرحلة بمرحلة.",
        "See where applicants drop off.": "اطّلع على أين ينسحب المتقدمون.",
        "The gradebook for a class and assessment.": "سجل الدرجات لصف وتقييم.",
        "Enter marks; weighted totals compute live.": "أدخل الدرجات؛ تُحسَب المجاميع المرجّحة مباشرةً.",
        "Grades sit against the same enrolled roster.": "الدرجات ترتكز على قائمة المسجّلين نفسها.",
        "One learner, one continuous academic record.": "متعلم واحد، سجل أكاديمي متواصل واحد.",
        "Grade distribution and cohort averages.": "توزيع الدرجات ومتوسطات الدفعة.",
        "Spot the assessment that needs a re-teach.": "اكتشف التقييم الذي يحتاج إعادة شرح.",
    },
    "sw": {
        "The student information dashboard the moment you sign in.": "Dashibodi ya taarifa za mwanafunzi mara tu unapoingia.",
        "Live enrolment, attendance and standing — one glance.": "Uandikishaji, mahudhurio na hali moja kwa moja — kwa mtazamo mmoja.",
        "Every learner in a sortable, filterable roster.": "Kila mwanafunzi katika orodha inayopangika na kuchujika.",
        "Click any row to open the full student record.": "Bofya safu yoyote kufungua rekodi kamili ya mwanafunzi.",
        "Daily attendance captured against the same roster.": "Mahudhurio ya kila siku yanarekodiwa kwenye orodha ile ile.",
        "Mark a whole class present in two taps.": "Weka darasa zima kuwa wapo kwa mibofyo miwili.",
        "Academic standing rolls up into report cards.": "Hali ya kitaaluma inajumlishwa katika kadi za ripoti.",
        "Grades flow straight to guardians.": "Alama zinawafikia walezi moja kwa moja.",
        "The class attendance grid for today's register.": "Gridi ya mahudhurio ya darasa kwa orodha ya leo.",
        "Tap a cell to cycle present, absent or late.": "Gusa kisanduku kuzungusha yupo, hayupo au amechelewa.",
        "Attendance is anchored to the live class roster.": "Mahudhurio yameunganishwa na orodha ya darasa moja kwa moja.",
        "No re-keying — the roster is the source of truth.": "Hakuna kuandika tena — orodha ndiyo chanzo cha ukweli.",
        "Attendance rates summarise into a daily snapshot.": "Viwango vya mahudhurio vinajumlishwa katika muhtasari wa kila siku.",
        "Spot at-risk learners before they fall behind.": "Tambua wanafunzi walio hatarini kabla hawajabaki nyuma.",
        "Collections and outstanding balances at a glance.": "Makusanyo na salio linalodaiwa kwa mtazamo mmoja.",
        "Know exactly what's billed, paid and overdue.": "Jua hasa kilichotozwa, kilicholipwa na kilichochelewa.",
        "A per-student fee ledger with every line item.": "Daftari la ada kwa kila mwanafunzi lenye kila kipengele.",
        "Decimal-accurate — no rounding surprises.": "Usahihi wa desimali — hakuna mshangao wa mzunguko.",
        "Send a payment reminder without leaving the ledger.": "Tuma ukumbusho wa malipo bila kuondoka kwenye daftari.",
        "Reminders go by the family's preferred channel.": "Vikumbusho hupita kupitia njia inayopendelewa na familia.",
        "Compose a message to a class, year group or whole school.": "Andika ujumbe kwa darasa, kundi la mwaka au shule nzima.",
        "One composer, every channel — email, SMS, push.": "Mwandishi mmoja, kila njia — barua pepe, SMS, arifa.",
        "Pick the audience straight from the live roster.": "Chagua hadhira moja kwa moja kutoka orodha hai.",
        "Target by class, role or custom segment.": "Lenga kwa darasa, jukumu au sehemu maalum.",
        "Track delivery and open rates after you send.": "Fuatilia uwasilishaji na viwango vya kufungua baada ya kutuma.",
        "See who received and read each message.": "Ona ni nani aliyepokea na kusoma kila ujumbe.",
        "The admissions pipeline from enquiry to enrolled.": "Mfumo wa udahili kutoka ulizo hadi kujiandikisha.",
        "Drag an applicant to advance their stage.": "Vuta mwombaji kusonga hatua yake mbele.",
        "Every applicant in a reviewable list.": "Kila mwombaji katika orodha inayokaguliwa.",
        "Open a record to see documents and decisions.": "Fungua rekodi kuona nyaraka na maamuzi.",
        "Send an offer or decision email in one click.": "Tuma barua pepe ya ofa au uamuzi kwa mbofyo mmoja.",
        "Templated, branded, and logged automatically.": "Yenye kiolezo, chapa, na kuhifadhiwa kiotomatiki.",
        "Conversion across the funnel, stage by stage.": "Ubadilishaji katika mfereji, hatua kwa hatua.",
        "See where applicants drop off.": "Ona pale waombaji wanapojiondoa.",
        "The gradebook for a class and assessment.": "Kitabu cha alama kwa darasa na tathmini.",
        "Enter marks; weighted totals compute live.": "Ingiza alama; jumla zenye uzito huhesabiwa moja kwa moja.",
        "Grades sit against the same enrolled roster.": "Alama zinakaa kwenye orodha ile ile ya waliojiandikisha.",
        "One learner, one continuous academic record.": "Mwanafunzi mmoja, rekodi moja ya kitaaluma inayoendelea.",
        "Grade distribution and cohort averages.": "Mgawanyo wa alama na wastani wa kundi.",
        "Spot the assessment that needs a re-teach.": "Tambua tathmini inayohitaji kufundishwa upya.",
    },
    "ha": {
        "The student information dashboard the moment you sign in.": "Dashboard ɗin bayanan ɗalibi nan take da ka shiga.",
        "Live enrolment, attendance and standing — one glance.": "Shiga, halarta da matsayi kai tsaye — kallo ɗaya.",
        "Every learner in a sortable, filterable roster.": "Kowane ɗalibi a cikin jeri mai tsarawa da tacewa.",
        "Click any row to open the full student record.": "Danna kowane layi don buɗe cikakken rikodin ɗalibi.",
        "Daily attendance captured against the same roster.": "Ana ɗaukar halartar yau da kullum kan jeri ɗaya.",
        "Mark a whole class present in two taps.": "Yi wa aji gabaki ɗaya alamar halarta da danni biyu.",
        "Academic standing rolls up into report cards.": "Matsayin ilimi yana taruwa cikin katunan rahoto.",
        "Grades flow straight to guardians.": "Maki suna kaiwa ga masu kula kai tsaye.",
        "The class attendance grid for today's register.": "Gidan halartar aji don rajistar yau.",
        "Tap a cell to cycle present, absent or late.": "Taɓa tantani don sauya halarta, rashi ko makara.",
        "Attendance is anchored to the live class roster.": "An ɗaure halarta da jerin ajin kai tsaye.",
        "No re-keying — the roster is the source of truth.": "Babu sake bugawa — jerin shi ne tushen gaskiya.",
        "Attendance rates summarise into a daily snapshot.": "Yawan halarta yana taƙaitawa cikin hoton yau da kullum.",
        "Spot at-risk learners before they fall behind.": "Gano ɗaliban da ke cikin haɗari kafin su koma baya.",
        "Collections and outstanding balances at a glance.": "Tarawa da ragowar da ake bin kallo ɗaya.",
        "Know exactly what's billed, paid and overdue.": "San ainihin abin da aka biya, aka biya da kuma jinkiri.",
        "A per-student fee ledger with every line item.": "Littafin kuɗi ga kowane ɗalibi tare da kowane abu.",
        "Decimal-accurate — no rounding surprises.": "Daidaiton goma — babu mamakin zagaye.",
        "Send a payment reminder without leaving the ledger.": "Aika tunatarwar biya ba tare da barin littafin ba.",
        "Reminders go by the family's preferred channel.": "Tunatarwa na bi ta hanyar da iyali suka fi so.",
        "Compose a message to a class, year group or whole school.": "Rubuta saƙo zuwa aji, rukunin shekara ko makaranta gabaki ɗaya.",
        "One composer, every channel — email, SMS, push.": "Mai tsara guda, kowace hanya — imel, SMS, sanarwa.",
        "Pick the audience straight from the live roster.": "Zaɓi masu sauraro kai tsaye daga jerin kai tsaye.",
        "Target by class, role or custom segment.": "Yi niyya ta aji, matsayi ko sashe na musamman.",
        "Track delivery and open rates after you send.": "Bi diddigin isarwa da yawan buɗewa bayan ka aika.",
        "See who received and read each message.": "Duba wanda ya karɓa kuma ya karanta kowane saƙo.",
        "The admissions pipeline from enquiry to enrolled.": "Tafarkin shigarwa daga tambaya zuwa shiga.",
        "Drag an applicant to advance their stage.": "Ja mai nema don ciyar da matakinsa gaba.",
        "Every applicant in a reviewable list.": "Kowane mai nema a cikin jeri mai dubawa.",
        "Open a record to see documents and decisions.": "Buɗe rikodi don ganin takardu da yanke shawara.",
        "Send an offer or decision email in one click.": "Aika imel na tayi ko shawara da danni ɗaya.",
        "Templated, branded, and logged automatically.": "Mai samfuri, mai alama, kuma an rubuta ta atomatik.",
        "Conversion across the funnel, stage by stage.": "Juyawa a cikin kwarya, mataki bayan mataki.",
        "See where applicants drop off.": "Duba inda masu nema ke sauka.",
        "The gradebook for a class and assessment.": "Littafin maki don aji da tantancewa.",
        "Enter marks; weighted totals compute live.": "Shigar da maki; jimillar nauyi tana lissafi kai tsaye.",
        "Grades sit against the same enrolled roster.": "Maki suna zaune kan jerin masu shiga ɗaya.",
        "One learner, one continuous academic record.": "Ɗalibi guda, rikodin ilimi mai ci gaba guda.",
        "Grade distribution and cohort averages.": "Rarraba maki da matsakaitan rukuni.",
        "Spot the assessment that needs a re-teach.": "Gano tantancewar da ke buƙatar sake koyarwa.",
    },
    "yo": {
        "The student information dashboard the moment you sign in.": "Pátákó ìròyìn akẹ́kọ̀ọ́ ní kété tí o bá wọlé.",
        "Live enrolment, attendance and standing — one glance.": "Ìforúkọsílẹ̀, wíwà àti ipò tààrà — ìwò kan.",
        "Every learner in a sortable, filterable roster.": "Akẹ́kọ̀ọ́ kọ̀ọ̀kan nínú àkójọ tí a lè tò tí a sì lè ṣẹ́.",
        "Click any row to open the full student record.": "Tẹ ìlà èyíkéyìí láti ṣí àkọsílẹ̀ akẹ́kọ̀ọ́ ní kíkún.",
        "Daily attendance captured against the same roster.": "A kọ wíwà ojoojúmọ́ sí àkójọ kan náà.",
        "Mark a whole class present in two taps.": "Sàmì sí gbogbo kíláàsì gẹ́gẹ́ bí ó ti wà ní ìtẹ̀ méjì.",
        "Academic standing rolls up into report cards.": "Ipò ẹ̀kọ́ ń kó jọ sínú àwọn káàdì ìròyìn.",
        "Grades flow straight to guardians.": "Àwọn àmì ń ṣàn tààrà sí àwọn olùtọ́jú.",
        "The class attendance grid for today's register.": "Àkójọ wíwà kíláàsì fún ìforúkọ òní.",
        "Tap a cell to cycle present, absent or late.": "Tẹ àpótí láti yí wà, àìsí tàbí pẹ́.",
        "Attendance is anchored to the live class roster.": "Wíwà ní ìdúró sí àkójọ kíláàsì tààrà.",
        "No re-keying — the roster is the source of truth.": "Kò sí àtúntẹ̀ — àkójọ ni orísun òtítọ́.",
        "Attendance rates summarise into a daily snapshot.": "Iye wíwà ń ṣàkójọ sí àkópọ̀ ojoojúmọ́.",
        "Spot at-risk learners before they fall behind.": "Ṣàwárí àwọn akẹ́kọ̀ọ́ tí ó wà nínú ewu kí wọ́n tó dúró lẹ́yìn.",
        "Collections and outstanding balances at a glance.": "Àkójọpọ̀ àti ìyókù tí a ń dúró dè ní ìwò kan.",
        "Know exactly what's billed, paid and overdue.": "Mọ̀ ohun tí a gbé sí owó, tí a san, àti tí ó ti pẹ́.",
        "A per-student fee ledger with every line item.": "Ìwé owó fún akẹ́kọ̀ọ́ kọ̀ọ̀kan pẹ̀lú gbogbo ohun kọ̀ọ̀kan.",
        "Decimal-accurate — no rounding surprises.": "Pípé déédéé — kò sí ìyàlẹ́nu yíká.",
        "Send a payment reminder without leaving the ledger.": "Fi ìránnilétí ìsanwó ránṣẹ́ láìjáde kúrò nínú ìwé.",
        "Reminders go by the family's preferred channel.": "Àwọn ìránnilétí ń gba ọ̀nà tí ẹbí fẹ́ràn.",
        "Compose a message to a class, year group or whole school.": "Kọ ìránṣẹ́ sí kíláàsì, ẹgbẹ́ ọdún tàbí gbogbo ilé-ìwé.",
        "One composer, every channel — email, SMS, push.": "Akọ̀wé kan, gbogbo ọ̀nà — ímeèlì, SMS, ìfìtónilétí.",
        "Pick the audience straight from the live roster.": "Yan àwùjọ tààrà láti inú àkójọ tààrà.",
        "Target by class, role or custom segment.": "Fojúsùn nípa kíláàsì, ipa tàbí apá àkànṣe.",
        "Track delivery and open rates after you send.": "Tọ́jú ìfijíṣẹ́ àti iye ṣíṣí lẹ́yìn tí o bá fi ránṣẹ́.",
        "See who received and read each message.": "Wo ẹni tí ó gbà tí ó sì ka ìránṣẹ́ kọ̀ọ̀kan.",
        "The admissions pipeline from enquiry to enrolled.": "Ọ̀nà ìgbàwọlé láti ìbéèrè dé ìforúkọsílẹ̀.",
        "Drag an applicant to advance their stage.": "Fa olùbéèrè láti tẹ ìpele wọn síwájú.",
        "Every applicant in a reviewable list.": "Olùbéèrè kọ̀ọ̀kan nínú àkójọ tí a lè ṣàyẹ̀wò.",
        "Open a record to see documents and decisions.": "Ṣí àkọsílẹ̀ láti rí àwọn ìwé àti àwọn ìpinnu.",
        "Send an offer or decision email in one click.": "Fi ímeèlì ìpèsè tàbí ìpinnu ránṣẹ́ ní ìtẹ̀ kan.",
        "Templated, branded, and logged automatically.": "Pẹ̀lú àwòṣe, àmì, àti àkọsílẹ̀ lọ́nà aládàáṣe.",
        "Conversion across the funnel, stage by stage.": "Ìyípadà káàkiri ọ̀nà, ìpele kọ̀ọ̀kan.",
        "See where applicants drop off.": "Wo ibi tí àwọn olùbéèrè ti ń jáde.",
        "The gradebook for a class and assessment.": "Ìwé àmì fún kíláàsì àti àyẹ̀wò.",
        "Enter marks; weighted totals compute live.": "Tẹ àwọn àmì; àpapọ̀ onírẹ̀wọ̀n ń ṣírò tààrà.",
        "Grades sit against the same enrolled roster.": "Àwọn àmì jókòó sí àkójọ tí a forúkọsílẹ̀ kan náà.",
        "One learner, one continuous academic record.": "Akẹ́kọ̀ọ́ kan, àkọsílẹ̀ ẹ̀kọ́ tí ń bá a lọ kan.",
        "Grade distribution and cohort averages.": "Pípín àmì àti àpapọ̀ ìpíndọ́gba ẹgbẹ́.",
        "Spot the assessment that needs a re-teach.": "Ṣàwárí àyẹ̀wò tí ó nílò àtúnkọ́.",
    },
}


def _normalize_lang(lang: Optional[str]) -> str:
    """Normalize a language code to a supported base code, default ``en``."""
    base = (lang or "en").strip().lower().replace("_", "-").split("-")[0]
    return base if base in SUPPORTED_LANGS else "en"


def _t_tour_text(text: str, lang: str) -> str:
    """Translate a caption/tooltip for ``lang``, English-fallback on miss."""
    if lang == "en":
        return text
    return _TOUR_TEXT_TRANSLATIONS.get(lang, {}).get(text, text)


def product_tour_for_slug(slug: str, lang: str = "en") -> Optional[ProductTour]:
    """Return the tour for ``slug`` (case-insensitive) or ``None``.

    The result is a fresh dict shaped ``{"slug": <canonical-slug>, "frames":
    [...]}`` suitable for handing straight to the ``_product_tour.html``
    component as the ``product_tour`` context variable.

    ``lang`` is an optional language code (``en``/``fr``/``es``/``pt``/``ar``
    plus best-effort ``sw``/``ha``/``yo``). Only the human-readable ``caption``
    and ``tooltip`` are localized; the stable ``key`` and ``ui_kind`` enums are
    never translated. English is the fallback for any missing translation or
    unknown language.
    """

    if not slug:
        return None
    key = slug.strip().lower()
    frames = _PRODUCT_TOURS.get(key)
    if not frames:
        return None
    norm_lang = _normalize_lang(lang)
    if norm_lang == "en":
        return {"slug": key, "frames": [dict(frame) for frame in frames]}
    localized: list[TourFrame] = [
        {
            "key": frame["key"],
            "caption": _t_tour_text(frame["caption"], norm_lang),
            "tooltip": _t_tour_text(frame["tooltip"], norm_lang),
            "ui_kind": frame["ui_kind"],
        }
        for frame in frames
    ]
    return {"slug": key, "frames": localized}


def flagship_tour_slugs() -> list[str]:
    """Return the list of slugs that have a defined product tour."""

    return list(_PRODUCT_TOURS.keys())
