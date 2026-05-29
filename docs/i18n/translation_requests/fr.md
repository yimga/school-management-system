# Native review packet: French (`fr`) — marketing chrome

**Purpose:** verify or correct AI-drafted French marketing strings before production deploy.

**Source:** English (`en`)  ·  **Locale:** `fr`  ·  **Strings:** 111 (111-string marketing set; anchors seeded via `seed_marketing_site`)

**Brand voice:** editorial / quiet-luxury — see [MARKETING_VOICE.md](../../MARKETING_VOICE.md).

**Locale notes:** French formal copy uses non-breaking space before `: ; ! ?`. School-domain terms (bursar → *intendant*, report card → *bulletin*) should match Francophone Africa + France operator expectations.

## Instructions for the native reviewer

1. Read the **AI draft** column (from `locale/fr/LC_MESSAGES/django.po` + seed script).
2. If correct, leave **Corrected** blank or copy the draft unchanged.
3. If wrong, write the corrected French in **Corrected**.
4. Sign off at the bottom.
5. Operator applies corrections to `locale/fr/LC_MESSAGES/django.po`, runs `python manage.py sync_i18n_catalog --compile`, then:

   `python manage.py i18n_review_status --mark-reviewed fr --reviewer "<your-name>"`

**Production gate:** `python scripts/verify_marketing_i18n_production_gate.py --production` blocks deploy until `fr` (and `es`, `pt-br`) are `production-ready` in `var/i18n-review-status.json`.

## String table

