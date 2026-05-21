#!/usr/bin/env python
"""One-shot script: seed French (`fr`) marketing translations.

12-pillar P11 polish (v3.23.9 2026-05-17). The 111-string set is the
same one es/pt-br already cover (top marketing chrome — nav / CTAs /
hero / pricing / footer / 404). These are AI-drafted by an LLM that
*does* read French at a working level; they still need a native-speaker
review pass before production deploy (operator workflow tracked in
``var/i18n-review-status.json``).

Idempotent: re-running it overwrites the French msgstr for these 111
exact msgids but does not touch any other entry.

Usage:
    python scripts/seed_french_marketing_translations.py
    python scripts/seed_french_marketing_translations.py --dry-run
"""
from __future__ import annotations

import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FR_PO = REPO_ROOT / "locale" / "fr" / "LC_MESSAGES" / "django.po"


# 111 high-leverage marketing strings → French.
# Style: editorial / "luxury school management" tone matching MARKETING_VOICE.md.
# Punctuation: French uses non-breaking space before : ; ! ? in formal copy.
TRANSLATIONS: dict[str, str] = {
    "Main navigation": "Navigation principale",
    "Toggle navigation": "Afficher / masquer la navigation",
    "Header primary action: Book demo": "Action principale de l’en-tête : réserver une démo",
    "Platform status": "Statut de la plateforme",
    "All systems operational": "Tous les systèmes sont opérationnels",
    "Login": "Connexion",
    "Book demo": "Réserver une démo",
    "Book a demo": "Réserver une démo",
    "Book a demo →": "Réserver une démo →",
    "Pricing": "Tarifs",
    "Why switch": "Pourquoi changer",
    "More": "Plus",
    "Choose language": "Choisir la langue",
    "Run": "Gérer",
    "Teach": "Enseigner",
    "Pay": "Payer",
    "Communicate": "Communiquer",
    "Grow": "Faire grandir",
    "was: Platform": "auparavant : Plateforme",
    "Solutions": "Solutions",
    "Company": "Société",
    "Demo": "Démo",
    "Tuesday · Cedar Ridge Academy": "Mardi · Cedar Ridge Academy",
    "One quiet system behind admissions, classrooms, fees, and the message you send a parent at 8:14 a.m.": "Un seul système discret derrière les admissions, les salles de classe, les frais, et le message que vous envoyez à un parent à 8 h 14.",
    "See it live": "Voir en direct",
    "Platform overview": "Aperçu de la plateforme",
    "Quick proof points": "Preuves rapides",
    "to fully switch from legacy SIS": "pour migrer entièrement depuis votre ancien SIS",
    "Multi-tenant, region-aware": "Multi-établissement, adapté à chaque région",
    "Your school's hour. Your school's currency. Your school's calendar.": "L’heure de votre école. La monnaie de votre école. Le calendrier de votre école.",
    "Run on local time, in the right language, with the academic structure your country actually uses. No forks. No regional plug-ins. One platform that bends to each campus.": "Fonctionne à l’heure locale, dans la bonne langue, avec la structure scolaire réellement utilisée dans votre pays. Aucun fork. Aucune extension régionale. Une plateforme qui s’adapte à chaque établissement.",
    "Localisation surfaces": "Surfaces de localisation",
    "180 currencies": "180 devises",
    "29 languages": "29 langues",
    "All major SIS imports": "Importation depuis tous les SIS majeurs",
    "FERPA · GDPR · POPIA aligned": "Aligné FERPA · RGPD · POPIA",
    "Offline-first where the network drops": "Mode hors-ligne d’abord, là où le réseau lâche",
    "Platform scale": "Échelle de la plateforme",
    "Coming from somewhere else?": "Vous venez d’ailleurs ?",
    "We've moved schools off PowerSchool, Blackbaud, Infinite Campus, and a folder full of spreadsheets.": "Nous avons déjà fait migrer des écoles depuis PowerSchool, Blackbaud, Infinite Campus, et un dossier rempli de feuilles de calcul.",
    "Migration timeline": "Chronologie de la migration",
    "Map your data": "Cartographier vos données",
    "Dry-run": "Test à blanc",
    "Cutover": "Bascule",
    "How a migration actually goes →": "Comment se déroule vraiment une migration →",
    "Records, enrollment context, and learner profile continuity.": "Dossiers, contexte d’inscription et continuité du profil élève.",
    "Pipeline from enquiry through enrollment with one thread.": "Un fil unique de la demande initiale jusqu’à l’inscription.",
    "Daily presence and formative marks tied to the same learner record.": "Présence quotidienne et notes formatives rattachées au même dossier élève.",
    "Invoices, receipts, and guardian visibility without spreadsheet drift.": "Factures, reçus et visibilité côté parents, sans dérive de feuilles de calcul.",
    "Assessment, transcripts, and reporting on one academic spine.": "Évaluation, bulletins et reporting sur une seule colonne vertébrale académique.",
    "Three plans, total transparency.": "Trois formules, transparence totale.",
    "Starter": "Démarrage",
    "Growth": "Croissance",
    "Enterprise": "Entreprise",
    "Custom": "Sur mesure",
    "Add-ons": "Extensions",
    "Migration Cloud": "Migration Cloud",
    "Phased cutover, dry-run sandbox, dedicated migration lead.": "Bascule par phases, environnement de test à blanc, chef de migration dédié.",
    "Marketplace apps": "Applications du marketplace",
    "Governed partner tiles — activate per campus.": "Tuiles partenaires gouvernées — activables par établissement.",
    "Premium support": "Support premium",
    "Enterprise SLA, operator command center access.": "SLA entreprise, accès au centre de commande opérateur.",
    "FAQ": "FAQ",
    "Common questions": "Questions fréquentes",
    "Trust center": "Centre de confiance",
    "Posture, certifications, and incident transparency.": "Posture, certifications et transparence sur les incidents.",
    "Request security packet": "Demander le dossier sécurité",
    "Implementation assurance": "Assurance de mise en œuvre",
    "Contact sales →": "Contacter les ventes →",
    "We document posture honestly — certifications and live PSP rails only when externally verified.": "Nous documentons notre posture honnêtement — certifications et flux PSP en production uniquement après vérification externe.",
    "Incident response": "Réponse aux incidents",
    "Your name": "Votre nom",
    "Work email": "E-mail professionnel",
    "School name": "Nom de l’école",
    "Phone": "Téléphone",
    "Country": "Pays",
    "School type": "Type d’école",
    "Number of students": "Nombre d’élèves",
    "Message": "Message",
    "Send": "Envoyer",
    "Get a 20-minute walkthrough.": "Obtenez une visite guidée de 20 minutes.",
    "Your Tuesday.": "Votre mardi.",
    "Read the full Tuesday for the head →": "Lire le mardi complet du chef d’établissement →",
    "Five roles. Five Tuesdays.": "Cinq rôles. Cinq mardis.",
    "What changes for everyone in the building": "Ce qui change pour chacun dans l’établissement",
    "Head of school": "Chef d’établissement",
    "Bursar": "Économe",
    "Teacher": "Enseignant",
    "Parent": "Parent",
    "IT lead": "Responsable informatique",
    "Talk to us": "Parler avec nous",
    "All solutions →": "Toutes les solutions →",
    "Talk to a human →": "Parler à un humain →",
    "Less software. More school.": "Moins de logiciels. Plus d’école.",
    "A campus advisor — editorial illustration.": "Un conseiller de campus — illustration éditoriale.",
    "Product": "Produit",
    "Why switch?": "Pourquoi changer ?",
    "Resources": "Ressources",
    "Help center": "Centre d’aide",
    "Release notes": "Notes de version",
    "Developers": "Développeurs",
    "Status": "Statut",
    "Privacy": "Confidentialité",
    "Terms": "Conditions",
    "Contact": "Contact",
    "Between the bells · Sent by RunMyCampus": "Entre deux sonneries · Envoyé par RunMyCampus",
    "Page not found": "Page introuvable",
    "That page isn't here.": "Cette page n’est pas ici.",
    "The link may be old, scoped to a different host, or missing required context. Try one of the stable entry points below.": "Le lien est peut-être obsolète, lié à un autre hôte, ou il manque un contexte requis. Essayez l’un des points d’entrée stables ci-dessous.",
    "Go to homepage": "Aller à la page d’accueil",
    "Contact support": "Contacter le support",
}


