"""
Import CurriculumNode from CSV.
Columns: code, title, parent_code, order, level_type, standard_id (or standard_name).
Header row optional; if missing, first row is data.
"""
import csv
import io

from django.core.management.base import BaseCommand

from apps.academics.models import CurriculumStandard, CurriculumNode


class Command(BaseCommand):
    help = "Import curriculum nodes from CSV. Columns: code, title, parent_code, order, level_type, standard_id"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", help="Path to CSV")
        parser.add_argument("--standard", type=int, help="CurriculumStandard PK (if not in CSV)")
        parser.add_argument("--dry-run", action="store_true", help="Do not write to DB")

    def handle(self, *args, **options):
        path = options.get("csv_file")
        standard_id = options.get("standard")
        dry_run = options.get("dry_run", False)
        if not path:
            self.stderr.write(self.style.ERROR("Provide csv_file path"))
            return
        with open(path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            self.stderr.write(self.style.ERROR("Empty or invalid CSV"))
            return
        keys = [k.strip().lower().replace(" ", "_") for k in reader.fieldnames]
        rows = list(reader)
        if not rows:
            self.stderr.write(self.style.ERROR("No data rows"))
            return
        # Normalize row keys
        data = []
        for row in rows:
            data.append({keys[i]: row.get(f, "").strip() for i, f in enumerate(reader.fieldnames)})
        # Resolve standard
        first = data[0]
        sid = standard_id or first.get("standard_id") or first.get("standard")
        sname = first.get("standard_name") or first.get("standard")
        standard = None
        if sid:
            try:
                standard = CurriculumStandard.objects.get(pk=int(sid))
            except (ValueError, CurriculumStandard.DoesNotExist):
                pass
        if not standard and sname:
            standard = CurriculumStandard.objects.filter(name__iexact=sname).first()
        if not standard:
            self.stderr.write(self.style.ERROR("Provide --standard=<id> or include standard_id/standard_name in CSV"))
            return
        # Pass 1: create all nodes with parent=None
        created = 0
        code_to_node = {}
        for row in data:
            code = (row.get("code") or "").strip()
            if not code:
                continue
            title = (row.get("title") or "").strip() or code
            try:
                order = int(row.get("order") or 0)
            except ValueError:
                order = 0
            level_type = (row.get("level_type") or "topic").strip().lower()
            if level_type not in dict(CurriculumNode.LevelType.choices):
                level_type = "topic"
            if dry_run:
                created += 1
                continue
            node, is_new = CurriculumNode.objects.update_or_create(
                standard=standard,
                code=code,
                defaults={"title": title, "parent": None, "order": order, "level_type": level_type},
            )
            code_to_node[code] = node
            if is_new:
                created += 1
        # Pass 2: set parents
        if not dry_run:
            for row in data:
                code = (row.get("code") or "").strip()
                parent_code = (row.get("parent_code") or "").strip()
                if not code or not parent_code or parent_code not in code_to_node:
                    continue
                node = code_to_node[code]
                if node.parent_id != code_to_node[parent_code].pk:
                    node.parent = code_to_node[parent_code]
                    node.save(update_fields=["parent"])
        self.stdout.write(self.style.SUCCESS(f"Processed {len(data)} rows; new/updated: {created}"))
