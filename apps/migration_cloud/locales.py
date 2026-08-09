"""Multilingual synonym overlay seed for the Migration Cloud ontology.

The seeded ``CANONICAL_ONTOLOGY`` in ``ontology/catalog.py`` ships
synonyms for en/fr/es/ar/pt — the platform's launch languages. Real
school deployments span far more: German, Italian, Chinese, Hindi,
Japanese, Korean, Vietnamese, Indonesian, Russian, Turkish, Swahili,
Hausa, Yoruba, Amharic, Twi, Pidgin English, Urdu, Bengali, Tamil, etc.

This module ships a *baseline overlay* — synonyms for the most common
canonical fields across ~20 additional languages — that
``all_synonyms()`` automatically merges in. Tenants override or extend
via ``RuntimeDefaults.payload['migration_cloud.ontology.synonyms_overlay']``
in the usual cascade (env → RuntimeDefaults → seed).

The overlay shape mirrors the catalog::

    {
        "<domain>": {
            "<canonical_field>": {
                "<lang_code>": ["synonym_1", "synonym_2", ...],
            }
        }
    }

Adding a language: extend ``BASELINE_OVERLAY`` below. Adding a field:
extend the relevant ``"<canonical_field>"`` dict. Both are reviewable in
PRs and exercised by `tests/test_ontology.py` (the concurrent agent's
suite asserts every overlay language is well-formed).

Coverage rationale:
    The overlay focuses on the ~25 "always-present" fields (identifiers,
    names, contact, enrollment, grade level, dates). Tail fields (e.g.
    custody.granted_at) remain English-only because no school migration
    has ever asked for them in non-English headers. Tenants needing
    those can layer their own overlay.
"""

from __future__ import annotations

# Each top-level dict is one extra language. Synonyms must be lowercased,
# whitespace-normalised (use ``_`` for spaces in headers), and locale-
# appropriate (preferring snake_case header form over natural prose).


def _multi(*langs: tuple[str, list[str]]) -> dict[str, list[str]]:
    """Convenience constructor: _multi(("de", [...]), ("it", [...]))."""
    return {code: list(words) for code, words in langs}