| # | Surface | English (source) | AI draft | Corrected (if changed) |
|---|---|---|---|---|
| 1 | `nav` | Main navigation | Navigation principale | _—_ |
| 2 | `nav` | Toggle navigation | Afficher / masquer la navigation | _—_ |
| 3 | `a11y-aria` | Header primary action: Book demo | Action principale de l’en-tête : réserver une démo | _—_ |
| 4 | `status-badge` | Platform status | Statut de la plateforme | _—_ |
| 5 | `status-badge` | All systems operational | Tous les systèmes sont opérationnels | _—_ |
| 6 | `nav-cta` | Login | Connexion | _—_ |
| 7 | `cta` | Book demo | Réserver une démo | _—_ |
| 8 | `cta` | Book a demo | Réserver une démo | _—_ |
| 9 | `cta` | Book a demo → | Réserver une démo → | _—_ |
| 10 | `nav` | Pricing | Tarifs | _—_ |
| 11 | `nav` | Why switch | Pourquoi changer | _—_ |
| 12 | `nav` | More | Plus | _—_ |
| 13 | `nav` | Choose language | Choisir la langue | _—_ |
| 14 | `verb-nav` | Run | Gérer | _—_ |
| 15 | `verb-nav` | Teach | Enseigner | _—_ |
| 16 | `verb-nav` | Pay | Payer | _—_ |
| 17 | `verb-nav` | Communicate | Communiquer | _—_ |
| 18 | `verb-nav` | Grow | Faire grandir | _—_ |
| 19 | `verb-nav` | was: Platform | auparavant : Plateforme | _—_ |
| 20 | `nav` | Solutions | Solutions | _—_ |
| 21 | `nav` | Company | Société | _—_ |
| 22 | `nav` | Demo | Démo | _—_ |
| 23 | `hero-eyebrow` | Tuesday · Cedar Ridge Academy | Mardi · Cedar Ridge Academy | _—_ |
| 24 | `hero-tagline` | One quiet system behind admissions, classrooms, fees, and the message you send a parent at 8:14 a.m. | Un seul système discret derrière les admissions, les salles de classe, les frais, et le message que vous envoyez à un parent à 8 h 14. | _—_ |
| 25 | `cta` | See it live | Voir en direct | _—_ |
| 26 | `section-heading` | Platform overview | Aperçu de la plateforme | _—_ |
| 27 | `section-heading` | Quick proof points | Preuves rapides | _—_ |
| 28 | `proof-point` | to fully switch from legacy SIS | pour migrer entièrement depuis votre ancien SIS | _—_ |
| 29 | `section-heading` | Multi-tenant, region-aware | Multi-établissement, adapté à chaque région | _—_ |
| 30 | `section-lede` | Your school's hour. Your school's currency. Your school's calendar. | L’heure de votre école. La monnaie de votre école. Le calendrier de votre école. | _—_ |
| 31 | `section-body` | Run on local time, in the right language, with the academic structure your country actually uses. No forks. No regional plug-ins. One platform that bends to each campus. | Fonctionne à l’heure locale, dans la bonne langue, avec la structure scolaire réellement utilisée dans votre pays. Aucun fork. Aucune extension régionale. Une plateforme qui s’adapte à chaque établissement. | _—_ |
| 32 | `section-heading` | Localisation surfaces | Surfaces de localisation | _—_ |
| 33 | `proof-point` | 180 currencies | 180 devises | _—_ |
| 34 | `proof-point` | 29 languages | 29 langues | _—_ |
| 35 | `proof-point` | All major SIS imports | Importation depuis tous les SIS majeurs | _—_ |
| 36 | `proof-point` | FERPA · GDPR · POPIA aligned | Aligné FERPA · RGPD · POPIA | _—_ |
| 37 | `proof-point` | Offline-first where the network drops | Mode hors-ligne d’abord, là où le réseau lâche | _—_ |
| 38 | `section-heading` | Platform scale | Échelle de la plateforme | _—_ |
| 39 | `section-heading` | Coming from somewhere else? | Vous venez d’ailleurs ? | _—_ |
| 40 | `section-body` | We've moved schools off PowerSchool, Blackbaud, Infinite Campus, and a folder full of spreadsheets. | Nous avons déjà fait migrer des écoles depuis PowerSchool, Blackbaud, Infinite Campus, et un dossier rempli de feuilles de calcul. | _—_ |
| 41 | `section-heading` | Migration timeline | Chronologie de la migration | _—_ |
| 42 | `migration-step` | Map your data | Cartographier vos données | _—_ |
| 43 | `migration-step` | Dry-run | Test à blanc | _—_ |
| 44 | `migration-step` | Cutover | Bascule | _—_ |
| 45 | `cta` | How a migration actually goes → | Comment se déroule vraiment une migration → | _—_ |
| 46 | `verb-detail` | Records, enrollment context, and learner profile continuity. | Dossiers, contexte d’inscription et continuité du profil élève. | _—_ |
| 47 | `verb-detail` | Pipeline from enquiry through enrollment with one thread. | Un fil unique de la demande initiale jusqu’à l’inscription. | _—_ |
| 48 | `verb-detail` | Daily presence and formative marks tied to the same learner record. | Présence quotidienne et notes formatives rattachées au même dossier élève. | _—_ |
| 49 | `verb-detail` | Invoices, receipts, and guardian visibility without spreadsheet drift. | Factures, reçus et visibilité côté parents, sans dérive de feuilles de calcul. | _—_ |
| 50 | `verb-detail` | Assessment, transcripts, and reporting on one academic spine. | Évaluation, bulletins et reporting sur une seule colonne vertébrale académique. | _—_ |
| 51 | `section-heading` | Three plans, total transparency. | Trois formules, transparence totale. | _—_ |
| 52 | `pricing-tier` | Starter | Démarrage | _—_ |
| 53 | `pricing-tier` | Growth | Croissance | _—_ |
| 54 | `pricing-tier` | Enterprise | Entreprise | _—_ |
| 55 | `pricing-tier` | Custom | Sur mesure | _—_ |
| 56 | `section-heading` | Add-ons | Extensions | _—_ |
| 57 | `addon-name` | Migration Cloud | Migration Cloud | _—_ |
| 58 | `addon-body` | Phased cutover, dry-run sandbox, dedicated migration lead. | Bascule par phases, environnement de test à blanc, chef de migration dédié. | _—_ |
| 59 | `addon-name` | Marketplace apps | Applications du marketplace | _—_ |
| 60 | `addon-body` | Governed partner tiles — activate per campus. | Tuiles partenaires gouvernées — activables par établissement. | _—_ |
| 61 | `addon-name` | Premium support | Support premium | _—_ |
| 62 | `addon-body` | Enterprise SLA, operator command center access. | SLA entreprise, accès au centre de commande opérateur. | _—_ |
| 63 | `section-heading` | FAQ | FAQ | _—_ |
| 64 | `section-heading` | Common questions | Questions fréquentes | _—_ |
| 65 | `section-heading` | Trust center | Centre de confiance | _—_ |
| 66 | `section-body` | Posture, certifications, and incident transparency. | Posture, certifications et transparence sur les incidents. | _—_ |
| 67 | `cta` | Request security packet | Demander le dossier sécurité | _—_ |
| 68 | `section-heading` | Implementation assurance | Assurance de mise en œuvre | _—_ |
| 69 | `cta` | Contact sales → | Contacter les ventes → | _—_ |
| 70 | `section-body` | We document posture honestly — certifications and live PSP rails only when externally verified. | Nous documentons notre posture honnêtement — certifications et flux PSP en production uniquement après vérification externe. | _—_ |
| 71 | `section-heading` | Incident response | Réponse aux incidents | _—_ |
| 72 | `form-field` | Your name | Votre nom | _—_ |
| 73 | `form-field` | Work email | E-mail professionnel | _—_ |
| 74 | `form-field` | School name | Nom de l’école | _—_ |
| 75 | `form-field` | Phone | Téléphone | _—_ |
| 76 | `form-field` | Country | Pays | _—_ |
| 77 | `form-field` | School type | Type d’école | _—_ |
| 78 | `form-field` | Number of students | Nombre d’élèves | _—_ |
| 79 | `form-field` | Message | Message | _—_ |
| 80 | `cta` | Send | Envoyer | _—_ |
| 81 | `cta-supporting` | Get a 20-minute walkthrough. | Obtenez une visite guidée de 20 minutes. | _—_ |
| 82 | `section-heading` | Your Tuesday. | Votre mardi. | _—_ |
| 83 | `cta` | Read the full Tuesday for the head → | Lire le mardi complet du chef d’établissement → | _—_ |
| 84 | `section-heading` | Five roles. Five Tuesdays. | Cinq rôles. Cinq mardis. | _—_ |
| 85 | `section-heading` | What changes for everyone in the building | Ce qui change pour chacun dans l’établissement | _—_ |
| 86 | `persona` | Head of school | Chef d’établissement | _—_ |
| 87 | `persona` | Bursar | Économe | _—_ |
| 88 | `persona` | Teacher | Enseignant | _—_ |
| 89 | `persona` | Parent | Parent | _—_ |
| 90 | `persona` | IT lead | Responsable informatique | _—_ |
| 91 | `cta` | Talk to us | Parler avec nous | _—_ |
| 92 | `cta` | All solutions → | Toutes les solutions → | _—_ |
| 93 | `cta` | Talk to a human → | Parler à un humain → | _—_ |
| 94 | `tagline` | Less software. More school. | Moins de logiciels. Plus d’école. | _—_ |
| 95 | `alt-text` | A campus advisor — editorial illustration. | Un conseiller de campus — illustration éditoriale. | _—_ |
| 96 | `footer` | Product | Produit | _—_ |
| 97 | `footer` | Why switch? | Pourquoi changer ? | _—_ |
| 98 | `footer` | Resources | Ressources | _—_ |
| 99 | `footer` | Help center | Centre d’aide | _—_ |
| 100 | `footer` | Release notes | Notes de version | _—_ |
| 101 | `footer` | Developers | Développeurs | _—_ |
| 102 | `footer` | Status | Statut | _—_ |
| 103 | `footer` | Privacy | Confidentialité | _—_ |
| 104 | `footer` | Terms | Conditions | _—_ |
| 105 | `footer` | Contact | Contact | _—_ |
| 106 | `email-signature` | Between the bells · Sent by RunMyCampus | Entre deux sonneries · Envoyé par RunMyCampus | _—_ |
| 107 | `404` | Page not found | Page introuvable | _—_ |
| 108 | `404` | That page isn't here. | Cette page n’est pas ici. | _—_ |
| 109 | `404` | The link may be old, scoped to a different host, or missing required context. Try one of the stable entry points below. | Le lien est peut-être obsolète, lié à un autre hôte, ou il manque un contexte requis. Essayez l’un des points d’entrée stables ci-dessous. | _—_ |
| 110 | `404` | Go to homepage | Aller à la page d’accueil | _—_ |
| 111 | `404` | Contact support | Contacter le support | _—_ |

## Sign-off

- **Reviewer name:** _—_
- **Date completed:** _—_
- **Native-speaker affirmation (Y/N):** _—_
- **Notes** (terms left in English, register choices): _—_

---

Regenerate this packet after `seed_french_marketing_translations.py` changes: `python scripts/generate_french_marketing_review_packet.py`