def _escape_po(s: str) -> str:
    """Escape a Python string for inclusion in a .po quoted-msgstr field."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _parse_po_blocks(text: str) -> list[dict]:
    """Parse a .po file into a list of {header_lines, msgid, msgstr_start, msgstr_end} blocks.

    Tracks raw msgstr line range so we can rewrite it in place.
    """
    # Light-weight, sufficient for our use: we only need msgid + msgstr ranges.
    lines = text.splitlines(keepends=True)
    blocks: list[dict] = []
    cur_msgid = None
    cur_msgstr_start = None
    cur_msgstr_end = None
    i = 0
    while i < len(lines):
        s = lines[i]
        if s.startswith("msgid "):
            cur_msgid = s[len("msgid "):].strip().strip('"')
            j = i + 1
            while j < len(lines) and lines[j].startswith('"'):
                cur_msgid += lines[j].strip().strip('"')
                j += 1
            i = j
            continue
        if s.startswith("msgstr ") and cur_msgid is not None:
            cur_msgstr_start = i
            j = i + 1
            while j < len(lines) and lines[j].startswith('"'):
                j += 1
            cur_msgstr_end = j
            blocks.append(
                {
                    "msgid": cur_msgid,
                    "msgstr_start": cur_msgstr_start,
                    "msgstr_end": cur_msgstr_end,
                }
            )
            cur_msgid = None
            i = j
            continue
        i += 1
    return blocks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not FR_PO.exists():
        print(f"locale not found: {FR_PO}")
        return 1

    text = FR_PO.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    blocks = _parse_po_blocks(text)
    by_msgid = {b["msgid"]: b for b in blocks}

    updated = 0
    missing_msgids: list[str] = []
    for msgid, msgstr in TRANSLATIONS.items():
        block = by_msgid.get(msgid)
        if block is None:
            missing_msgids.append(msgid)
            continue
        # Replace block range with a single-line msgstr.
        new_line = f'msgstr "{_escape_po(msgstr)}"\n'
        start = block["msgstr_start"]
        end = block["msgstr_end"]
        # Only overwrite if the current msgstr is empty (don't trample a prior
        # operator-corrected translation).
        existing = "".join(lines[start:end])
        existing_value = existing.split("msgstr", 1)[1].strip().strip('"')
        # Multi-line case: extract all quoted continuation strings.
        cont = ""
        for cl in lines[start + 1 : end]:
            cont += cl.strip().strip('"')
        if existing_value or cont:
            # Already translated — skip to preserve prior work.
            continue
        lines[start:end] = [new_line]
        # Recompute block indices for subsequent edits.
        # Simple approach: re-parse after each write. Cheap enough for 111 entries.
        new_text = "".join(lines)
        blocks = _parse_po_blocks(new_text)
        by_msgid = {b["msgid"]: b for b in blocks}
        lines = new_text.splitlines(keepends=True)
        updated += 1

    if missing_msgids:
        print(f"  skipped {len(missing_msgids)} msgids absent from current locale catalog:")
        for mid in missing_msgids[:5]:
            print(f"    {mid[:80]}")
        if len(missing_msgids) > 5:
            print(f"    ... and {len(missing_msgids) - 5} more")

    if args.dry_run:
        print(f"  would rewrite {updated} French msgstr entries (dry-run)")
        return 0

    FR_PO.write_text("".join(lines), encoding="utf-8")
    print(f"  wrote {updated} French msgstr entries to {FR_PO.relative_to(REPO_ROOT)}")
    print("  next: python manage.py sync_i18n_catalog --compile  (regenerate .mo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