BASELINE_OVERLAY: dict[str, dict[str, dict[str, list[str]]]] = {
    "students": {
        "external_id": {
            "de": ["schulernummer", "schueler_id", "matrikelnummer"],
            "it": ["matricola", "codice_studente"],
            "zh": ["学号", "学生编号"],
            "hi": ["chhatra_id", "vidhyarthi_id", "रोल_नंबर"],
            "ja": ["生徒番号", "学籍番号"],
            "ko": ["학번", "학생번호"],
            "vi": ["ma_hoc_sinh", "so_hoc_sinh"],
            "id": ["nis", "nomor_induk_siswa", "id_siswa"],
            "ru": ["номер_ученика", "табельный_номер"],
            "tr": ["ogrenci_no", "kayit_no"],
            "sw": ["nambari_ya_mwanafunzi", "id_mwanafunzi"],
            "ha": ["lambar_dalibi"],
            "yo": ["nomba_akeko"],
            "am": ["የተማሪ_መታወቂያ"],
            "tw": ["sukuufoɔ_nɔma"],
            "pid": ["pikin_id", "student_nomba"],
            "ur": ["talib_e_ilm_id", "rol_nambar"],
            "bn": ["chatra_id", "rol_nombor"],
            "ta": ["maanavar_kuri_yedu", "id"],
        },
        "first_name": {
            "de": ["vorname"],
            "it": ["nome"],
            "zh": ["名", "名字"],
            "hi": ["pratham_naam", "naam"],
            "ja": ["名", "名前"],
            "ko": ["이름"],
            "vi": ["ten", "ho_ten"],
            "id": ["nama_depan", "nama"],
            "ru": ["имя"],
            "tr": ["ad", "isim"],
            "sw": ["jina_la_kwanza"],
            "ha": ["sunan_farko"],
            "yo": ["oruko_akoko"],
            "am": ["ስም"],
            "tw": ["din_a_edi_kan"],
            "pid": ["fess_nem"],
            "ur": ["pehla_naam"],
            "bn": ["pratham_naam"],
            "ta": ["mudhal_peyar"],
        },
        "last_name": {
            "de": ["nachname", "familienname"],
            "it": ["cognome"],
            "zh": ["姓", "姓氏"],
            "hi": ["antim_naam", "surname"],
            "ja": ["姓", "苗字"],
            "ko": ["성", "성씨"],
            "vi": ["ho"],
            "id": ["nama_belakang", "nama_keluarga"],
            "ru": ["фамилия"],
            "tr": ["soyad", "soyadi"],
            "sw": ["jina_la_familia", "jina_la_ukoo"],
            "ha": ["sunan_iyali"],
            "yo": ["oruko_idile"],
            "am": ["የአያት_ስም"],
            "tw": ["abusuadin"],
            "pid": ["fadda_nem", "famli_nem"],
            "ur": ["khaandani_naam"],
            "bn": ["padobi"],
            "ta": ["kudumba_peyar"],
        },
        "middle_name": {
            "de": ["zweitname"],
            "it": ["secondo_nome"],
            "es": ["segundo_nombre", "nombre_intermedio"],
            "id": ["nama_tengah"],
            "ru": ["отчество"],
        },
        "date_of_birth": {
            "de": ["geburtsdatum", "geburtstag"],
            "it": ["data_di_nascita", "data_nascita"],
            "zh": ["出生日期", "出生年月"],
            "hi": ["janm_tithi", "जन्म_तिथि"],
            "ja": ["生年月日"],
            "ko": ["생년월일"],
            "vi": ["ngay_sinh"],
            "id": ["tanggal_lahir"],
            "ru": ["дата_рождения"],
            "tr": ["dogum_tarihi"],
            "sw": ["tarehe_ya_kuzaliwa"],
            "ha": ["ranar_haihuwa"],
            "yo": ["ojo_ibi"],
            "am": ["የልደት_ቀን"],
            "ur": ["tarikh_e_paidaish"],
            "bn": ["jonmo_tarikh"],
            "ta": ["pirantha_thedhi"],
        },
        "gender": {
            "de": ["geschlecht"],
            "it": ["sesso", "genere"],
            "zh": ["性别"],
            "hi": ["ling", "लिंग"],
            "ja": ["性別"],
            "ko": ["성별"],
            "vi": ["gioi_tinh"],
            "id": ["jenis_kelamin"],
            "ru": ["пол"],
            "tr": ["cinsiyet"],
            "sw": ["jinsia"],
            "ha": ["jinsi"],
            "yo": ["abo_tabi_ako"],
            "am": ["ጾታ"],
            "ur": ["jins"],
            "bn": ["lingo"],
            "ta": ["paalinam"],
        },
        "grade_level": {
            "de": ["klassenstufe", "jahrgang", "klasse"],
            "it": ["classe", "anno_scolastico"],
            "zh": ["年级", "班级"],
            "hi": ["kaksha", "कक्षा"],
            "ja": ["学年", "クラス"],
            "ko": ["학년", "반"],
            "vi": ["lop", "khoi"],
            "id": ["kelas", "tingkat"],
            "ru": ["класс"],
            "tr": ["sinif"],
            "sw": ["darasa", "kidato"],
            "ha": ["aji"],
            "yo": ["ipele"],
            "am": ["ክፍል"],
            "ur": ["jamaat"],
            "bn": ["sreni", "class"],
            "ta": ["vakuppu"],
        },
        "enrollment_status": {
            "de": ["status", "einschreibestatus"],
            "it": ["stato_iscrizione"],
            "fr": ["statut_inscription", "etat_inscription"],
            "es": ["estado_inscripcion", "estado_matricula"],
            "pt": ["status_matricula"],
            "zh": ["注册状态", "在学状态"],
            "ja": ["在籍状況"],
            "ko": ["재학상태"],
            "id": ["status_pendaftaran"],
            "ru": ["статус_зачисления"],
            "tr": ["kayit_durumu"],
            "sw": ["hali_ya_usajili"],
        },
        "email": {
            "de": ["email", "e_mail", "mail"],
            "it": ["email", "posta_elettronica"],
            "zh": ["邮箱", "电子邮件"],
            "ja": ["メール", "メールアドレス"],
            "ko": ["이메일"],
            "vi": ["thu_dien_tu"],
            "id": ["surel", "email"],
            "ru": ["почта", "электронная_почта"],
            "tr": ["eposta", "elektronik_posta"],
            "sw": ["barua_pepe"],
            "ha": ["imel"],
            "am": ["ኢሜይል"],
        },
        "phone": {
            "de": ["telefon", "telefonnummer", "handy"],
            "it": ["telefono", "cellulare"],
            "zh": ["电话", "手机"],
            "hi": ["phone", "mobile"],
            "ja": ["電話", "携帯"],
            "ko": ["전화", "휴대폰"],
            "vi": ["dien_thoai", "so_dien_thoai"],
            "id": ["telepon", "nomor_hp"],
            "ru": ["телефон"],
            "tr": ["telefon", "cep_telefonu"],
            "sw": ["simu", "nambari_ya_simu"],
            "ha": ["wayar_hannu", "lambar_waya"],
            "yo": ["foonu"],
            "am": ["ስልክ"],
        },
        "address": {
            "de": ["adresse", "anschrift"],
            "it": ["indirizzo"],
            "zh": ["地址", "住址"],
            "ja": ["住所"],
            "ko": ["주소"],
            "vi": ["dia_chi"],
            "id": ["alamat"],
            "ru": ["адрес"],
            "tr": ["adres"],
            "sw": ["anwani"],
            "ha": ["adireshi"],
            "am": ["አድራሻ"],
        },
        "admission_number": {
            "de": ["aufnahmenummer", "aufnahmenr"],
            "it": ["numero_iscrizione"],
            "zh": ["入学编号"],
            "hi": ["pravesh_sankhya", "एडमिशन_नंबर"],
            "ja": ["入学番号"],
            "ko": ["입학번호"],
            "vi": ["so_dang_ky"],
            "id": ["nomor_pendaftaran"],
            "tr": ["kayit_numarasi"],
            "sw": ["nambari_ya_uandikishaji"],
            "ur": ["dakhla_nambar"],
        },
    },
    "guardians": {
        "first_name": {
            "de": ["vorname_des_erziehungsberechtigten"],
            "zh": ["家长姓名"],
            "ja": ["保護者名"],
            "ko": ["보호자_이름"],
            "vi": ["ten_phu_huynh"],
            "id": ["nama_wali"],
            "sw": ["jina_la_mzazi"],
            "ha": ["sunan_iyaye"],
            "yo": ["oruko_obi"],
            "am": ["የወላጅ_ስም"],
            "ur": ["walidain_ka_naam"],
        },
        "relationship": {
            "de": ["beziehung", "verhaeltnis"],
            "it": ["parentela", "relazione"],
            "zh": ["关系"],
            "ja": ["続柄"],
            "ko": ["관계"],
            "vi": ["quan_he"],
            "id": ["hubungan"],
            "ru": ["родство"],
            "tr": ["yakinlik"],
            "sw": ["uhusiano"],
            "ha": ["dangantaka"],
            "am": ["ግንኙነት"],
        },
        "phone": {
            "de": ["telefon_eltern"],
            "zh": ["家长电话"],
            "ja": ["保護者電話"],
            "ko": ["보호자_전화"],
            "vi": ["dien_thoai_phu_huynh"],
            "id": ["telepon_wali"],
            "sw": ["simu_ya_mzazi"],
        },
        "email": {
            "de": ["email_eltern"],
            "zh": ["家长邮箱"],
            "id": ["email_wali"],
        },
    },
    "staff": {
        "external_id": {
            "de": ["personalnummer", "lehrernummer"],
            "it": ["matricola_personale", "codice_dipendente"],
            "zh": ["员工编号", "教师编号"],
            "ja": ["教職員番号"],
            "ko": ["직원번호"],
            "vi": ["ma_giao_vien", "ma_nhan_vien"],
            "id": ["nip", "nomor_induk_pegawai"],
            "ru": ["табельный_номер_сотрудника"],
            "tr": ["personel_no", "ogretmen_no"],
            "sw": ["nambari_ya_mwalimu"],
            "ha": ["lambar_malami"],
            "yo": ["nomba_olukoni"],
        },
        "first_name": {
            "de": ["vorname_lehrer"],
            "zh": ["教师姓名"],
            "vi": ["ten_giao_vien"],
            "id": ["nama_guru"],
            "sw": ["jina_la_mwalimu"],
        },
        "subject_taught": {
            "de": ["unterrichtetes_fach"],
            "it": ["materia_insegnata"],
            "zh": ["所教科目"],
            "hi": ["padhaya_jane_wala_vishay"],
            "ja": ["担当教科"],
            "ko": ["담당과목"],
            "vi": ["mon_day"],
            "id": ["mata_pelajaran"],
            "ru": ["преподаваемый_предмет"],
            "tr": ["okutulan_ders"],
            "sw": ["somo_linalofundishwa"],
        },
    },
    "grades": {
        "score": {
            "de": ["note", "punkte", "bewertung"],
            "it": ["voto", "punteggio"],
            "zh": ["成绩", "分数"],
            "hi": ["ank", "अंक"],
            "ja": ["成績", "得点"],
            "ko": ["성적", "점수"],
            "vi": ["diem", "diem_so"],
            "id": ["nilai"],
            "ru": ["оценка", "балл"],
            "tr": ["not", "puan"],
            "sw": ["alama", "pointi"],
            "ha": ["maki"],
            "yo": ["aami"],
            "am": ["ነጥብ"],
            "ur": ["nambar"],
        },
        "grade_letter": {
            "de": ["notenbuchstabe", "buchstabennote"],
            "it": ["voto_lettera"],
            "zh": ["等级"],
            "ja": ["評価"],
            "ko": ["등급"],
            "id": ["nilai_huruf"],
            "ru": ["буквенная_оценка"],
        },
        "term": {
            "de": ["halbjahr", "trimester"],
            "it": ["trimestre", "quadrimestre"],
            "zh": ["学期"],
            "ja": ["学期"],
            "ko": ["학기"],
            "vi": ["hoc_ky"],
            "id": ["semester"],
            "ru": ["четверть", "семестр"],
            "tr": ["donem"],
            "sw": ["muhula"],
        },
    },
    "attendance": {
        "date": {
            "de": ["datum"],
            "it": ["data"],
            "zh": ["日期"],
            "ja": ["日付"],
            "ko": ["날짜"],
            "vi": ["ngay"],
            "id": ["tanggal"],
            "ru": ["дата"],
            "tr": ["tarih"],
            "sw": ["tarehe"],
        },
        "status": {
            "de": ["anwesenheit", "status"],
            "it": ["presenza", "stato"],
            "zh": ["出勤状态"],
            "ja": ["出欠"],
            "ko": ["출결"],
            "vi": ["chuyen_can", "trang_thai"],
            "id": ["status_kehadiran"],
            "ru": ["посещаемость"],
            "tr": ["devam_durumu"],
            "sw": ["mahudhurio"],
            "am": ["ህልውና"],
        },
    },
    "finance": {
        "amount": {
            "de": ["betrag", "summe"],
            "it": ["importo", "somma"],
            "zh": ["金额"],
            "hi": ["raashi", "राशि"],
            "ja": ["金額"],
            "ko": ["금액"],
            "vi": ["so_tien"],
            "id": ["jumlah", "nominal"],
            "ru": ["сумма"],
            "tr": ["tutar", "miktar"],
            "sw": ["kiasi", "jumla"],
            "ha": ["adadi"],
        },
        "currency": {
            "de": ["waehrung"],
            "it": ["valuta"],
            "zh": ["货币"],
            "ja": ["通貨"],
            "ko": ["통화"],
            "vi": ["loai_tien"],
            "id": ["mata_uang"],
            "ru": ["валюта"],
            "tr": ["para_birimi"],
            "sw": ["sarafu"],
        },
        "due_date": {
            "de": ["faelligkeitsdatum", "zahlungsdatum"],
            "it": ["scadenza", "data_scadenza"],
            "zh": ["到期日", "缴费日期"],
            "ja": ["支払期日"],
            "ko": ["납기일"],
            "vi": ["ngay_den_han"],
            "id": ["tanggal_jatuh_tempo"],
            "ru": ["срок_оплаты"],
            "tr": ["son_odeme_tarihi"],
            "sw": ["tarehe_ya_malipo"],
        },
    },
    "enrollment": {
        "enrolled_at": {
            "de": ["einschreibungsdatum"],
            "it": ["data_iscrizione"],
            "zh": ["入学日期"],
            "ja": ["入学日"],
            "ko": ["입학일"],
            "vi": ["ngay_nhap_hoc"],
            "id": ["tanggal_masuk"],
            "ru": ["дата_поступления"],
            "tr": ["kayit_tarihi"],
            "sw": ["tarehe_ya_kujiunga"],
        },
        "academic_year": {
            "de": ["schuljahr"],
            "it": ["anno_accademico", "anno_scolastico"],
            "zh": ["学年"],
            "ja": ["年度"],
            "ko": ["학년도"],
            "vi": ["nam_hoc"],
            "id": ["tahun_ajaran"],
            "ru": ["учебный_год"],
            "tr": ["egitim_yili"],
            "sw": ["mwaka_wa_masomo"],
        },
    },
}


