"""
Management command to seed admin dashboard color palettes.
Creates preset ThemePacks with admin_dashboard palette from Unfold design system.
Run: python manage.py seed_admin_dashboard_palettes [--reset]
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.siteconfig.models import ThemePack, SiteSettings


def build_admin_dashboard_palette(
    primary,
    accent,
    accent_light,
    dashboard_bg,
    surface,
    border,
    border_strong,
    text,
    muted,
    subtle,
    role_admin,
    role_student,
    role_teacher,
    success="#10b981",
    warning="#f59e0b",
    danger="#ef4444",
    info="#3b82f6",
    shadow="0 1px 2px rgba(15,23,42,0.05)",
    shadow_hover="0 4px 12px rgba(15,23,42,0.1)",
    border_hover=None,
    weather_bg=None,
):
    border_hover = border_hover or border_strong
    if weather_bg is None and primary.startswith("#") and len(primary) >= 7:
        try:
            r = int(primary[1:3], 16)
            g = int(primary[3:5], 16)
            b = int(primary[5:7], 16)
            weather_bg = f"rgba({r},{g},{b},0.08)"
        except (ValueError, IndexError):
            weather_bg = "rgba(255,106,136,0.08)"
    if weather_bg is None:
        weather_bg = "rgba(255,106,136,0.08)"
    return {
        "admin_dashboard": {
            "primary": primary,
            "accent": accent,
            "accent_light": accent_light,
            "dashboard_bg": dashboard_bg,
            "surface": surface,
            "border": border,
            "border_strong": border_strong,
            "text": text,
            "muted": muted,
            "subtle": subtle,
            "role_admin": role_admin,
            "role_student": role_student,
            "role_teacher": role_teacher,
            "success": success,
            "warning": warning,
            "danger": danger,
            "info": info,
            "shadow": shadow,
            "shadow_hover": shadow_hover,
            "border_hover": border_hover or border_strong,
            "weather_bg": weather_bg,
        }
    }


class Command(BaseCommand):
    help = "Seed preset admin dashboard color palettes (Unfold design system)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing admin dashboard palettes before creating",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options.get("reset", False)

        self.stdout.write(self.style.SUCCESS("Creating admin dashboard color palettes...\n"))

        # School-focused palettes: professional, readable, all theme modes supported
        palettes = [
            # 1. Academic Slate (Default) - neutral, professional, K-12
            {
                "slug": "admin-academic-slate",
                "name": "Academic Slate (Default)",
                "description": "Neutral slate grey. Professional, low-distraction, ideal for schools.",
                "applies_to_admin": True,
                "is_default": True,
                "is_active": True,
                "primary_color": "#475569",
                "accent_color": "#0ea5e9",
                "palette": build_admin_dashboard_palette(
                    primary="#475569",
                    accent="#0ea5e9",
                    accent_light="#38bdf8",
                    dashboard_bg="#f8fafc",
                    surface="#ffffff",
                    border="rgba(15,23,42,0.08)",
                    border_strong="rgba(15,23,42,0.12)",
                    text="#0f172a",
                    muted="#64748b",
                    subtle="#475569",
                    role_admin="#6366f1",
                    role_student="#0ea5e9",
                    role_teacher="#10b981",
                    weather_bg="rgba(14,165,233,0.08)",
                ),
            },
            # 2. Campus Blue - trust, calm, institutional
            {
                "slug": "admin-campus-blue",
                "name": "Campus Blue",
                "description": "Trust and calm. Institutional blue, ideal for academies.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#2563eb",
                "accent_color": "#38bdf8",
                "palette": build_admin_dashboard_palette(
                    primary="#2563eb",
                    accent="#38bdf8",
                    accent_light="#7dd3fc",
                    dashboard_bg="#eff6ff",
                    surface="#ffffff",
                    border="rgba(37,99,235,0.12)",
                    border_strong="rgba(37,99,235,0.2)",
                    text="#0f172a",
                    muted="#64748b",
                    subtle="#475569",
                    role_admin="#6366f1",
                    role_student="#2563eb",
                    role_teacher="#10b981",
                    weather_bg="rgba(37,99,235,0.08)",
                ),
            },
            # 3. Forest Academy - nature, growth, learning
            {
                "slug": "admin-forest-academy",
                "name": "Forest Academy",
                "description": "Natural green. Calming, growth-oriented, ideal for learning.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#059669",
                "accent_color": "#34d399",
                "palette": build_admin_dashboard_palette(
                    primary="#059669",
                    accent="#34d399",
                    accent_light="#6ee7b7",
                    dashboard_bg="#f0fdf4",
                    surface="#ffffff",
                    border="rgba(5,150,105,0.15)",
                    border_strong="rgba(5,150,105,0.25)",
                    text="#0f172a",
                    muted="#64748b",
                    subtle="#475569",
                    role_admin="#059669",
                    role_student="#0ea5e9",
                    role_teacher="#34d399",
                    weather_bg="rgba(5,150,105,0.08)",
                ),
            },
            # 4. Gilead Warm Pink - brand accent
            {
                "slug": "admin-gilead-warm-pink",
                "name": "Gilead Warm Pink",
                "description": "Warm pink with purple. Friendly, creative, brand accent.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#ff6a88",
                "accent_color": "#9b6bff",
                "palette": build_admin_dashboard_palette(
                    primary="#ff6a88",
                    accent="#9b6bff",
                    accent_light="#c4a5ff",
                    dashboard_bg="#f8fafc",
                    surface="#ffffff",
                    border="rgba(15,23,42,0.08)",
                    border_strong="rgba(15,23,42,0.12)",
                    text="#0f172a",
                    muted="#6b7280",
                    subtle="#22314e",
                    role_admin="#9b6bff",
                    role_student="#ff6a88",
                    role_teacher="#2dd4bf",
                    weather_bg="rgba(255,106,136,0.08)",
                ),
            },
            # 5. Gilead Dark Pink - Unfold dark primary
            {
                "slug": "admin-midnight-scholar",
                "name": "Midnight Scholar",
                "description": "Dark, focused. Ideal for data-heavy and analytics views.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#3b82f6",
                "accent_color": "#818cf8",
                "palette": build_admin_dashboard_palette(
                    primary="#3b82f6",
                    accent="#818cf8",
                    accent_light="#a5b4fc",
                    dashboard_bg="#0f172a",
                    surface="#1e293b",
                    border="rgba(148,163,184,0.25)",
                    border_strong="rgba(148,163,184,0.35)",
                    text="#f1f5f9",
                    muted="#94a3b8",
                    subtle="#cbd5e1",
                    role_admin="#818cf8",
                    role_student="#60a5fa",
                    role_teacher="#34d399",
                    shadow="0 1px 2px rgba(0,0,0,0.3)",
                    shadow_hover="0 6px 16px rgba(0,0,0,0.4)",
                    weather_bg="rgba(59,130,246,0.15)",
                ),
            },
            # 6. Indigo Lecture - modern, tech-forward
            {
                "slug": "admin-indigo-lecture",
                "name": "Indigo Lecture",
                "description": "Modern indigo/purple. Tech-forward, ideal for STEM.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#4f46e5",
                "accent_color": "#818cf8",
                "palette": build_admin_dashboard_palette(
                    primary="#4f46e5",
                    accent="#818cf8",
                    accent_light="#a5b4fc",
                    dashboard_bg="#0f172a",
                    surface="#1e293b",
                    border="rgba(148,163,184,0.25)",
                    border_strong="rgba(148,163,184,0.35)",
                    text="#f1f5f9",
                    muted="#94a3b8",
                    subtle="#cbd5e1",
                    role_admin="#818cf8",
                    role_student="#60a5fa",
                    role_teacher="#34d399",
                    shadow="0 1px 2px rgba(0,0,0,0.3)",
                    shadow_hover="0 6px 16px rgba(0,0,0,0.4)",
                    weather_bg="rgba(79,70,229,0.15)",
                ),
            },
            # 7. Sunset Study - warm dark, energetic
            {
                "slug": "admin-sunset-study",
                "name": "Sunset Study",
                "description": "Warm orange/amber dark. Energetic, creative, low glare.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#f59e0b",
                "accent_color": "#fbbf24",
                "palette": build_admin_dashboard_palette(
                    primary="#f59e0b",
                    accent="#fbbf24",
                    accent_light="#fde68a",
                    dashboard_bg="#1c1917",
                    surface="#292524",
                    border="rgba(251,191,36,0.2)",
                    border_strong="rgba(251,191,36,0.35)",
                    text="#fef3c7",
                    muted="#d6d3d1",
                    subtle="#e7e5e4",
                    role_admin="#fbbf24",
                    role_student="#f59e0b",
                    role_teacher="#34d399",
                    shadow="0 1px 2px rgba(0,0,0,0.3)",
                    shadow_hover="0 6px 16px rgba(0,0,0,0.4)",
                    weather_bg="rgba(245,158,11,0.15)",
                ),
            },
            # 8. Gilead Dark Neutral - neutral dark
            {
                "slug": "admin-gilead-dark-neutral",
                "name": "Gilead Dark Neutral",
                "description": "Unfold dark grays: neutral dark admin.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#94a3b8",
                "accent_color": "#cbd5e1",
                "palette": build_admin_dashboard_palette(
                    primary="#94a3b8",
                    accent="#cbd5e1",
                    accent_light="#e2e8f0",
                    dashboard_bg="#0f172a",
                    surface="#1e293b",
                    border="rgba(148,163,184,0.25)",
                    border_strong="rgba(148,163,184,0.35)",
                    text="#f1f5f9",
                    muted="#94a3b8",
                    subtle="#cbd5e1",
                    role_admin="#818cf8",
                    role_student="#60a5fa",
                    role_teacher="#34d399",
                    shadow="0 1px 2px rgba(0,0,0,0.3)",
                    shadow_hover="0 6px 16px rgba(0,0,0,0.4)",
                    weather_bg="rgba(148,163,184,0.12)",
                ),
            },
            # 9. Sky Blue (Professional)
            {
                "slug": "admin-sky-blue",
                "name": "Sky Blue",
                "description": "Professional sky blue; clean and modern.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#0ea5e9",
                "accent_color": "#38bdf8",
                "palette": build_admin_dashboard_palette(
                    primary="#0ea5e9",
                    accent="#38bdf8",
                    accent_light="#7dd3fc",
                    dashboard_bg="#f8fafc",
                    surface="#ffffff",
                    border="#e2e8f0",
                    border_strong="#cbd5e1",
                    text="#0f172a",
                    muted="#64748b",
                    subtle="#475569",
                    role_admin="#6366f1",
                    role_student="#0ea5e9",
                    role_teacher="#10b981",
                    weather_bg="rgba(14,165,233,0.08)",
                ),
            },
            # 10. Forest Green
            {
                "slug": "admin-forest-green",
                "name": "Forest Green",
                "description": "Natural green; calming and professional.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#10b981",
                "accent_color": "#34d399",
                "palette": build_admin_dashboard_palette(
                    primary="#10b981",
                    accent="#34d399",
                    accent_light="#6ee7b7",
                    dashboard_bg="#f0fdf4",
                    surface="#ffffff",
                    border="#d1fae5",
                    border_strong="#a7f3d0",
                    text="#0f172a",
                    muted="#64748b",
                    subtle="#475569",
                    role_admin="#059669",
                    role_student="#10b981",
                    role_teacher="#34d399",
                    weather_bg="rgba(16,185,129,0.08)",
                ),
            },
            # 11. Sunset Warm
            {
                "slug": "admin-sunset-warm",
                "name": "Sunset Warm",
                "description": "Warm orange/amber; friendly and energetic.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#f59e0b",
                "accent_color": "#fbbf24",
                "palette": build_admin_dashboard_palette(
                    primary="#f59e0b",
                    accent="#fbbf24",
                    accent_light="#fde68a",
                    dashboard_bg="#fffbeb",
                    surface="#ffffff",
                    border="#fde68a",
                    border_strong="#fcd34d",
                    text="#0f172a",
                    muted="#64748b",
                    subtle="#475569",
                    role_admin="#d97706",
                    role_student="#f59e0b",
                    role_teacher="#10b981",
                    weather_bg="rgba(245,158,11,0.08)",
                ),
            },
            # 12. Ocean Blue
            {
                "slug": "admin-ocean-blue",
                "name": "Ocean Blue",
                "description": "Deep blue; trustworthy and corporate.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#3b82f6",
                "accent_color": "#60a5fa",
                "palette": build_admin_dashboard_palette(
                    primary="#3b82f6",
                    accent="#60a5fa",
                    accent_light="#93c5fd",
                    dashboard_bg="#eff6ff",
                    surface="#ffffff",
                    border="#bfdbfe",
                    border_strong="#93c5fd",
                    text="#0f172a",
                    muted="#64748b",
                    subtle="#475569",
                    role_admin="#6366f1",
                    role_student="#3b82f6",
                    role_teacher="#10b981",
                    weather_bg="rgba(59,130,246,0.08)",
                ),
            },
            # 13. High Contrast Light (WCAG AAA)
            {
                "slug": "admin-high-contrast-light",
                "name": "High Contrast Light",
                "description": "Maximum accessibility; light background, strong contrast.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#000000",
                "accent_color": "#0066cc",
                "palette": build_admin_dashboard_palette(
                    primary="#000000",
                    accent="#0066cc",
                    accent_light="#3385ff",
                    dashboard_bg="#ffffff",
                    surface="#ffffff",
                    border="#000000",
                    border_strong="#000000",
                    text="#000000",
                    muted="#333333",
                    subtle="#666666",
                    role_admin="#000080",
                    role_student="#0066cc",
                    role_teacher="#008000",
                    shadow="0 2px 4px rgba(0,0,0,0.2)",
                    shadow_hover="0 4px 8px rgba(0,0,0,0.3)",
                    weather_bg="rgba(0,102,204,0.1)",
                ),
            },
            # 14. High Contrast Dark
            {
                "slug": "admin-high-contrast-dark",
                "name": "High Contrast Dark",
                "description": "Maximum accessibility; dark background, strong contrast.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#60a5fa",
                "accent_color": "#93c5fd",
                "palette": build_admin_dashboard_palette(
                    primary="#60a5fa",
                    accent="#93c5fd",
                    accent_light="#bfdbfe",
                    dashboard_bg="#0c0c0c",
                    surface="#171717",
                    border="#404040",
                    border_strong="#525252",
                    text="#fafafa",
                    muted="#a3a3a3",
                    subtle="#d4d4d4",
                    role_admin="#818cf8",
                    role_student="#60a5fa",
                    role_teacher="#34d399",
                    shadow="0 2px 4px rgba(0,0,0,0.5)",
                    shadow_hover="0 6px 12px rgba(0,0,0,0.6)",
                    weather_bg="rgba(96,165,250,0.2)",
                ),
            },
            # 15. Slate Gray
            {
                "slug": "admin-slate-gray",
                "name": "Slate Gray",
                "description": "Muted slate; minimal and focused.",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#475569",
                "accent_color": "#64748b",
                "palette": build_admin_dashboard_palette(
                    primary="#475569",
                    accent="#64748b",
                    accent_light="#94a3b8",
                    dashboard_bg="#f1f5f9",
                    surface="#ffffff",
                    border="#e2e8f0",
                    border_strong="#cbd5e1",
                    text="#0f172a",
                    muted="#64748b",
                    subtle="#475569",
                    role_admin="#4f46e5",
                    role_student="#0369a1",
                    role_teacher="#047857",
                    weather_bg="rgba(71,85,105,0.08)",
                ),
            },
            # 16. Deep Space / Midnight Blue
            {
                "slug": "admin-deep-space-midnight",
                "name": "Deep Space / Midnight Blue",
                "description": "Midnight base (#101010–#222222), Neon Blue/Teal (#3B86D1) for data, soft white text (#F8F9FA).",
                "applies_to_admin": True,
                "is_default": False,
                "is_active": True,
                "primary_color": "#3B86D1",
                "accent_color": "#5ba3e8",
                "palette": build_admin_dashboard_palette(
                    primary="#3B86D1",
                    accent="#5ba3e8",
                    accent_light="#7eb8ed",
                    dashboard_bg="#101010",
                    surface="#222222",
                    border="rgba(248,249,250,0.12)",
                    border_strong="rgba(248,249,250,0.2)",
                    text="#F8F9FA",
                    muted="#b8bcc4",
                    subtle="#e2e4e8",
                    role_admin="#5ba3e8",
                    role_student="#3B86D1",
                    role_teacher="#34d399",
                    shadow="0 1px 2px rgba(0,0,0,0.4)",
                    shadow_hover="0 6px 16px rgba(0,0,0,0.5)",
                    border_hover="rgba(248,249,250,0.25)",
                    weather_bg="rgba(59,134,209,0.15)",
                ),
            },
        ]

        slugs = [p["slug"] for p in palettes]
        if reset:
            self.stdout.write("Deleting existing admin dashboard palettes...")
            ThemePack.objects.filter(slug__in=slugs).delete()
            self.stdout.write(self.style.SUCCESS("  Deleted.\n"))

        created_count = 0
        updated_count = 0
        for definition in palettes:
            slug = definition.pop("slug")
            palette_json = definition.pop("palette")
            pack, created = ThemePack.objects.update_or_create(
                slug=slug,
                defaults={**definition, "palette": palette_json},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  + Created: {pack.name}"))
            else:
                updated_count += 1
                self.stdout.write(self.style.WARNING(f"  ~ Updated: {pack.name}"))

        site_settings = SiteSettings.get_solo()
        if not site_settings.admin_theme_pack:
            default_pack = ThemePack.objects.filter(slug="admin-academic-slate").first()
            if default_pack:
                site_settings.admin_theme_pack = default_pack
                site_settings.save(update_fields=["admin_theme_pack"])
                self.stdout.write(self.style.SUCCESS(f"\n  + Set default admin theme: {default_pack.name}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone: {created_count + updated_count} palettes ({created_count} created, {updated_count} updated)"
            )
        )
