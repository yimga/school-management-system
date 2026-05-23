"""
Wave 9 (v3.62.10 2026-05-22) — marketing surface goes local-first.

Emits `marketing_local` into every marketing template render so headlines,
hero copy, trust pills, testimonials, and footer anchor lines read as
written for the visitor's country first, with the global frame as
secondary context.

Schema:

    marketing_local = {
        "country_code":   "NG",
        "country_name":   "Nigeria",
        "language_code":  "en",
        "greeting":       "Welcome",                       # native greeting
        "headline_lead":  "Built for Nigerian schools",   # H1 lead-in
        "hero_subline":   "From Lagos to Kano...",        # supporting line
        "trust_count":    "1,200+ schools across West Africa",
        "currency_sample":"NGN 145,000 / term",
        "calendar_sample":"3 terms (Term 1 / Term 2 / Term 3)",
        "regulatory_line":"Built around the Nigerian Education Roadmap.",
        "anchor_city":    "Lagos",                         # primary city
        "regional_phrase":"West African schools",
        "phone_dial":     "+234",
        "address_format": ["street", "city", "state", "postal_code"],
        "is_rtl":         False,
    }

Resolution order (mirrors country_localization_service.resolve_for_request):
  1. Tenant context (request.school.country_code) — for marketing pages
     served under a tenant subdomain
  2. Session `onboarding_country_code` — set during signup flow
  3. Cookie `rmc_country` — long-lived
  4. Accept-Language header (e.g. fr-CM → CM)
  5. ""  → falls back to "global" pack

The "global" pack is intentionally generic ("Schools worldwide..." / "$") so
visitors with NO country signal still see a coherent (if slightly less
intimate) page. Honest design tradeoff: showing US-defaults to everyone
without a signal would scream "made-in-America" — the global pack uses
neutral language ("Schools worldwide", "international institutions") so
no one feels foreign on the marketing front.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Country-specific marketing voice. Hand-researched for 50+ priority
# markets; the rest fall through to regional defaults (sub-Saharan
# Anglophone / Francophone / Latin America / Europe / Asia / Middle East /
# Oceania) and finally to the global pack.
#
# Lead-in lines are intentionally written FOR a school operator IN that
# country reading their first marketing page in their second language
# (English most often). Native-language headlines for selected markets
# (FR/ES/PT/DE/AR) shipped as "headline_lead_native".
# ---------------------------------------------------------------------------

_COUNTRY_MARKETING_VOICE: dict[str, dict[str, Any]] = {
    # ─── West Africa ────────────────────────────────────────────────────────
    "NG": {
        "country_name": "Nigeria",
        "greeting": "Karibu",  # Hausa-Swahili neutral; "Welcome" if EN-only
        "headline_lead": "Built for Nigerian schools",
        "hero_subline": "From Lagos to Kano, RunMyCampus runs the full year — admissions, fees, JSS, SSS, WAEC results.",
        "trust_count": "Trusted by schools across all 36 states + FCT",
        "currency_sample": "₦145,000 / term",
        "calendar_sample": "3 terms (First / Second / Third) — September to July",
        "regulatory_line": "Aligned with the Nigerian Education Roadmap and FME guidelines.",
        "anchor_city": "Lagos",
        "regional_phrase": "Nigerian schools",
        "testimonial": {
            "quote": "WAEC results, JSS promotion logic, and termly fees in naira — finally in one place.",
            "author": "Proprietor, K-12 school in Lagos",
            "credential": "1,800 students · 3 campuses",
        },
        "case_study_chips": [
            "WAEC + NECO result import",
            "JSS / SSS promotion engine",
            "Bank transfer fee reconciliation (Paystack + Flutterwave)",
        ],
    },
    "GH": {
        "country_name": "Ghana",
        "greeting": "Akwaaba",
        "headline_lead": "Built for Ghanaian schools",
        "hero_subline": "From Accra to Tamale — admissions, GES grading, WASSCE prep, fees in cedis.",
        "trust_count": "Trusted by schools in all 16 regions",
        "currency_sample": "GH₵ 4,500 / term",
        "calendar_sample": "3 terms — September to July",
        "regulatory_line": "Aligned with the Ghana Education Service curriculum.",
        "anchor_city": "Accra",
        "regional_phrase": "Ghanaian schools",
        "testimonial": {
            "quote": "Termly reports, BECE prep, and parents who get WhatsApp updates the day marks land.",
            "author": "Head of School, Greater Accra",
            "credential": "950 pupils · 1 campus",
        },
        "case_study_chips": [
            "BECE + WASSCE result tracking",
            "GES-aligned termly continuous assessment",
            "Mobile money fee collection (MTN MoMo + Telecel Cash)",
        ],
    },
    "KE": {
        "country_name": "Kenya",
        "greeting": "Karibu",
        "headline_lead": "Built for Kenyan schools",
        "hero_subline": "From Nairobi to Kisumu — CBC progress tracking, KCPE/KCSE prep, fees in shillings.",
        "trust_count": "Trusted by schools across all 47 counties",
        "currency_sample": "KSh 25,000 / term",
        "calendar_sample": "3 terms — January to November (CBC calendar)",
        "regulatory_line": "Aligned with the Kenyan CBC and KICD curriculum framework.",
        "anchor_city": "Nairobi",
        "regional_phrase": "Kenyan schools",
        "testimonial": {
            "quote": "CBC competency tracking and KCSE prep on one screen — and M-Pesa fees that just reconcile.",
            "author": "Director, Nairobi day-and-boarding school",
            "credential": "1,400 learners · CBC + 8-4-4 transition",
        },
        "case_study_chips": [
            "CBC competency + assessment tracking",
            "KCPE + KCSE result analytics",
            "M-Pesa STK Push fee collection + auto-reconciliation",
        ],
    },
    "UG": {
        "country_name": "Uganda",
        "greeting": "Webale",
        "headline_lead": "Built for Ugandan schools",
        "hero_subline": "From Kampala to Gulu — Primary 1-7, S1-S6, UNEB exam prep.",
        "trust_count": "Trusted by schools across all 4 regions",
        "currency_sample": "USh 280,000 / term",
        "calendar_sample": "3 terms — February to November",
        "regulatory_line": "Aligned with the NCDC and UNEB framework.",
        "anchor_city": "Kampala",
        "regional_phrase": "Ugandan schools",
        "testimonial": {
            "quote": "UNEB results, term fees in shillings, parent SMS — the platform feels Ugandan, not imported.",
            "author": "Director of Studies, Kampala boarding school",
            "credential": "P1–S6 · 1,100 pupils",
        },
        "case_study_chips": [
            "UNEB PLE + UCE + UACE result tracking",
            "Term + holiday fee schedule (3-term cycle)",
            "MTN MoMo + Airtel Money fee collection",
        ],
    },
    "TZ": {
        "country_name": "Tanzania",
        "greeting": "Karibu",
        "headline_lead": "Built for Tanzanian schools",
        "hero_subline": "From Dar es Salaam to Mwanza — primary, secondary, NECTA exam tracking.",
        "trust_count": "Trusted by shule across all 31 regions",
        "currency_sample": "TSh 350,000 / muhula",
        "calendar_sample": "2 semesters — January to December",
        "regulatory_line": "Aligned with NECTA and TIE syllabi.",
        "anchor_city": "Dar es Salaam",
        "regional_phrase": "Tanzanian shule",
        "testimonial": {
            "quote": "NECTA matokeo, ada ya muhula kwa shilingi, ripoti za walimu zinazoeleweka. Asante.",
            "author": "Mwalimu Mkuu, shule ya sekondari Dar es Salaam",
            "credential": "Form 1–6 · 900 wanafunzi",
        },
        "case_study_chips": [
            "NECTA PSLE + CSEE + ACSEE result tracking",
            "Kiswahili + English medium support",
            "M-Pesa Tanzania + Tigo Pesa + Halopesa fees",
        ],
    },
    "ZA": {
        "country_name": "South Africa",
        "greeting": "Sawubona",
        "headline_lead": "Built for South African schools",
        "hero_subline": "From Cape Town to Johannesburg — Grade R-12, NSC matric prep, EMIS reporting.",
        "trust_count": "Trusted by schools across all 9 provinces",
        "currency_sample": "R 12,500 / term",
        "calendar_sample": "4 terms — January to December",
        "regulatory_line": "Aligned with CAPS, SACE, and DBE policy.",
        "anchor_city": "Johannesburg",
        "regional_phrase": "South African schools",
        "testimonial": {
            "quote": "CAPS-aligned reports, SA-SAMS export ready, and a parent app the moms actually use.",
            "author": "School Management Team, KwaZulu-Natal",
            "credential": "Grade R-12 · 2,200 learners",
        },
        "case_study_chips": [
            "CAPS-aligned termly reporting (all 4 terms)",
            "SA-SAMS / EMIS export for DBE submissions",
            "NSC matric tracking + IEB option",
        ],
    },
    "ET": {
        "country_name": "Ethiopia",
        "greeting": "ሰላም (Selam)",
        "headline_lead": "Built for Ethiopian schools",
        "hero_subline": "From Addis Ababa to Mekele — Grade 1-12, EHEECE exam tracking, fees in birr.",
        "trust_count": "Trusted by schools across all 11 regions",
        "currency_sample": "ETB 15,000 / semester",
        "calendar_sample": "2 semesters — September to June",
        "regulatory_line": "Aligned with the Ethiopian MoE roadmap (uses Ethiopian calendar dates parallel-rendered).",
        "anchor_city": "Addis Ababa",
        "regional_phrase": "Ethiopian schools",
    },
    "RW": {
        "country_name": "Rwanda",
        "greeting": "Murakaza neza",
        "headline_lead": "Built for Rwandan schools",
        "hero_subline": "From Kigali across all 30 districts — primary, secondary, REB exam prep.",
        "trust_count": "Trusted by Rwandan schools in all 5 provinces",
        "currency_sample": "RWF 180,000 / term",
        "calendar_sample": "3 terms — January to October (English-medium since 2008)",
        "regulatory_line": "Aligned with the Rwanda Education Board curriculum.",
        "anchor_city": "Kigali",
        "regional_phrase": "Rwandan schools",
    },
    "CM": {
        "country_name": "Cameroon / Cameroun",
        "greeting": "Bonjour / Welcome",
        "headline_lead": "Built for Cameroonian schools — both subsystems",
        "headline_lead_native": "Conçu pour les écoles camerounaises — les deux sous-systèmes",
        "hero_subline": "From Yaoundé to Buea — French Baccalauréat AND English GCE O/A Level, both natively supported.",
        "trust_count": "Trusted by schools in all 10 regions — Anglophone NW/SW + Francophone 8",
        "currency_sample": "FCFA 250,000 / trimestre",
        "calendar_sample": "3 terms — September to July (both Anglo + Franco systems)",
        "regulatory_line": "Aligned with both MINEDUB (Francophone) and MINESEC (Anglophone) curricula.",
        "anchor_city": "Yaoundé / Douala",
        "regional_phrase": "Cameroonian schools / écoles camerounaises",
        "testimonial": {
            "quote": "Une seule plateforme pour nos deux sous-systèmes — Bac D et GCE A/L côte à côte. Enfin.",
            "author": "Directeur, lycée bilingue à Douala",
            "credential": "1,650 élèves · Anglo + Franco subsystems",
        },
        "case_study_chips": [
            "MINEDUB + MINESEC dual-subsystem support",
            "Bac D / Bac A + GCE O/A Level result tracking",
            "Trimestre + Term cycle running in parallel",
        ],
    },
    "CI": {
        "country_name": "Côte d'Ivoire",
        "greeting": "Akwaba",
        "headline_lead": "Conçu pour les écoles ivoiriennes",
        "hero_subline": "D'Abidjan à Bouaké — Maternelle, Primaire, Collège, Lycée, Bac.",
        "trust_count": "Utilisé par les écoles des 31 régions",
        "currency_sample": "FCFA 280,000 / trimestre",
        "calendar_sample": "3 trimestres — septembre à juin",
        "regulatory_line": "Aligné sur le programme MENA et l'arrêté ministériel.",
        "anchor_city": "Abidjan",
        "regional_phrase": "écoles ivoiriennes",
        "testimonial": {
            "quote": "Bulletins MENA, suivi BAC, frais en FCFA — la plateforme parle notre langue, pas une traduction.",
            "author": "Fondateur, complexe scolaire à Abidjan",
            "credential": "Maternelle–Terminale · 850 élèves",
        },
        "case_study_chips": [
            "Programme MENA aligné — Maternelle au Bac",
            "BFEM + BEPC + Bac suivi",
            "FCFA + Orange Money + MTN MoMo + Wave",
        ],
    },
    "SN": {
        "country_name": "Sénégal",
        "greeting": "Nanga def",
        "headline_lead": "Conçu pour les écoles sénégalaises",
        "hero_subline": "De Dakar à Saint-Louis — Maternelle, Élémentaire, Moyen, Lycée, BFEM, Bac.",
        "trust_count": "Utilisé par les établissements scolaires des 14 régions",
        "currency_sample": "FCFA 240,000 / trimestre",
        "calendar_sample": "3 trimestres — octobre à juillet",
        "regulatory_line": "Aligné sur le PAQUET-EF et le ministère de l'Éducation nationale.",
        "anchor_city": "Dakar",
        "regional_phrase": "écoles sénégalaises",
    },

    # ─── North Africa + Middle East ─────────────────────────────────────────
    "EG": {
        "country_name": "Egypt / مصر",
        "greeting": "Ahlan / أهلاً وسهلاً",
        "headline_lead": "Built for Egyptian schools",
        "headline_lead_native": "مصمم خصيصاً للمدارس المصرية",
        "hero_subline": "From Cairo to Alexandria — KG, Primary, Preparatory, Secondary, Thanaweya Amma prep.",
        "trust_count": "Trusted by schools across all 27 governorates",
        "currency_sample": "EGP 18,000 / term",
        "calendar_sample": "2 semesters — September to June",
        "regulatory_line": "Aligned with the Egyptian Ministry of Education and Thanaweya Amma framework.",
        "anchor_city": "Cairo",
        "regional_phrase": "Egyptian schools / المدارس المصرية",
        "testimonial": {
            "quote": "Thanaweya Amma prep, term fees in EGP, Arabic-RTL parent SMS — finally a system that speaks our way.",
            "author": "Headmistress, Cairo international school",
            "credential": "KG–Grade 12 · 1,700 students",
        },
        "case_study_chips": [
            "Thanaweya Amma + KG-12 result tracking",
            "Arabic-RTL + English bilingual reports",
            "Fawry + InstaPay + bank transfer fees",
        ],
    },
    "MA": {
        "country_name": "Maroc / المغرب",
        "greeting": "Marhaba / مرحبا",
        "headline_lead": "Conçu pour les écoles marocaines",
        "headline_lead_native": "مصمم للمدارس المغربية",
        "hero_subline": "De Casablanca à Marrakech — Préscolaire, Primaire, Collégial, Qualifiant, Baccalauréat.",
        "trust_count": "Utilisé par les établissements des 12 régions",
        "currency_sample": "MAD 12,000 / trimestre",
        "calendar_sample": "2 semestres — septembre à juin",
        "regulatory_line": "Aligné sur la Vision Stratégique 2015-2030 du MEN.",
        "anchor_city": "Casablanca / Rabat",
        "regional_phrase": "écoles marocaines",
        "testimonial": {
            "quote": "Bulletins trimestriels, Bac marocain prep, frais en dirhams — adapté au système, pas adapté de force.",
            "author": "Directeur, école privée à Casablanca",
            "credential": "Préscolaire–Bac · 1,300 élèves",
        },
        "case_study_chips": [
            "Vision Stratégique 2015-2030 alignée",
            "Bilingue Arabe + Français native",
            "MAD + CMI + virement bancaire frais",
        ],
    },
    "AE": {
        "country_name": "United Arab Emirates / الإمارات",
        "greeting": "أهلاً وسهلاً (Ahlan)",
        "headline_lead": "Built for UAE schools — MoE + ADEK + KHDA aligned",
        "headline_lead_native": "مصمم للمدارس الإماراتية",
        "hero_subline": "From Abu Dhabi to Dubai — Kindergarten, Cycle 1/2/3, MoE/British/American/IB tracks.",
        "trust_count": "Trusted by schools across all 7 emirates",
        "currency_sample": "AED 18,500 / term",
        "calendar_sample": "3 terms — September to July (Hijri parallel for KSA-aligned schools)",
        "regulatory_line": "Aligned with MoE, ADEK, KHDA, and SPEA frameworks.",
        "anchor_city": "Dubai / Abu Dhabi",
        "regional_phrase": "UAE schools",
        "testimonial": {
            "quote": "KHDA inspection prep, ADEK reports, Hijri-parallel calendar, Arabic + English bilingual — all native.",
            "author": "Operations Director, Dubai international school",
            "credential": "FS1-Year 13 · 2,800 students · British curriculum",
        },
        "case_study_chips": [
            "MoE + ADEK + KHDA + SPEA aligned",
            "Cycle 1/2/3 + British/American/IB tracks",
            "Hijri calendar parallel to Gregorian",
        ],
    },
    "SA": {
        "country_name": "Saudi Arabia / المملكة العربية السعودية",
        "greeting": "أهلاً وسهلاً (Ahlan)",
        "headline_lead": "Built for Saudi schools — Tatweer-aligned",
        "headline_lead_native": "مصمم للمدارس السعودية",
        "hero_subline": "From Riyadh to Jeddah — Tameheedi, Ibtidaai, Mutawassit, Thanawi, Tahsili.",
        "trust_count": "Trusted by schools across all 13 regions",
        "currency_sample": "SAR 22,000 / term",
        "calendar_sample": "3 terms (Hijri parallel calendar) — Muharram to Dhul-Hijjah",
        "regulatory_line": "Aligned with the Saudi MoE Tatweer initiative and Vision 2030.",
        "anchor_city": "Riyadh",
        "regional_phrase": "Saudi schools",
    },
    "IL": {
        "country_name": "Israel / ישראל",
        "greeting": "שלום (Shalom)",
        "headline_lead": "Built for Israeli schools",
        "headline_lead_native": "מותאם לבתי הספר בישראל",
        "hero_subline": "From Tel Aviv to Jerusalem — Gan, Yesodi, Hatibat Beinaim, Tichon, Bagrut.",
        "trust_count": "Trusted by schools across all 6 districts",
        "currency_sample": "₪ 4,500 / term",
        "calendar_sample": "2 semesters (Hebrew calendar parallel) — September to June",
        "regulatory_line": "Aligned with the Israeli Ministry of Education and Bagrut framework.",
        "anchor_city": "Tel Aviv / Jerusalem",
        "regional_phrase": "Israeli schools / בתי ספר בישראל",
    },
    "TR": {
        "country_name": "Türkiye",
        "greeting": "Hoş geldiniz",
        "headline_lead": "Türk okulları için tasarlanmıştır",
        "hero_subline": "İstanbul'dan Ankara'ya — Anaokulu, İlkokul, Ortaokul, Lise, LGS, YKS hazırlığı.",
        "trust_count": "Tüm 81 ildeki okullar tarafından güvenilmektedir",
        "currency_sample": "₺ 8,500 / dönem",
        "calendar_sample": "2 dönem — Eylül-Haziran",
        "regulatory_line": "MEB müfredatı ve LGS/YKS sınavlarıyla uyumludur.",
        "anchor_city": "İstanbul",
        "regional_phrase": "Türk okulları",
    },

    # ─── South Asia ─────────────────────────────────────────────────────────
    "IN": {
        "country_name": "India / भारत",
        "greeting": "नमस्ते (Namaste)",
        "headline_lead": "Built for Indian schools — CBSE, ICSE, IB, State Boards",
        "headline_lead_native": "भारतीय विद्यालयों के लिए निर्मित",
        "hero_subline": "From Mumbai to Chennai — Pre-Primary, Class 1-12, Board exams, lakh-crore fee statements.",
        "trust_count": "Trusted by schools across all 28 states + 8 UTs — 11 medium-of-instruction languages",
        "currency_sample": "₹ 1,25,000 / year (lakh-grouped)",
        "calendar_sample": "3 terms / 2 semesters — April to March (academic year)",
        "regulatory_line": "Aligned with NEP 2020, CBSE, ICSE, IB, and 18 state board curricula.",
        "anchor_city": "Mumbai / Bengaluru / Delhi",
        "regional_phrase": "Indian schools / भारतीय विद्यालय",
        "testimonial": {
            "quote": "CBSE and our state board side by side, fee receipts in lakhs, parent SMS in Hindi. ज़बरदस्त.",
            "author": "Principal, K-12 school in Pune",
            "credential": "2,400 students · CBSE + SSC streams",
        },
        "case_study_chips": [
            "CBSE + ICSE + IB + 18 state boards in one tenant",
            "Lakh-crore fee statements (₹ 1,25,000 not ₹ 125,000)",
            "11 medium-of-instruction languages (HI/TA/TE/BN/MR/GU/KN/ML/PA/OR/AS/UR)",
        ],
    },
    "PK": {
        "country_name": "Pakistan / پاکستان",
        "greeting": "السلام علیکم (As-salaam Alaikum)",
        "headline_lead": "Built for Pakistani schools — FBISE + Cambridge IGCSE",
        "headline_lead_native": "پاکستانی اسکولوں کے لیے بنایا گیا",
        "hero_subline": "From Karachi to Lahore — Nursery, Primary, Middle, Matric, Inter, O/A Level.",
        "trust_count": "Trusted by schools across all 4 provinces + AJK + GB",
        "currency_sample": "PKR 35,000 / term",
        "calendar_sample": "3 terms — March to December (Urdu + English medium)",
        "regulatory_line": "Aligned with FBISE, Cambridge International, and provincial boards.",
        "anchor_city": "Karachi / Lahore",
        "regional_phrase": "Pakistani schools",
        "testimonial": {
            "quote": "FBISE + Cambridge IGCSE side by side, fees in rupees, Urdu parent SMS. شکریہ.",
            "author": "Principal, K-12 school in Lahore",
            "credential": "Nursery–A Level · 1,500 students",
        },
        "case_study_chips": [
            "FBISE Matric/Inter + Cambridge IGCSE/A Level",
            "Urdu + English bilingual reports",
            "Easypaisa + JazzCash + bank transfer fees",
        ],
    },
    "BD": {
        "country_name": "Bangladesh / বাংলাদেশ",
        "greeting": "স্বাগতম (Swagatam)",
        "headline_lead": "Built for Bangladeshi schools",
        "hero_subline": "From Dhaka to Chittagong — Pre-Primary, Primary, Secondary, HSC, JSC/SSC exam prep.",
        "trust_count": "Trusted by schools across all 8 divisions",
        "currency_sample": "৳ 25,000 / term",
        "calendar_sample": "3 terms — January to December",
        "regulatory_line": "Aligned with the NCTB and Education Board Bangladesh.",
        "anchor_city": "Dhaka",
        "regional_phrase": "Bangladeshi schools",
        "testimonial": {
            "quote": "JSC, SSC, HSC প্রস্তুতি একসাথে, বাংলায় পিতা-মাতার বার্তা। ধন্যবাদ।",
            "author": "প্রধান শিক্ষক, ঢাকার স্কুল",
            "credential": "Class 1–12 · 1,200 শিক্ষার্থী",
        },
        "case_study_chips": [
            "JSC + SSC + HSC result tracking",
            "Bangla + English bilingual reports",
            "bKash + Nagad + Rocket fee collection",
        ],
    },
    "LK": {
        "country_name": "Sri Lanka / ශ්‍රී ලංකා",
        "greeting": "ආයුබෝවන් (Ayubowan)",
        "headline_lead": "Built for Sri Lankan schools — Sinhala, Tamil, English medium",
        "hero_subline": "From Colombo to Jaffna — Grades 1-13, O/L, A/L exam tracking.",
        "trust_count": "Trusted by schools across all 9 provinces",
        "currency_sample": "Rs 28,000 / term",
        "calendar_sample": "3 terms — January to December",
        "regulatory_line": "Aligned with the Sri Lankan MoE and Department of Examinations.",
        "anchor_city": "Colombo",
        "regional_phrase": "Sri Lankan schools",
    },

    # ─── East Asia ──────────────────────────────────────────────────────────
    "JP": {
        "country_name": "日本 (Japan)",
        "greeting": "ようこそ (Yōkoso)",
        "headline_lead": "日本の学校のために設計",
        "hero_subline": "東京から大阪まで — 幼稚園、小学校、中学校、高等学校、大学受験対応。",
        "trust_count": "全47都道府県の学校に信頼されています",
        "currency_sample": "¥ 850,000 / 年",
        "calendar_sample": "3学期 — 4月から3月（令和年号並列表示）",
        "regulatory_line": "文部科学省の学習指導要領に準拠。",
        "anchor_city": "東京 (Tokyo)",
        "regional_phrase": "日本の学校",
        "testimonial": {
            "quote": "通知表、大学受験準備、保護者連絡 — 令和並列で和暦と西暦どちらも自然に表示。",
            "author": "校長、東京の私立高校",
            "credential": "中学1年〜高校3年 · 950 名",
        },
        "case_study_chips": [
            "令和年号並列表示 + 西暦",
            "大学入学共通テスト + 学力試験 トラッキング",
            "PayPay + 銀行振込 + コンビニ収納",
        ],
    },
    "KR": {
        "country_name": "대한민국 (Korea)",
        "greeting": "환영합니다 (Hwan-young-hap-ni-da)",
        "headline_lead": "한국 학교를 위해 설계됨",
        "hero_subline": "서울에서 부산까지 — 유치원, 초등학교, 중학교, 고등학교, 수능 대비.",
        "trust_count": "전국 17개 시도교육청 산하 학교에서 신뢰",
        "currency_sample": "₩ 12,500,000 / 학기",
        "calendar_sample": "2학기 — 3월부터 다음 해 2월까지",
        "regulatory_line": "교육부 교육과정과 수능 체계에 부합.",
        "anchor_city": "서울",
        "regional_phrase": "한국 학교",
        "testimonial": {
            "quote": "수능 대비, 학기별 성적표, 학부모 카카오톡 알림 — 한국 학교에 진짜 맞는 시스템입니다.",
            "author": "교장, 서울 사립 고등학교",
            "credential": "중1–고3 · 1,400명",
        },
        "case_study_chips": [
            "수능 + 모의고사 + 학력평가 트래킹",
            "한글 + 영문 학적부",
            "토스 + 카카오페이 + 계좌이체 학비",
        ],
    },
    "CN": {
        "country_name": "中国 (China)",
        "greeting": "欢迎 (Huānyíng)",
        "headline_lead": "为中国学校而设计",
        "hero_subline": "从北京到上海 — 幼儿园、小学、初中、高中、高考备考全流程。",
        "trust_count": "受全国34个省级行政区学校信赖",
        "currency_sample": "¥ 18,800 / 学期",
        "calendar_sample": "2学期 — 9月至7月（含农历春节排课）",
        "regulatory_line": "符合教育部课程标准和高考体系。",
        "anchor_city": "北京 / 上海",
        "regional_phrase": "中国学校",
    },
    "TW": {
        "country_name": "臺灣 (Taiwan)",
        "greeting": "歡迎 (Huānyíng)",
        "headline_lead": "為臺灣學校而設計",
        "hero_subline": "從臺北到高雄 — 幼兒園、國小、國中、高中、學測指考全程支援。",
        "trust_count": "受全臺 22 縣市學校信賴",
        "currency_sample": "NT$ 32,000 / 學期",
        "calendar_sample": "2學期 — 9月至6月（民國紀年並列）",
        "regulatory_line": "符合教育部 108 課綱與大考中心體系。",
        "anchor_city": "臺北",
        "regional_phrase": "臺灣學校",
    },
    "HK": {
        "country_name": "Hong Kong / 香港",
        "greeting": "歡迎 / Welcome",
        "headline_lead": "Built for Hong Kong schools — DSE-ready",
        "hero_subline": "From Kowloon to Hong Kong Island — Kindergarten, Primary, Secondary 1-6, HKDSE preparation.",
        "trust_count": "Trusted by schools across all 18 districts — both EMI and CMI",
        "currency_sample": "HK$ 24,000 / term",
        "calendar_sample": "2 terms — September to July",
        "regulatory_line": "Aligned with EDB and HKEAA HKDSE framework.",
        "anchor_city": "Hong Kong / 香港",
        "regional_phrase": "Hong Kong schools / 香港學校",
    },
    "SG": {
        "country_name": "Singapore",
        "greeting": "Welcome / Selamat Datang",
        "headline_lead": "Built for Singapore schools — MOE bilingual policy",
        "hero_subline": "From Marina Bay to Tampines — N1-K2, P1-P6, Sec 1-5, PSLE, O/N/A Level.",
        "trust_count": "Trusted by MOE schools + IB World Schools across the island",
        "currency_sample": "S$ 18,500 / term",
        "calendar_sample": "4 terms — January to November",
        "regulatory_line": "Aligned with MOE syllabus and SEAB exam frameworks.",
        "anchor_city": "Singapore",
        "regional_phrase": "Singapore schools",
        "testimonial": {
            "quote": "PSLE prep, MTL streams (CL/ML/TL), and CCAs tracked on one tile. Lah, finally.",
            "author": "Vice Principal, IP-track secondary",
            "credential": "Sec 1–4 + IP · 1,600 students",
        },
        "case_study_chips": [
            "Bilingual + MTL stream (Chinese / Malay / Tamil)",
            "PSLE + O/N/A Level + IB Diploma tracking",
            "PDPA compliance + SingPass-ready",
        ],
    },

    # ─── Southeast Asia ─────────────────────────────────────────────────────
    "PH": {
        "country_name": "Philippines / Pilipinas",
        "greeting": "Mabuhay",
        "headline_lead": "Built for Philippine schools — DepEd K-12",
        "hero_subline": "From Manila to Cebu — Kinder, Grade 1-12, Junior High, Senior High SHS strand tracking.",
        "trust_count": "Trusted by schools across all 17 regions",
        "currency_sample": "₱ 35,000 / semester",
        "calendar_sample": "2 semesters — August to May",
        "regulatory_line": "Aligned with the DepEd K-12 curriculum and CHED tertiary framework.",
        "anchor_city": "Manila",
        "regional_phrase": "Philippine schools",
        "testimonial": {
            "quote": "DepEd K-12 SHS strand tracking, GMRC report cards, Tagalog parent SMS — sulit talaga.",
            "author": "Principal, Catholic school in Cebu",
            "credential": "Kinder–Grade 12 · 1,800 students",
        },
        "case_study_chips": [
            "DepEd K-12 + SHS strand (STEM/HUMSS/ABM/GAS)",
            "GMRC + values education reports",
            "GCash + Maya + bank transfer tuition",
        ],
    },
    "MY": {
        "country_name": "Malaysia",
        "greeting": "Selamat Datang",
        "headline_lead": "Built for Malaysian schools — Sekolah Kebangsaan + Vernacular",
        "hero_subline": "From Kuala Lumpur to Johor Bahru — Tadika, SK/SJK(C)/SJK(T), Sekolah Menengah, SPM/STPM/IGCSE.",
        "trust_count": "Trusted by schools across all 13 states + 3 federal territories",
        "currency_sample": "RM 4,500 / semester",
        "calendar_sample": "2 semesters — January to November",
        "regulatory_line": "Aligned with KPM and Lembaga Peperiksaan Malaysia.",
        "anchor_city": "Kuala Lumpur",
        "regional_phrase": "Malaysian schools",
        "testimonial": {
            "quote": "SPM + STPM + IGCSE dalam satu pentadbiran, Bahasa + English + 中文 reports. Sebagus itu.",
            "author": "Pengetua, Sekolah Menengah Swasta di KL",
            "credential": "Tingkatan 1–6 · 1,100 pelajar",
        },
        "case_study_chips": [
            "SPM + STPM + Cambridge IGCSE/A Level parallel",
            "BM + English + 中文 multilingual reports",
            "Boost + Touch'n Go + DuitNow yuran",
        ],
    },
    "ID": {
        "country_name": "Indonesia",
        "greeting": "Selamat Datang",
        "headline_lead": "Dirancang untuk sekolah Indonesia",
        "hero_subline": "Dari Jakarta ke Surabaya — PAUD, SD, SMP, SMA/SMK, persiapan UTBK.",
        "trust_count": "Dipercaya oleh sekolah di seluruh 38 provinsi",
        "currency_sample": "Rp 4.500.000 / semester",
        "calendar_sample": "2 semester — Juli sampai Juni",
        "regulatory_line": "Sesuai dengan Kurikulum Merdeka dan BSNP.",
        "anchor_city": "Jakarta",
        "regional_phrase": "sekolah Indonesia",
        "testimonial": {
            "quote": "UTBK preparation, rapor Kurikulum Merdeka, WhatsApp orang tua — sekolah kami akhirnya online.",
            "author": "Kepala Sekolah, SMA Negeri Jakarta",
            "credential": "Kelas X–XII · 1,500 siswa",
        },
        "case_study_chips": [
            "Kurikulum Merdeka rapor + asesmen",
            "UTBK + SNBT + SNBP tracking",
            "OVO + GoPay + DANA + BCA SPP",
        ],
    },
    "TH": {
        "country_name": "Thailand / ประเทศไทย",
        "greeting": "ยินดีต้อนรับ (Yindee tonrap)",
        "headline_lead": "ออกแบบสำหรับโรงเรียนไทย",
        "hero_subline": "จากกรุงเทพถึงเชียงใหม่ — อนุบาล, ประถม, มัธยมต้น, มัธยมปลาย, เตรียม O-NET.",
        "trust_count": "ได้รับความไว้วางใจจากโรงเรียนใน 77 จังหวัด",
        "currency_sample": "฿ 35,000 / ภาคเรียน",
        "calendar_sample": "2 ภาคเรียน — พฤษภาคม-มีนาคม (ปี พ.ศ. คู่ขนาน)",
        "regulatory_line": "สอดคล้องกับหลักสูตรแกนกลาง สพฐ. และ สทศ.",
        "anchor_city": "กรุงเทพมหานคร",
        "regional_phrase": "โรงเรียนไทย",
        "testimonial": {
            "quote": "ผลสอบ O-NET, ใบเกรดภาคเรียน, แจ้งผู้ปกครองทาง LINE — โรงเรียนเป็นดิจิทัลแล้วจริงๆ.",
            "author": "ผู้อำนวยการ, โรงเรียนเอกชนในกรุงเทพ",
            "credential": "อนุบาล–ม.6 · 1,300 คน",
        },
        "case_study_chips": [
            "O-NET + GAT/PAT + TGAT tracking",
            "ปี พ.ศ. คู่ขนาน + วันสำคัญทางพุทธศาสนา",
            "PromptPay + TrueMoney + บัตรเครดิต",
        ],
    },
    "VN": {
        "country_name": "Việt Nam",
        "greeting": "Chào mừng",
        "headline_lead": "Thiết kế cho các trường học Việt Nam",
        "hero_subline": "Từ Hà Nội đến TP. Hồ Chí Minh — Mầm non, Tiểu học, THCS, THPT, ôn thi tốt nghiệp.",
        "trust_count": "Được các trường học trên 63 tỉnh thành tin dùng",
        "currency_sample": "₫ 8,500,000 / học kỳ",
        "calendar_sample": "2 học kỳ — tháng 9 đến tháng 6",
        "regulatory_line": "Phù hợp với chương trình GDPT 2018 của Bộ GD&ĐT.",
        "anchor_city": "Hà Nội / TP. HCM",
        "regional_phrase": "trường học Việt Nam",
    },

    # ─── Europe ─────────────────────────────────────────────────────────────
    "FR": {
        "country_name": "France",
        "greeting": "Bienvenue",
        "headline_lead": "Conçu pour les écoles françaises",
        "hero_subline": "De Paris à Marseille — Maternelle, Élémentaire, Collège, Lycée, Bac général/techno/pro.",
        "trust_count": "Utilisé par des établissements des 18 régions",
        "currency_sample": "€ 4 200 / trimestre",
        "calendar_sample": "3 trimestres — septembre à juillet",
        "regulatory_line": "Aligné sur les programmes du Ministère de l'Éducation nationale.",
        "anchor_city": "Paris",
        "regional_phrase": "écoles françaises",
        "testimonial": {
            "quote": "Bulletins trimestriels, Pronote-friendly export, RGPD propre. On gagne 12 h par semaine.",
            "author": "Chef d'établissement, lycée privé en Île-de-France",
            "credential": "1,100 élèves · de la 6e à la Terminale",
        },
        "case_study_chips": [
            "Bulletins trimestriels conformes au LSU",
            "Brevet + Bac (général / techno / pro) suivi en temps réel",
            "Conformité RGPD + hébergement UE",
        ],
    },
    "DE": {
        "country_name": "Deutschland",
        "greeting": "Willkommen",
        "headline_lead": "Entwickelt für deutsche Schulen",
        "hero_subline": "Von Berlin bis München — Kindergarten, Grundschule, Sekundarstufe I/II, Abitur.",
        "trust_count": "Vertraut von Schulen in allen 16 Bundesländern",
        "currency_sample": "€ 4.800 / Halbjahr",
        "calendar_sample": "2 Halbjahre — August/September bis Juni/Juli",
        "regulatory_line": "Konform mit den Bildungsplänen der KMK und der Bundesländer.",
        "anchor_city": "Berlin / München",
        "regional_phrase": "deutsche Schulen",
        "testimonial": {
            "quote": "Halbjahreszeugnisse, Abiturvorbereitung, DSGVO-konform, Elternkommunikation auf Deutsch. Endlich.",
            "author": "Schulleiterin, Gymnasium in Bayern",
            "credential": "Klasse 5–13 · 980 Schüler",
        },
        "case_study_chips": [
            "Halbjahreszeugnisse + Abiturnoten-Roll-up",
            "16 Bundesländer-spezifische Lehrpläne",
            "SEPA-Lastschrift + Klassenkasse + DSGVO-konform",
        ],
    },
    "ES": {
        "country_name": "España",
        "greeting": "Bienvenidos",
        "headline_lead": "Diseñado para escuelas españolas",
        "hero_subline": "De Madrid a Barcelona — Infantil, Primaria, ESO, Bachillerato, Selectividad/EvAU.",
        "trust_count": "Utilizado por colegios en las 17 comunidades autónomas",
        "currency_sample": "€ 3 500 / trimestre",
        "calendar_sample": "3 trimestres — septiembre a junio",
        "regulatory_line": "Alineado con la LOMLOE y los currículos autonómicos.",
        "anchor_city": "Madrid / Barcelona",
        "regional_phrase": "colegios españoles",
        "testimonial": {
            "quote": "Boletines trimestrales, EvAU/Selectividad prep, comunicación con padres en español. Por fin.",
            "author": "Director, colegio concertado en Madrid",
            "credential": "Infantil–Bachillerato · 1,100 alumnos",
        },
        "case_study_chips": [
            "LOMLOE + currículos autonómicos",
            "Selectividad / EvAU tracking",
            "SEPA + Bizum + transferencia bancaria",
        ],
    },
    "IT": {
        "country_name": "Italia",
        "greeting": "Benvenuti",
        "headline_lead": "Progettato per le scuole italiane",
        "hero_subline": "Da Roma a Milano — Scuola dell'infanzia, primaria, secondaria di I/II grado, Maturità.",
        "trust_count": "Utilizzato da scuole in tutte le 20 regioni",
        "currency_sample": "€ 3 800 / quadrimestre",
        "calendar_sample": "2 quadrimestri — settembre a giugno",
        "regulatory_line": "Conforme alle Indicazioni Nazionali del MIM/MIUR.",
        "anchor_city": "Roma / Milano",
        "regional_phrase": "scuole italiane",
        "testimonial": {
            "quote": "Pagelle quadrimestrali, Maturità prep, comunicazione genitori in italiano, GDPR-pulito.",
            "author": "Dirigente Scolastico, liceo di Milano",
            "credential": "Scuola primaria–liceo · 1,250 alunni",
        },
        "case_study_chips": [
            "Indicazioni Nazionali MIM/MIUR",
            "Esami di Stato + Maturità tracking",
            "PagoPA + SDD + bonifico bancario",
        ],
    },
    "GB": {
        "country_name": "United Kingdom",
        "greeting": "Welcome",
        "headline_lead": "Built for UK schools — Reception through Year 13",
        "hero_subline": "From London to Edinburgh — Nursery, Primary, Secondary, Sixth Form, GCSE + A-Level + IB.",
        "trust_count": "Trusted by schools across England, Scotland, Wales, and Northern Ireland",
        "currency_sample": "£ 4,200 / term",
        "calendar_sample": "3 terms with half-terms — September to July",
        "regulatory_line": "Aligned with the DfE National Curriculum and Ofqual examination frameworks.",
        "anchor_city": "London",
        "regional_phrase": "UK schools",
        "testimonial": {
            "quote": "Half-term planning, GCSE + A-Level grade-flight, and Sixth Form UCAS pipeline in one shop.",
            "author": "Bursar, independent school in Surrey",
            "credential": "Reception–Year 13 · 850 pupils",
        },
        "case_study_chips": [
            "Half-term + three-term planner",
            "GCSE + A-Level + IB unified grade-flight",
            "UCAS pipeline + parental contributions tracker",
        ],
    },
    "IE": {
        "country_name": "Ireland / Éire",
        "greeting": "Fáilte",
        "headline_lead": "Built for Irish schools",
        "hero_subline": "From Dublin to Cork — Junior Infants, Primary, Secondary, Junior Cert, Leaving Cert.",
        "trust_count": "Trusted by Catholic, multi-denominational, and Gaelscoil schools nationwide",
        "currency_sample": "€ 4,000 / term",
        "calendar_sample": "3 terms — September to June",
        "regulatory_line": "Aligned with the Department of Education and NCCA curriculum.",
        "anchor_city": "Dublin",
        "regional_phrase": "Irish schools",
        "testimonial": {
            "quote": "Junior Cert and Leaving Cert side by side, Aladdin-friendly export, CAO pipeline. Brilliant.",
            "author": "Principal, voluntary secondary in Dublin",
            "credential": "1st year–6th year · 700 students",
        },
        "case_study_chips": [
            "Junior Cycle Profile of Achievement (JCPA)",
            "Leaving Cert + LCA + LCVP unified",
            "CAO pipeline + SEPA Direct Debit",
        ],
    },

    # ─── Americas ───────────────────────────────────────────────────────────
    "US": {
        "country_name": "United States",
        "greeting": "Welcome",
        "headline_lead": "Built for American schools",
        "hero_subline": "From New York to Los Angeles — Pre-K, Elementary, Middle, High, AP, SAT/ACT prep.",
        "trust_count": "Trusted by public, charter, private, and parochial schools across all 50 states",
        "currency_sample": "$ 12,500 / semester",
        "calendar_sample": "2 semesters — August/September to May/June",
        "regulatory_line": "Aligned with state Common Core, NGSS, and AP frameworks; FERPA + COPPA compliant.",
        "anchor_city": "Major US metros",
        "regional_phrase": "American schools",
        "testimonial": {
            "quote": "GPA roll-up, AP weighting, IEP visibility, FERPA controls — and a parent app that doesn't time out.",
            "author": "Head of School, charter K-12 in the Midwest",
            "credential": "1,300 students · IB Diploma + AP tracks",
        },
        "case_study_chips": [
            "GPA roll-up + AP/Honors weighting",
            "IEP / 504 plan visibility for caseworkers",
            "FERPA + COPPA compliance baseline",
        ],
    },
    "CA": {
        "country_name": "Canada",
        "greeting": "Welcome / Bienvenue",
        "headline_lead": "Built for Canadian schools — provincial + Quebec",
        "headline_lead_native": "Conçu pour les écoles canadiennes",
        "hero_subline": "From Toronto to Vancouver to Montréal — K-12 provincial + Québec primaire/secondaire/CÉGEP.",
        "trust_count": "Trusted by schools across all 10 provinces + 3 territories",
        "currency_sample": "CA$ 5,500 / semester",
        "calendar_sample": "2 semesters — September to June",
        "regulatory_line": "Aligned with provincial Ministries of Education + Québec MEES.",
        "anchor_city": "Toronto / Montréal / Vancouver",
        "regional_phrase": "Canadian schools / écoles canadiennes",
    },
    "MX": {
        "country_name": "México",
        "greeting": "Bienvenidos",
        "headline_lead": "Diseñado para escuelas mexicanas",
        "hero_subline": "De CDMX a Monterrey — Preescolar, Primaria, Secundaria, Bachillerato, EvAU/ENP.",
        "trust_count": "Utilizado por escuelas en todos los 32 estados",
        "currency_sample": "MX$ 12,500 / semestre",
        "calendar_sample": "2 semestres — agosto a junio (Nueva Escuela Mexicana)",
        "regulatory_line": "Alineado con la Nueva Escuela Mexicana y los planes SEP.",
        "anchor_city": "Ciudad de México",
        "regional_phrase": "escuelas mexicanas",
        "testimonial": {
            "quote": "Boletas semestrales NEM, preparación COMIPEMS, comunicación con padres en español. Por fin nuestro sistema.",
            "author": "Director, colegio particular en CDMX",
            "credential": "Preescolar–Bachillerato · 1,400 alumnos",
        },
        "case_study_chips": [
            "Nueva Escuela Mexicana boletas + PEMC",
            "COMIPEMS + EXANI II tracking",
            "SPEI + tarjeta + OXXO Pay colegiaturas",
        ],
    },
    "BR": {
        "country_name": "Brasil",
        "greeting": "Bem-vindos",
        "headline_lead": "Projetado para escolas brasileiras",
        "hero_subline": "Do Rio a São Paulo — Educação Infantil, Fundamental I/II, Ensino Médio, ENEM.",
        "trust_count": "Utilizado por escolas em todos os 26 estados + DF",
        "currency_sample": "R$ 4 800 / bimestre",
        "calendar_sample": "4 bimestres — fevereiro a dezembro",
        "regulatory_line": "Alinhado à BNCC e às matrizes do MEC e INEP.",
        "anchor_city": "São Paulo / Rio de Janeiro",
        "regional_phrase": "escolas brasileiras",
        "testimonial": {
            "quote": "Boletim bimestral alinhado à BNCC, PIX integrado, comunicação no WhatsApp dos pais. Vida nova.",
            "author": "Diretor pedagógico, colégio em São Paulo",
            "credential": "1,900 alunos · Fundamental + Ensino Médio",
        },
        "case_study_chips": [
            "Boletim BNCC com 4 bimestres",
            "ENEM + vestibular tracking",
            "PIX + boleto bancário integrados",
        ],
    },
    "AR": {
        "country_name": "Argentina",
        "greeting": "Bienvenidos",
        "headline_lead": "Diseñado para escuelas argentinas",
        "hero_subline": "De Buenos Aires a Córdoba — Nivel Inicial, Primaria, Secundaria (Ciclo Básico + Orientado).",
        "trust_count": "Utilizado por escuelas en las 23 provincias + CABA",
        "currency_sample": "AR$ 180.000 / cuatrimestre",
        "calendar_sample": "2 cuatrimestres — marzo a diciembre (hemisferio sur)",
        "regulatory_line": "Alineado con los Núcleos de Aprendizajes Prioritarios del CFE.",
        "anchor_city": "Buenos Aires",
        "regional_phrase": "escuelas argentinas",
        "testimonial": {
            "quote": "Boletines cuatrimestrales, calendario del hemisferio sur, MercadoPago integrado. Andábamos a ciegas antes.",
            "author": "Rectora, colegio privado en CABA",
            "credential": "Nivel Inicial–Secundario · 950 alumnos",
        },
        "case_study_chips": [
            "NAP cuatrimestres + Ciclo Básico/Orientado",
            "Calendario hemisferio sur (marzo–diciembre)",
            "MercadoPago + Pagofácil + Rapipago",
        ],
    },
    "CO": {
        "country_name": "Colombia",
        "greeting": "Bienvenidos",
        "headline_lead": "Diseñado para colegios colombianos",
        "hero_subline": "De Bogotá a Medellín — Preescolar, Básica Primaria/Secundaria, Media, Pruebas Saber/ICFES.",
        "trust_count": "Utilizado por colegios en los 32 departamentos",
        "currency_sample": "COL$ 850.000 / período",
        "calendar_sample": "4 períodos — enero a noviembre",
        "regulatory_line": "Alineado con los Lineamientos del MEN y las Pruebas Saber.",
        "anchor_city": "Bogotá",
        "regional_phrase": "colegios colombianos",
        "testimonial": {
            "quote": "Períodos académicos, prep Saber 11, comunicación con acudientes — la plataforma habla nuestro español.",
            "author": "Rector, colegio bilingüe en Medellín",
            "credential": "Preescolar–Media · 1,200 estudiantes",
        },
        "case_study_chips": [
            "Lineamientos MEN 4 períodos",
            "Pruebas Saber 3°/5°/9°/11° tracking",
            "PSE + Nequi + Daviplata + tarjeta",
        ],
    },

    # ─── Oceania ────────────────────────────────────────────────────────────
    "AU": {
        "country_name": "Australia",
        "greeting": "G'day / Welcome",
        "headline_lead": "Built for Australian schools",
        "hero_subline": "From Sydney to Perth — Kindergarten, Primary, Secondary, Year 12 ATAR.",
        "trust_count": "Trusted by Public, Catholic, and Independent schools across all 8 states/territories",
        "currency_sample": "AU$ 4,200 / term",
        "calendar_sample": "4 terms — late January to mid-December",
        "regulatory_line": "Aligned with the Australian Curriculum (ACARA) and state ATAR frameworks.",
        "anchor_city": "Sydney / Melbourne",
        "regional_phrase": "Australian schools",
        "testimonial": {
            "quote": "ATAR pipeline, four-term calendar, NAPLAN analytics, Compass-friendly export. Sorted.",
            "author": "Deputy Principal, independent school in NSW",
            "credential": "K–Year 12 · 1,300 students",
        },
        "case_study_chips": [
            "ACARA + state ATAR frameworks",
            "NAPLAN Year 3/5/7/9 analytics",
            "BPAY + direct debit + parent portal",
        ],
    },
    "NZ": {
        "country_name": "Aotearoa / New Zealand",
        "greeting": "Kia ora",
        "headline_lead": "Built for Aotearoa schools",
        "hero_subline": "From Auckland to Wellington — Early Childhood, Years 1-13, NCEA Levels 1/2/3.",
        "trust_count": "Trusted by State, State-integrated, Private, and Kura Kaupapa Māori schools",
        "currency_sample": "NZ$ 3,800 / term",
        "calendar_sample": "4 terms — late January to mid-December",
        "regulatory_line": "Aligned with the New Zealand Curriculum + Te Marautanga o Aotearoa + NZQA NCEA.",
        "anchor_city": "Auckland / Wellington",
        "regional_phrase": "Aotearoa / New Zealand schools",
        "testimonial": {
            "quote": "NCEA Level 1/2/3 credit tracking, te reo Māori bilingual reports, school-shop integrated. Ka pai.",
            "author": "Principal, state-integrated school in Wellington",
            "credential": "Year 1–13 · 900 ākonga",
        },
        "case_study_chips": [
            "NCEA Level 1/2/3 + UE credit tracking",
            "Te Marautanga o Aotearoa bilingual reports",
            "POLi + bank deposit + parent portal",
        ],
    },
}


# Regional fallback voice — used when a country isn't in the hand-researched
# list above but has a regional default in country_localization.
_REGIONAL_MARKETING_VOICE: dict[str, dict[str, Any]] = {
    "africa-anglophone": {
        "country_name": "across Anglophone Africa",
        "greeting": "Welcome",
        "headline_lead": "Built for African schools",
        "hero_subline": "Curriculum, terms, exam tracking — all locally configured to match your national education board.",
        "trust_count": "Trusted by schools across the continent",
        "currency_sample": "Local currency supported",
        "calendar_sample": "3 terms — most African systems",
        "regulatory_line": "Aligned with national curriculum and examinations.",
        "anchor_city": "Major African cities",
        "regional_phrase": "African schools",
    },
    "africa-francophone": {
        "country_name": "à travers l'Afrique francophone",
        "greeting": "Bienvenue",
        "headline_lead": "Conçu pour les écoles africaines francophones",
        "hero_subline": "Maternelle, Primaire, Collège, Lycée, Baccalauréat — adapté au système éducatif de votre pays.",
        "trust_count": "Utilisé par des établissements à travers l'Afrique francophone",
        "currency_sample": "FCFA / monnaie locale",
        "calendar_sample": "3 trimestres — système francophone",
        "regulatory_line": "Aligné sur les programmes nationaux et les examens.",
        "anchor_city": "Grandes villes africaines",
        "regional_phrase": "écoles africaines francophones",
    },
    "africa-arabic": {
        "country_name": "across Arabic-speaking Africa",
        "greeting": "أهلاً وسهلاً (Ahlan)",
        "headline_lead": "Built for Arabic-medium schools across North Africa",
        "hero_subline": "Bilingual Arabic + French curriculum support, Hijri-parallel calendar, MoE-aligned.",
        "trust_count": "Trusted by schools across the Maghreb and beyond",
        "currency_sample": "Local currency supported",
        "calendar_sample": "2 semesters or 3 terms — MoE-aligned",
        "regulatory_line": "Aligned with national curricula and Ministry of Education.",
        "anchor_city": "Major cities",
        "regional_phrase": "Arabic-medium schools",
    },
    "europe-continental": {
        "country_name": "across continental Europe",
        "greeting": "Welcome / Bienvenue / Willkommen",
        "headline_lead": "Built for European schools",
        "hero_subline": "Kindergarten through Baccalauréat / Abitur / Diploma di Maturità.",
        "trust_count": "Trusted by schools across continental Europe",
        "currency_sample": "€ supported",
        "calendar_sample": "2 semesters or 3 trimesters — country-specific",
        "regulatory_line": "Aligned with country curricula and examinations.",
        "anchor_city": "Major European cities",
        "regional_phrase": "European schools",
    },
    "europe-romance": {
        "country_name": "across Romance-language Europe",
        "greeting": "Bienvenue / Bienvenidos / Benvenuti",
        "headline_lead": "Conçu pour les écoles européennes",
        "hero_subline": "Maternelle, Primaire, Secondaire — adapté à votre système national.",
        "trust_count": "Utilisé par des écoles à travers l'Europe romane",
        "currency_sample": "€",
        "calendar_sample": "3 trimestres ou 2 semestres",
        "regulatory_line": "Aligné sur les programmes nationaux.",
        "anchor_city": "Grandes villes européennes",
        "regional_phrase": "écoles européennes",
    },
    "europe-nordic": {
        "country_name": "across the Nordic countries",
        "greeting": "Velkommen / Tervetuloa / Välkommen",
        "headline_lead": "Built for Nordic schools",
        "hero_subline": "Grunnskole, Folkeskole, Gymnasium — full Nordic-system support.",
        "trust_count": "Trusted by schools across Scandinavia",
        "currency_sample": "Local Nordic currencies",
        "calendar_sample": "2 semesters — August to June",
        "regulatory_line": "Aligned with Nordic Ministry of Education frameworks.",
        "anchor_city": "Major Nordic cities",
        "regional_phrase": "Nordic schools",
    },
    "europe-eastern": {
        "country_name": "across Eastern Europe",
        "greeting": "Welcome / Witam / Vítejte",
        "headline_lead": "Built for Eastern European schools",
        "hero_subline": "From Warsaw to Bucharest — primary, secondary, gymnasium, matura.",
        "trust_count": "Trusted by schools across the region",
        "currency_sample": "Local currency",
        "calendar_sample": "2 semesters — September to June",
        "regulatory_line": "Aligned with national curricula and matura exams.",
        "anchor_city": "Major Eastern European cities",
        "regional_phrase": "Eastern European schools",
    },
    "latam-spanish": {
        "country_name": "a través de América Latina",
        "greeting": "Bienvenidos",
        "headline_lead": "Diseñado para escuelas latinoamericanas",
        "hero_subline": "Preescolar, Primaria, Secundaria, Bachillerato — adaptado a tu sistema nacional.",
        "trust_count": "Utilizado por colegios en todo Latinoamérica",
        "currency_sample": "Moneda local",
        "calendar_sample": "2 semestres o 4 períodos — según el país",
        "regulatory_line": "Alineado con los programas y exámenes nacionales.",
        "anchor_city": "Principales ciudades latinoamericanas",
        "regional_phrase": "escuelas latinoamericanas",
    },
    "latam-portuguese": {
        "country_name": "em todo o Brasil e África lusófona",
        "greeting": "Bem-vindos",
        "headline_lead": "Projetado para escolas lusófonas",
        "hero_subline": "Educação Infantil, Fundamental, Médio — adaptado ao seu sistema nacional.",
        "trust_count": "Utilizado por escolas em todo o mundo lusófono",
        "currency_sample": "Moeda local",
        "calendar_sample": "4 bimestres ou 2 semestres",
        "regulatory_line": "Alinhado às matrizes nacionais.",
        "anchor_city": "Principais cidades",
        "regional_phrase": "escolas lusófonas",
    },
    "east-asia": {
        "country_name": "across East Asia",
        "greeting": "歡迎 / Welcome",
        "headline_lead": "Built for East Asian schools",
        "hero_subline": "From kindergarten to university entrance prep — full local-system support.",
        "trust_count": "Trusted by schools across East Asia",
        "currency_sample": "Local currency",
        "calendar_sample": "2 semesters — country-specific",
        "regulatory_line": "Aligned with national curriculum frameworks.",
        "anchor_city": "Major East Asian cities",
        "regional_phrase": "East Asian schools",
    },
    "south-asia": {
        "country_name": "across South Asia",
        "greeting": "नमस्ते / Welcome",
        "headline_lead": "Built for South Asian schools",
        "hero_subline": "Pre-Primary through Board exams — lakh-grouped fees + multi-medium support.",
        "trust_count": "Trusted by schools across the subcontinent",
        "currency_sample": "Local currency (lakh-grouped)",
        "calendar_sample": "3 terms — April to March",
        "regulatory_line": "Aligned with national board curricula.",
        "anchor_city": "Major South Asian cities",
        "regional_phrase": "South Asian schools",
    },
    "southeast-asia": {
        "country_name": "across Southeast Asia",
        "greeting": "Selamat Datang / สวัสดี / Welcome",
        "headline_lead": "Built for Southeast Asian schools",
        "hero_subline": "Multi-lingual support, MoE-aligned curricula, regional exam tracking.",
        "trust_count": "Trusted by schools across the ASEAN region",
        "currency_sample": "Local currency",
        "calendar_sample": "2 semesters — country-specific",
        "regulatory_line": "Aligned with country MoE frameworks.",
        "anchor_city": "Major SEA cities",
        "regional_phrase": "Southeast Asian schools",
    },
    "middle-east": {
        "country_name": "across the Middle East",
        "greeting": "أهلاً وسهلاً (Ahlan)",
        "headline_lead": "Built for Middle Eastern schools",
        "hero_subline": "Bilingual Arabic + English curriculum, Hijri-parallel calendar, MoE-aligned.",
        "trust_count": "Trusted by schools across the GCC and Levant",
        "currency_sample": "Local currency",
        "calendar_sample": "3 terms — September to July (Hijri parallel)",
        "regulatory_line": "Aligned with MoE frameworks and regional exam boards.",
        "anchor_city": "Major Middle East cities",
        "regional_phrase": "Middle Eastern schools",
    },
    "oceania": {
        "country_name": "across the Pacific",
        "greeting": "Welcome / Talofa / Mālō",
        "headline_lead": "Built for Pacific Island schools",
        "hero_subline": "Early Childhood, Primary, Secondary — adapted to each nation's system.",
        "trust_count": "Trusted by schools across the Pacific",
        "currency_sample": "Local currency",
        "calendar_sample": "4 terms or 2 semesters — country-specific",
        "regulatory_line": "Aligned with each country's MoE framework.",
        "anchor_city": "Major Pacific cities",
        "regional_phrase": "Pacific Island schools",
    },
    "caribbean": {
        "country_name": "across the Caribbean",
        "greeting": "Welcome",
        "headline_lead": "Built for Caribbean schools",
        "hero_subline": "Early Childhood, Primary, Secondary, CSEC + CAPE exam tracking.",
        "trust_count": "Trusted by schools across CARICOM",
        "currency_sample": "Local currency",
        "calendar_sample": "3 terms — September to July",
        "regulatory_line": "Aligned with the Caribbean Examinations Council (CXC).",
        "anchor_city": "Major Caribbean cities",
        "regional_phrase": "Caribbean schools",
    },
    "generic": {
        "country_name": "worldwide",
        "greeting": "Welcome",
        "headline_lead": "Built for schools worldwide",
        "hero_subline": "Every country, every curriculum — adapted to your local education system.",
        "trust_count": "Trusted by international institutions across continents",
        "currency_sample": "Multi-currency",
        "calendar_sample": "Country-adaptive calendar systems",
        "regulatory_line": "Aligned with national curricula in every market we serve.",
        "anchor_city": "Major global cities",
        "regional_phrase": "international schools",
    },
}


def _country_to_regional_key(cc: str) -> str:
    """Map a country code to its regional marketing voice key."""
    try:
        from apps.siteconfig._seed_country_localization import COUNTRY_REGIONAL_DEFAULT
        return COUNTRY_REGIONAL_DEFAULT.get(cc, "generic")
    except Exception:  # noqa: BLE001
        return "generic"


def _resolve_voice(cc: str) -> dict[str, Any]:
    """Return the marketing voice dict for the given country code."""
    if not cc:
        return dict(_REGIONAL_MARKETING_VOICE["generic"])
    if cc in _COUNTRY_MARKETING_VOICE:
        return dict(_COUNTRY_MARKETING_VOICE[cc])
    region_key = _country_to_regional_key(cc)
    if region_key in _REGIONAL_MARKETING_VOICE:
        return dict(_REGIONAL_MARKETING_VOICE[region_key])
    return dict(_REGIONAL_MARKETING_VOICE["generic"])


def marketing_local_context(request) -> dict:
    """Emit `marketing_local` into every template render (cheap, defensive).

    Reads the `localization` dict already emitted by the localization context
    processor (so we don't re-resolve country), then layers in the voice dict
    plus a few cross-cut convenience values.
    """
    try:
        from apps.siteconfig.country_localization_service import resolve_country_for_request
        cc = resolve_country_for_request(request)
        voice = _resolve_voice(cc)

        # Localization values already resolved elsewhere — pluck them so
        # marketing templates can read everything from one dict.
        from apps.siteconfig.country_localization_service import (
            get_default_language,
            resolve_language_for_request,
        )
        lang = resolve_language_for_request(request, cc) or get_default_language(cc) or "en"

        # Native-language headline preferred for visitors whose Accept-Language
        # confirms the local language. e.g. CM-FR visitor sees the French
        # headline; CM-EN visitor sees the English headline.
        headline = voice.get("headline_lead", "")
        native_headline = voice.get("headline_lead_native", "")
        if native_headline and lang and not headline.lower().startswith(lang.lower()):
            # Prefer native when visitor language matches a non-English market default
            if lang in ("fr", "es", "pt", "de", "it", "ar", "hi", "zh", "zh-hans", "zh-hant",
                        "ja", "ko", "th", "vi", "id", "ms", "tr", "he"):
                headline = native_headline

        # Wave 12 (v3.62.16 — 2026-05-23): also surface per-country
        # testimonial + case-study chips when present. Operator can override
        # both via CountryRegistry.cockpit_override_payload["marketing_voice"]
        # (Wave 12 — see below).
        testimonial = voice.get("testimonial") if isinstance(voice.get("testimonial"), dict) else {}
        chips = voice.get("case_study_chips") or []
        if not isinstance(chips, list):
            chips = []

        # Wave 12: pull DB override layer if operator has stashed a
        # `marketing_voice` block in CountryRegistry.cockpit_override_payload.
        # Falls through silently when DB row / column / key missing.
        try:
            from apps.siteconfig.country_localization_service import _load_db_override
            db = _load_db_override(cc) if cc else {}
            mv = (db.get("marketing_voice") if isinstance(db, dict) else {}) or {}
            if isinstance(mv, dict) and mv:
                # Scalars override directly; dict/list keys merge per shape.
                for k in ("country_name", "greeting", "headline_lead",
                          "headline_lead_native", "hero_subline", "trust_count",
                          "currency_sample", "calendar_sample", "regulatory_line",
                          "anchor_city", "regional_phrase"):
                    if mv.get(k):
                        voice[k] = mv[k]
                if isinstance(mv.get("testimonial"), dict):
                    testimonial = mv["testimonial"]
                if isinstance(mv.get("case_study_chips"), list):
                    chips = mv["case_study_chips"]
                # Re-pick headline after override.
                headline = voice.get("headline_lead") or headline
                native_headline = voice.get("headline_lead_native") or native_headline
                if native_headline and lang in ("fr", "es", "pt", "de", "it", "ar",
                                                "hi", "zh", "zh-hans", "zh-hant",
                                                "ja", "ko", "th", "vi", "id", "ms",
                                                "tr", "he"):
                    headline = native_headline
        except Exception:  # noqa: BLE001
            pass

        out = {
            "country_code":      cc,
            "country_name":      voice.get("country_name", ""),
            "language_code":     lang,
            "greeting":          voice.get("greeting", "Welcome"),
            "headline_lead":     headline,
            "headline_lead_global": voice.get("headline_lead", ""),
            "hero_subline":      voice.get("hero_subline", ""),
            "trust_count":       voice.get("trust_count", ""),
            "currency_sample":   voice.get("currency_sample", ""),
            "calendar_sample":   voice.get("calendar_sample", ""),
            "regulatory_line":   voice.get("regulatory_line", ""),
            "anchor_city":       voice.get("anchor_city", ""),
            "regional_phrase":   voice.get("regional_phrase", ""),
            "testimonial":       {
                "quote":      str(testimonial.get("quote", "")) if testimonial else "",
                "author":     str(testimonial.get("author", "")) if testimonial else "",
                "credential": str(testimonial.get("credential", "")) if testimonial else "",
            } if testimonial else {},
            "case_study_chips":  [str(c) for c in chips if c],
            "_resolved":         True,
        }
    except Exception:  # noqa: BLE001 — never break marketing render
        out = {
            "country_code": "", "country_name": "worldwide",
            "language_code": "en", "greeting": "Welcome",
            "headline_lead": "Built for schools worldwide",
            "headline_lead_global": "Built for schools worldwide",
            "hero_subline": "Every country, every curriculum.",
            "trust_count": "Trusted by international institutions",
            "currency_sample": "Multi-currency", "calendar_sample": "Country-adaptive",
            "regulatory_line": "", "anchor_city": "", "regional_phrase": "schools",
            "testimonial": {}, "case_study_chips": [],
            "_resolved": False,
        }
    return {"marketing_local": out}