# --- French coverage seed (2026-08-08) --------------------------------------
#
# The catalog seeds `fr` on only ~13 of 123 canonical fields, so a French-
# headered SIS export from the platform's home market (Cameroon — French +
# English official languages) failed to auto-map on ~90% of fields and mass-
# quarantined. This block brings French to bedrock coverage across every
# domain. Synonyms are ASCII / accent-FREE snake_case: `_normalize_header`
# folds Latin diacritics (Prénom -> prenom, Numéro d'élève -> numero_d_eleve)
# before matching, so an accented header lands on its accent-free synonym here.
#
# Cameroon note: school-management software (and its CSV exports) carry French
# or English column headers, never local-language (Ewondo / Duala / Fulfulde)
# headers, so seeding local-language HEADERS would be theatre — French is the
# load-bearing second-official-language coverage this market actually needs.
# A tenant with genuinely bespoke headers still layers its own overlay via
# `RuntimeDefaults.payload['migration_cloud.ontology.synonyms_overlay']`.
_FRENCH_SEED_2026_08: dict[str, dict[str, list[str]]] = {
    "students": {
        "external_id": ["numero_eleve", "matricule", "matricule_eleve", "code_eleve", "identifiant_eleve", "id_eleve"],
        "admission_number": ["numero_inscription", "numero_admission", "matricule_inscription", "numero_dossier"],
        "first_name": ["prenom", "prenoms"],
        "last_name": ["nom", "nom_de_famille", "nom_famille"],
        "middle_name": ["deuxieme_prenom", "autre_prenom", "second_prenom"],
        "date_of_birth": ["date_de_naissance", "date_naissance", "ne_le", "nee_le", "naissance"],
        "gender": ["sexe", "genre"],
        "grade_level": ["classe", "niveau", "niveau_scolaire", "niveau_classe"],
        "enrollment_status": ["statut", "statut_inscription", "statut_eleve", "actif"],
        "email": ["courriel", "adresse_email", "mail", "mel", "email"],
        "phone": ["telephone", "tel", "numero_telephone", "portable", "mobile", "gsm"],
        "address": ["adresse", "adresse_domicile", "domicile", "residence", "adresse_postale"],
    },
    "guardians": {
        "guardian_external_id": ["numero_parent", "id_parent", "code_parent", "numero_tuteur", "identifiant_parent"],
        "student_external_id": ["numero_eleve", "matricule_eleve", "id_eleve", "numero_enfant"],
        "relationship": ["relation", "lien", "lien_de_parente", "parente", "qualite"],
        "first_name": ["prenom", "prenom_parent", "prenom_tuteur"],
        "last_name": ["nom", "nom_parent", "nom_tuteur", "nom_de_famille"],
        "email": ["courriel", "email_parent", "courriel_parent", "email"],
        "phone": ["telephone", "tel", "portable", "telephone_parent"],
        "is_primary": ["principal", "contact_principal", "parent_principal", "tuteur_principal"],
    },
    "staff": {
        "staff_external_id": ["numero_employe", "matricule_employe", "matricule_personnel", "id_employe", "matricule_enseignant", "numero_enseignant"],
        "first_name": ["prenom"],
        "last_name": ["nom", "nom_de_famille"],
        "email": ["courriel", "email_professionnel", "email"],
        "role": ["fonction", "poste", "titre", "intitule_poste", "role"],
        "department": ["departement", "service", "unite", "filiere"],
        "hire_date": ["date_embauche", "date_d_embauche", "date_recrutement", "date_entree", "date_debut"],
    },
    "enrollment": {
        "student_external_id": ["numero_eleve", "matricule_eleve", "id_eleve"],
        "academic_year": ["annee_scolaire", "annee_academique", "annee"],
        "grade_level": ["niveau", "niveau_scolaire"],
        "homeroom": ["classe", "groupe", "salle_de_classe", "section"],
        "enrollment_date": ["date_inscription", "date_d_inscription", "date_entree", "date_admission"],
        "exit_date": ["date_sortie", "date_depart", "date_de_sortie", "date_radiation"],
    },
    "academics": {
        "subject_code": ["code_matiere", "code_cours", "code_discipline"],
        "subject_name": ["matiere", "discipline", "intitule_matiere", "nom_matiere", "cours"],
        "credits": ["credits", "coefficient", "coefficients", "unites"],
        "department": ["departement", "filiere", "service"],
    },
    "sections": {
        "section_external_id": ["numero_section", "id_section", "code_classe", "id_classe", "numero_groupe"],
        "subject_code": ["code_matiere", "code_cours"],
        "teacher_external_id": ["numero_enseignant", "id_enseignant", "matricule_enseignant", "code_professeur"],
        "academic_year": ["annee_scolaire", "annee_academique"],
        "term": ["trimestre", "semestre", "periode", "sequence"],
    },
    "schedule": {
        "section_external_id": ["numero_section", "id_classe"],
        "day_of_week": ["jour", "jour_de_la_semaine", "jour_semaine"],
        "start_time": ["heure_debut", "heure_de_debut", "debut"],
        "end_time": ["heure_fin", "heure_de_fin", "fin"],
        "room": ["salle", "salle_de_classe", "local", "lieu"],
    },
    "attendance": {
        "student_external_id": ["numero_eleve", "matricule_eleve"],
        "date": ["date", "date_presence", "jour"],
        "status": ["statut", "presence", "etat", "absence"],
        "period": ["periode", "creneau", "heure"],
        "reason": ["motif", "raison", "commentaire", "observation"],
    },
    "grades": {
        "student_external_id": ["numero_eleve", "matricule_eleve"],
        "section_external_id": ["numero_section", "id_classe", "code_classe"],
        "assessment_name": ["evaluation", "controle", "devoir", "examen", "composition", "interrogation"],
        "score": ["note", "note_obtenue", "points", "resultat"],
        "max_score": ["note_maximale", "sur", "note_max", "bareme"],
        "letter_grade": ["mention", "appreciation", "note_lettre"],
        "term": ["trimestre", "semestre", "periode", "sequence"],
        "academic_year": ["annee_scolaire", "annee_academique"],
    },
    "transcripts": {
        "student_external_id": ["numero_eleve", "matricule_eleve"],
        "academic_year": ["annee_scolaire", "annee_academique"],
        "subject_code": ["code_matiere", "code_cours"],
        "final_grade": ["note_finale", "moyenne", "note_annuelle", "resultat_final"],
        "credits_earned": ["credits_obtenus", "coefficients", "unites_obtenues"],
        "gpa_points": ["points_moyenne", "moyenne_generale"],
    },
    "behavior": {
        "student_external_id": ["numero_eleve", "matricule_eleve"],
        "date": ["date", "date_incident"],
        "category": ["categorie", "type_incident", "nature", "infraction"],
        "description": ["description", "narratif", "details", "observation"],
        "consequence": ["consequence", "sanction", "mesure", "suite"],
    },
    "health": {
        "student_external_id": ["numero_eleve", "matricule_eleve"],
        "blood_type": ["groupe_sanguin", "groupe_de_sang"],
        "allergies": ["allergies", "allergie"],
        "medications": ["medicaments", "traitements", "prescriptions"],
        "immunizations": ["vaccinations", "vaccins", "vaccination"],
        "emergency_contact_name": ["contact_urgence", "personne_a_prevenir", "nom_contact_urgence"],
        "emergency_contact_phone": ["telephone_urgence", "tel_urgence", "numero_urgence", "telephone_contact_urgence"],
    },
    "finance": {
        "student_external_id": ["numero_eleve", "matricule_eleve"],
        "invoice_number": ["numero_facture", "numero_de_facture", "no_facture", "facture", "numero_recu", "reference_facture"],
        "fee_category": ["type_frais", "categorie_frais", "nature_frais", "rubrique"],
        "amount": ["montant", "valeur", "montant_frais", "somme"],
        "currency": ["devise", "monnaie", "code_devise"],
        "due_date": ["date_echeance", "date_d_echeance", "echeance", "date_limite", "date_de_paiement", "date_limite_de_paiement"],
        "paid_amount": ["montant_paye", "paye", "montant_regle", "versement"],
        "balance": ["solde", "reste", "reliquat", "restant_du", "montant_du"],
    },
    "payroll": {
        "staff_external_id": ["numero_employe", "matricule_employe", "matricule"],
        "pay_period": ["periode_paie", "periode", "mois_paie"],
        "gross_pay": ["salaire_brut", "brut", "remuneration_brute"],
        "net_pay": ["salaire_net", "net", "net_a_payer", "remuneration_nette"],
    },
    "communications": {
        "thread_external_id": ["numero_fil", "id_conversation", "id_discussion"],
        "sender_external_id": ["id_expediteur", "expediteur", "numero_expediteur"],
        "sent_at": ["envoye_le", "date_envoi", "horodatage"],
        "body": ["message", "texte", "contenu", "corps"],
    },
    "events": {
        "event_external_id": ["numero_evenement", "id_evenement"],
        "name": ["nom", "titre", "intitule", "nom_evenement"],
        "start_at": ["date_debut", "debut", "commence_le"],
        "end_at": ["date_fin", "fin", "termine_le"],
        "venue": ["lieu", "endroit", "salle", "emplacement"],
    },
    "library": {
        "item_external_id": ["numero_ouvrage", "id_livre", "code_livre", "cote"],
        "title": ["titre", "intitule"],
        "isbn": ["isbn"],
        "barcode": ["code_barres", "code_barre", "etiquette"],
        "borrower_external_id": ["numero_emprunteur", "id_emprunteur", "emprunte_par"],
        "due_date": ["date_retour", "a_rendre_le", "date_de_retour"],
    },
    "transport": {
        "route_name": ["itineraire", "ligne", "trajet", "circuit"],
        "stop_name": ["arret", "point_arret", "arret_bus", "point_ramassage"],
        "student_external_id": ["numero_eleve", "matricule_eleve"],
        "bus_label": ["bus", "vehicule", "numero_bus", "car"],
    },
    "hostel": {
        "hostel_name": ["internat", "dortoir", "pensionnat", "foyer"],
        "room_number": ["chambre", "numero_chambre", "lit", "numero_lit"],
        "student_external_id": ["numero_eleve", "matricule_eleve"],
    },
    "cafeteria": {
        "student_external_id": ["numero_eleve", "matricule_eleve"],
        "meal_plan": ["forfait_repas", "plan_repas", "formule_repas", "cantine"],
        "balance": ["solde", "credit", "solde_cantine"],
    },
    "alumni": {
        "alumnus_external_id": ["numero_ancien", "id_ancien", "numero_diplome"],
        "graduation_year": ["annee_diplome", "annee_obtention", "promotion", "annee_sortie"],
        "current_employer": ["employeur", "entreprise", "employeur_actuel", "societe"],
        "email": ["courriel", "email_contact", "email"],
    },
    "compliance": {
        "consent_type": ["type_consentement", "consentement", "autorisation"],
        "student_external_id": ["numero_eleve", "matricule_eleve"],
        "granted": ["accorde", "consenti", "autorise", "approuve"],
        "granted_at": ["date_consentement", "signe_le", "date_signature", "accorde_le"],
    },
}


def _merge_french_seed() -> None:
    """Fold the French coverage seed into BASELINE_OVERLAY under the ``fr`` key,
    additively (never dropping an existing overlay language or ``fr`` entry)."""
    for domain, fields in _FRENCH_SEED_2026_08.items():
        dom = BASELINE_OVERLAY.setdefault(domain, {})
        for field, syns in fields.items():
            field_langs = dom.setdefault(field, {})
            existing = list(field_langs.get("fr", []))
            field_langs["fr"] = list(dict.fromkeys([*existing, *syns]))


_merge_french_seed()


# --- Spanish + Portuguese coverage seed (2026-08-08) ------------------------
#
# Same gap the French seed closed, for the other two Latin launch languages:
# es / pt each carried synonyms on only ~13 of 123 canonical fields. Now that
# `_normalize_header` folds Latin diacritics, an accented Spanish / Portuguese
# header ("Apellido", "Número", "Endereço", "Matrícula", "Situação") normalizes
# to its accent-free synonym below. Same discipline as French: ASCII/accent-free
# snake_case, no within-domain collision, liaison / natural multi-word forms
# seeded so real headers match. "Global presence" — the platform serves Latin
# America and Lusophone Africa/Brazil, not just francophone markets.
_SPANISH_SEED_2026_08: dict[str, dict[str, list[str]]] = {
    "students": {
        "external_id": ["numero_estudiante", "matricula", "matricula_estudiante", "codigo_estudiante", "id_estudiante", "numero_matricula"],
        "admission_number": ["numero_admision", "numero_inscripcion", "numero_expediente"],
        "first_name": ["nombre", "nombres"],
        "last_name": ["apellido", "apellidos", "apellido_paterno"],
        "middle_name": ["segundo_nombre"],
        "date_of_birth": ["fecha_de_nacimiento", "fecha_nacimiento", "nacimiento"],
        "gender": ["sexo", "genero"],
        "grade_level": ["grado", "nivel", "curso"],
        "enrollment_status": ["estado", "estado_inscripcion", "estatus", "activo"],
        "email": ["correo", "correo_electronico", "email"],
        "phone": ["telefono", "celular", "movil", "numero_telefono"],
        "address": ["direccion", "domicilio", "residencia"],
    },
    "guardians": {
        "guardian_external_id": ["numero_padre", "id_padre", "id_tutor", "codigo_tutor", "numero_apoderado"],
        "student_external_id": ["numero_estudiante", "matricula_estudiante", "id_estudiante", "id_hijo"],
        "relationship": ["relacion", "parentesco", "vinculo"],
        "first_name": ["nombre", "nombre_padre", "nombre_tutor"],
        "last_name": ["apellido", "apellido_padre", "apellido_tutor"],
        "email": ["correo", "correo_padre", "email_padre"],
        "phone": ["telefono", "celular", "telefono_padre"],
        "is_primary": ["principal", "contacto_principal", "apoderado_principal", "tutor_principal"],
    },
    "staff": {
        "staff_external_id": ["numero_empleado", "matricula_empleado", "id_empleado", "numero_personal", "codigo_docente", "numero_docente"],
        "first_name": ["nombre"],
        "last_name": ["apellido", "apellidos"],
        "email": ["correo", "correo_institucional", "email"],
        "role": ["cargo", "puesto", "funcion", "rol"],
        "department": ["departamento", "area", "unidad"],
        "hire_date": ["fecha_contratacion", "fecha_ingreso", "fecha_alta", "fecha_inicio"],
    },
    "enrollment": {
        "student_external_id": ["numero_estudiante", "matricula_estudiante", "id_estudiante"],
        "academic_year": ["ano_escolar", "ano_academico", "ciclo_escolar", "ano_lectivo"],
        "grade_level": ["grado", "nivel"],
        "homeroom": ["seccion", "grupo", "aula", "salon"],
        "enrollment_date": ["fecha_inscripcion", "fecha_matricula", "fecha_ingreso", "fecha_alta"],
        "exit_date": ["fecha_salida", "fecha_baja", "fecha_retiro", "fecha_egreso"],
    },
    "academics": {
        "subject_code": ["codigo_materia", "codigo_asignatura", "codigo_curso"],
        "subject_name": ["materia", "asignatura", "curso", "nombre_materia"],
        "credits": ["creditos", "unidades", "horas_credito"],
        "department": ["departamento", "area"],
    },
    "sections": {
        "section_external_id": ["numero_seccion", "id_seccion", "codigo_grupo", "id_grupo"],
        "subject_code": ["codigo_materia", "codigo_asignatura"],
        "teacher_external_id": ["numero_docente", "id_docente", "codigo_profesor"],
        "academic_year": ["ano_escolar", "ano_academico"],
        "term": ["periodo", "semestre", "trimestre", "bimestre"],
    },
    "schedule": {
        "section_external_id": ["numero_seccion", "id_grupo"],
        "day_of_week": ["dia", "dia_de_la_semana", "dia_semana"],
        "start_time": ["hora_inicio", "hora_de_inicio", "inicio"],
        "end_time": ["hora_fin", "hora_de_fin", "fin"],
        "room": ["aula", "salon", "sala", "lugar"],
    },
    "attendance": {
        "student_external_id": ["numero_estudiante", "matricula_estudiante"],
        "date": ["fecha", "fecha_asistencia", "dia"],
        "status": ["estado", "asistencia", "marca"],
        "period": ["periodo", "hora", "bloque"],
        "reason": ["motivo", "razon", "comentario", "observacion"],
    },
    "grades": {
        "student_external_id": ["numero_estudiante", "matricula_estudiante"],
        "section_external_id": ["numero_seccion", "id_grupo", "codigo_grupo"],
        "assessment_name": ["evaluacion", "examen", "prueba", "tarea", "trabajo"],
        "score": ["nota", "calificacion", "puntaje", "puntos"],
        "max_score": ["nota_maxima", "sobre", "puntaje_maximo"],
        "letter_grade": ["calificacion_letra", "letra"],
        "term": ["periodo", "semestre", "trimestre", "bimestre"],
        "academic_year": ["ano_escolar", "ano_academico"],
    },
    "transcripts": {
        "student_external_id": ["numero_estudiante", "matricula_estudiante"],
        "academic_year": ["ano_escolar", "ano_academico"],
        "subject_code": ["codigo_materia", "codigo_asignatura"],
        "final_grade": ["nota_final", "calificacion_final", "promedio"],
        "credits_earned": ["creditos_obtenidos", "unidades_obtenidas"],
        "gpa_points": ["promedio_general", "puntos_promedio"],
    },
    "behavior": {
        "student_external_id": ["numero_estudiante", "matricula_estudiante"],
        "date": ["fecha", "fecha_incidente"],
        "category": ["categoria", "tipo_incidente", "falta"],
        "description": ["descripcion", "detalle", "observacion", "notas"],
        "consequence": ["consecuencia", "sancion", "medida"],
    },
    "health": {
        "student_external_id": ["numero_estudiante", "matricula_estudiante"],
        "blood_type": ["grupo_sanguineo", "tipo_de_sangre", "tipo_sangre"],
        "allergies": ["alergias", "alergia"],
        "medications": ["medicamentos", "medicinas"],
        "immunizations": ["vacunas", "vacunacion", "inmunizaciones"],
        "emergency_contact_name": ["contacto_emergencia", "nombre_contacto_emergencia", "persona_a_contactar"],
        "emergency_contact_phone": ["telefono_emergencia", "telefono_contacto_emergencia", "numero_emergencia"],
    },
    "finance": {
        "student_external_id": ["numero_estudiante", "matricula_estudiante"],
        "invoice_number": ["numero_factura", "numero_de_factura", "numero_recibo", "folio"],
        "fee_category": ["tipo_pago", "categoria_pago", "concepto", "rubro"],
        "amount": ["monto", "importe", "valor", "cantidad"],
        "currency": ["moneda", "divisa", "codigo_moneda"],
        "due_date": ["fecha_vencimiento", "vencimiento", "fecha_limite", "fecha_de_pago"],
        "paid_amount": ["monto_pagado", "pagado", "importe_pagado"],
        "balance": ["saldo", "saldo_pendiente", "adeudo", "pendiente"],
    },
    "payroll": {
        "staff_external_id": ["numero_empleado", "matricula_empleado"],
        "pay_period": ["periodo_pago", "periodo", "mes_pago"],
        "gross_pay": ["salario_bruto", "bruto", "sueldo_bruto"],
        "net_pay": ["salario_neto", "neto", "sueldo_neto", "neto_a_pagar"],
    },
    "communications": {
        "thread_external_id": ["numero_hilo", "id_conversacion", "id_mensaje"],
        "sender_external_id": ["id_remitente", "remitente", "numero_remitente"],
        "sent_at": ["enviado_el", "fecha_envio", "marca_de_tiempo"],
        "body": ["mensaje", "texto", "contenido", "cuerpo"],
    },
    "events": {
        "event_external_id": ["numero_evento", "id_evento"],
        "name": ["nombre", "titulo", "nombre_evento"],
        "start_at": ["fecha_inicio", "inicio", "comienza"],
        "end_at": ["fecha_fin", "fin", "termina"],
        "venue": ["lugar", "sede", "ubicacion"],
    },
    "library": {
        "item_external_id": ["numero_libro", "id_libro", "codigo_libro", "signatura"],
        "title": ["titulo", "nombre"],
        "isbn": ["isbn"],
        "barcode": ["codigo_de_barras", "codigo_barras", "etiqueta"],
        "borrower_external_id": ["numero_prestatario", "id_prestatario", "prestado_a"],
        "due_date": ["fecha_devolucion", "devolver_antes", "fecha_de_devolucion"],
    },
    "transport": {
        "route_name": ["ruta", "nombre_ruta", "itinerario"],
        "stop_name": ["parada", "punto_parada", "punto_recogida"],
        "student_external_id": ["numero_estudiante", "matricula_estudiante"],
        "bus_label": ["autobus", "vehiculo", "numero_autobus", "camion"],
    },
    "hostel": {
        "hostel_name": ["internado", "residencia", "dormitorio", "albergue"],
        "room_number": ["habitacion", "numero_habitacion", "cuarto", "cama"],
        "student_external_id": ["numero_estudiante", "matricula_estudiante"],
    },
    "cafeteria": {
        "student_external_id": ["numero_estudiante", "matricula_estudiante"],
        "meal_plan": ["plan_de_comidas", "plan_comidas", "comedor"],
        "balance": ["saldo", "credito", "saldo_comedor"],
    },
    "alumni": {
        "alumnus_external_id": ["numero_egresado", "id_egresado", "numero_exalumno"],
        "graduation_year": ["ano_graduacion", "ano_egreso", "promocion"],
        "current_employer": ["empleador", "empresa", "empleador_actual"],
        "email": ["correo", "correo_contacto", "email"],
    },
    "compliance": {
        "consent_type": ["tipo_consentimiento", "consentimiento", "autorizacion"],
        "student_external_id": ["numero_estudiante", "matricula_estudiante"],
        "granted": ["otorgado", "consentido", "autorizado", "aprobado"],
        "granted_at": ["fecha_consentimiento", "firmado_el", "fecha_firma"],
    },
}

_PORTUGUESE_SEED_2026_08: dict[str, dict[str, list[str]]] = {
    "students": {
        "external_id": ["numero_aluno", "matricula", "matricula_aluno", "codigo_aluno", "id_aluno", "ra"],
        "admission_number": ["numero_matricula", "numero_inscricao", "numero_admissao"],
        "first_name": ["nome", "primeiro_nome", "nomes"],
        "last_name": ["sobrenome", "apelido", "ultimo_nome", "nome_de_familia"],
        "middle_name": ["nome_do_meio", "segundo_nome"],
        "date_of_birth": ["data_de_nascimento", "data_nascimento", "nascimento"],
        "gender": ["sexo", "genero"],
        "grade_level": ["serie", "ano", "nivel", "grau"],
        "enrollment_status": ["situacao", "status", "estado", "ativo"],
        "email": ["email", "correio_eletronico", "e_mail"],
        "phone": ["telefone", "celular", "telemovel", "numero_telefone"],
        "address": ["endereco", "morada", "residencia"],
    },
    "guardians": {
        "guardian_external_id": ["numero_responsavel", "id_responsavel", "id_encarregado", "codigo_responsavel"],
        "student_external_id": ["numero_aluno", "matricula_aluno", "id_aluno", "id_filho"],
        "relationship": ["relacao", "parentesco", "vinculo", "grau_de_parentesco"],
        "first_name": ["nome", "nome_responsavel"],
        "last_name": ["sobrenome", "apelido", "sobrenome_responsavel"],
        "email": ["email", "email_responsavel"],
        "phone": ["telefone", "celular", "telefone_responsavel"],
        "is_primary": ["principal", "contato_principal", "responsavel_principal"],
    },
    "staff": {
        "staff_external_id": ["numero_funcionario", "matricula_funcionario", "id_funcionario", "numero_servidor", "codigo_professor", "numero_professor"],
        "first_name": ["nome"],
        "last_name": ["sobrenome", "apelido"],
        "email": ["email", "email_institucional"],
        "role": ["cargo", "funcao", "papel"],
        "department": ["departamento", "area", "setor"],
        "hire_date": ["data_admissao", "data_contratacao", "data_de_admissao", "data_inicio"],
    },
    "enrollment": {
        "student_external_id": ["numero_aluno", "matricula_aluno", "id_aluno"],
        "academic_year": ["ano_letivo", "ano_escolar", "ano_academico"],
        "grade_level": ["serie", "ano", "nivel"],
        "homeroom": ["turma", "grupo", "sala_de_aula"],
        "enrollment_date": ["data_matricula", "data_inscricao", "data_ingresso"],
        "exit_date": ["data_saida", "data_desligamento", "data_transferencia"],
    },
    "academics": {
        "subject_code": ["codigo_disciplina", "codigo_materia", "codigo_curso"],
        "subject_name": ["disciplina", "materia", "curso", "nome_disciplina"],
        "credits": ["creditos", "carga_horaria", "unidades"],
        "department": ["departamento", "area"],
    },
    "sections": {
        "section_external_id": ["numero_turma", "id_turma", "codigo_turma", "id_secao"],
        "subject_code": ["codigo_disciplina", "codigo_materia"],
        "teacher_external_id": ["numero_professor", "id_professor", "codigo_docente"],
        "academic_year": ["ano_letivo", "ano_escolar"],
        "term": ["periodo", "semestre", "trimestre", "bimestre"],
    },
    "schedule": {
        "section_external_id": ["numero_turma", "id_turma"],
        "day_of_week": ["dia", "dia_da_semana", "dia_semana"],
        "start_time": ["hora_inicio", "hora_de_inicio", "inicio"],
        "end_time": ["hora_fim", "hora_de_fim", "fim"],
        "room": ["sala", "sala_de_aula", "local"],
    },
    "attendance": {
        "student_external_id": ["numero_aluno", "matricula_aluno"],
        "date": ["data", "data_presenca", "dia"],
        "status": ["situacao", "presenca", "frequencia"],
        "period": ["periodo", "aula", "bloco"],
        "reason": ["motivo", "razao", "observacao"],
    },
    "grades": {
        "student_external_id": ["numero_aluno", "matricula_aluno"],
        "section_external_id": ["numero_turma", "id_turma", "codigo_turma"],
        "assessment_name": ["avaliacao", "prova", "exame", "tarefa", "trabalho"],
        "score": ["nota", "pontuacao", "pontos"],
        "max_score": ["nota_maxima", "valor_total", "pontuacao_maxima"],
        "letter_grade": ["conceito", "mencao"],
        "term": ["periodo", "semestre", "trimestre", "bimestre"],
        "academic_year": ["ano_letivo", "ano_escolar"],
    },
    "transcripts": {
        "student_external_id": ["numero_aluno", "matricula_aluno"],
        "academic_year": ["ano_letivo", "ano_escolar"],
        "subject_code": ["codigo_disciplina", "codigo_materia"],
        "final_grade": ["nota_final", "media", "media_final"],
        "credits_earned": ["creditos_obtidos", "carga_horaria_cumprida"],
        "gpa_points": ["media_geral", "coeficiente_rendimento"],
    },
    "behavior": {
        "student_external_id": ["numero_aluno", "matricula_aluno"],
        "date": ["data", "data_ocorrencia"],
        "category": ["categoria", "tipo_ocorrencia", "infracao"],
        "description": ["descricao", "detalhe", "observacao"],
        "consequence": ["consequencia", "penalidade", "medida"],
    },
    "health": {
        "student_external_id": ["numero_aluno", "matricula_aluno"],
        "blood_type": ["tipo_sanguineo", "grupo_sanguineo"],
        "allergies": ["alergias", "alergia"],
        "medications": ["medicamentos", "remedios"],
        "immunizations": ["vacinas", "vacinacao", "imunizacoes"],
        "emergency_contact_name": ["contato_emergencia", "nome_contato_emergencia", "pessoa_a_contatar"],
        "emergency_contact_phone": ["telefone_emergencia", "telefone_contato_emergencia", "numero_emergencia"],
    },
    "finance": {
        "student_external_id": ["numero_aluno", "matricula_aluno"],
        "invoice_number": ["numero_fatura", "numero_da_fatura", "numero_recibo", "numero_boleto"],
        "fee_category": ["tipo_pagamento", "categoria_pagamento", "rubrica"],
        "amount": ["valor", "montante", "quantia", "valor_taxa"],
        "currency": ["moeda", "codigo_moeda"],
        "due_date": ["data_vencimento", "vencimento", "data_limite", "data_de_pagamento"],
        "paid_amount": ["valor_pago", "pago", "montante_pago"],
        "balance": ["saldo", "saldo_devedor", "restante", "valor_devido"],
    },
    "payroll": {
        "staff_external_id": ["numero_funcionario", "matricula_funcionario"],
        "pay_period": ["periodo_pagamento", "periodo", "mes_pagamento"],
        "gross_pay": ["salario_bruto", "bruto", "vencimento_bruto"],
        "net_pay": ["salario_liquido", "liquido", "vencimento_liquido"],
    },
    "communications": {
        "thread_external_id": ["numero_conversa", "id_conversa", "id_mensagem"],
        "sender_external_id": ["id_remetente", "remetente", "numero_remetente"],
        "sent_at": ["enviado_em", "data_envio", "carimbo_de_tempo"],
        "body": ["mensagem", "texto", "conteudo", "corpo"],
    },
    "events": {
        "event_external_id": ["numero_evento", "id_evento"],
        "name": ["nome", "titulo", "nome_evento"],
        "start_at": ["data_inicio", "inicio", "comeca"],
        "end_at": ["data_fim", "fim", "termina"],
        "venue": ["local", "sede", "localizacao"],
    },
    "library": {
        "item_external_id": ["numero_livro", "id_livro", "codigo_livro", "tombamento"],
        "title": ["titulo", "nome"],
        "isbn": ["isbn"],
        "barcode": ["codigo_de_barras", "codigo_barras", "etiqueta"],
        "borrower_external_id": ["numero_leitor", "id_leitor", "emprestado_a"],
        "due_date": ["data_devolucao", "devolver_ate", "data_de_devolucao"],
    },
    "transport": {
        "route_name": ["rota", "nome_rota", "itinerario", "linha"],
        "stop_name": ["parada", "ponto_parada", "ponto_embarque"],
        "student_external_id": ["numero_aluno", "matricula_aluno"],
        "bus_label": ["onibus", "veiculo", "numero_onibus", "autocarro"],
    },
    "hostel": {
        "hostel_name": ["internato", "alojamento", "dormitorio", "residencia"],
        "room_number": ["quarto", "numero_quarto", "cama"],
        "student_external_id": ["numero_aluno", "matricula_aluno"],
    },
    "cafeteria": {
        "student_external_id": ["numero_aluno", "matricula_aluno"],
        "meal_plan": ["plano_de_refeicoes", "plano_refeicoes", "cantina", "refeitorio"],
        "balance": ["saldo", "credito", "saldo_cantina"],
    },
    "alumni": {
        "alumnus_external_id": ["numero_ex_aluno", "id_ex_aluno", "numero_egresso"],
        "graduation_year": ["ano_formatura", "ano_conclusao"],
        "current_employer": ["empregador", "empresa", "empregador_atual"],
        "email": ["email", "email_contato"],
    },
    "compliance": {
        "consent_type": ["tipo_consentimento", "consentimento", "autorizacao"],
        "student_external_id": ["numero_aluno", "matricula_aluno"],
        "granted": ["concedido", "consentido", "autorizado", "aprovado"],
        "granted_at": ["data_consentimento", "assinado_em", "data_assinatura"],
    },
}


def _merge_lang_seed(seed: dict, lang: str) -> None:
    """Fold a language coverage seed into BASELINE_OVERLAY under ``lang``,
    additively (never dropping an existing overlay language / entry)."""
    for domain, fields in seed.items():
        dom = BASELINE_OVERLAY.setdefault(domain, {})
        for field, syns in fields.items():
            field_langs = dom.setdefault(field, {})
            existing = list(field_langs.get(lang, []))
            field_langs[lang] = list(dict.fromkeys([*existing, *syns]))


_merge_lang_seed(_SPANISH_SEED_2026_08, "es")
_merge_lang_seed(_PORTUGUESE_SEED_2026_08, "pt")
