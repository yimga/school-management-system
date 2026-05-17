#!/usr/bin/env python3
"""Emit marketing backlog v3 templates (one-shot dev utility)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

V3_HEAD = """{% extends "schools/marketing_page_layout.html" %}
{% load i18n static %}
{% block extrastyle %}{{ block.super }}<link rel="stylesheet" href="{% static 'marketing/css/marketing-v3-pages.css' %}">{% endblock %}
"""


def write(rel: str, content: str) -> None:
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    print("wrote", rel)


write(
    "templates/marketing/pages/type_contact.html",
    V3_HEAD
    + """{% block marketing_page_stack_class %} mkt-page-type-contact{% endblock %}
{% block marketing_page_inner %}
<article class="mkt-v3-page mkt-v3-page--contact">
  <header class="mkt-v3-page__hero mkt-edt-container rmc-reveal">
    <p class="mkt-v3-eyebrow">{% trans "Contact" %}</p>
    <h1 class="mkt-v3-section-headline">{{ page.headline }}</h1>
    <p class="mkt-v3-lead">{{ page.subheadline }}</p>
  </header>
  {% if page.segments %}
  <section class="mkt-edt-container mkt-v3-page__section rmc-reveal">
    <motion class="mkt-v3-segment-grid">
      {% for seg in page.segments %}
      <article class="mkt-v3-segment-card">
        <h2 class="h5">{{ seg.title }}</h2>
        <p>{{ seg.body }}</p>
      </article>
      {% endfor %}
    </motion>
  </section>
  {% endif %}
  <section class="mkt-edt-container rmc-reveal">
    {% include "marketing/components/_marketing_contact_form.html" %}
  </section>
</article>
{% endblock %}
""".replace("<motion", "<div").replace("</motion>", "</div>"),
)

write(
    "templates/marketing/pages/type_demo.html",
    V3_HEAD
    + """{% block marketing_page_stack_class %} mkt-page-type-demo{% endblock %}
{% block marketing_page_inner %}
<article class="mkt-v3-page mkt-v3-page--demo">
  <header class="mkt-v3-page__hero mkt-edt-container rmc-reveal">
    <p class="mkt-v3-eyebrow">{% trans "Demo" %}</p>
    <h1 class="mkt-v3-section-headline">{{ page.headline }}</h1>
    <p class="mkt-v3-lead">{{ page.subheadline }}</p>
  </header>
  {% if page.segments %}
  <section class="mkt-edt-container mkt-v3-page__section rmc-reveal">
    <div class="mkt-v3-segment-grid">
      {% for seg in page.segments %}
      <article class="mkt-v3-segment-card">
        <h2 class="h5">{{ seg.title }}</h2>
        <p>{{ seg.body }}</p>
      </article>
      {% endfor %}
    </motion>
  </section>
  {% endif %}
  <section class="mkt-edt-container rmc-reveal">
    {% include "marketing/components/_marketing_demo_form.html" %}
  </section>
</article>
{% endblock %}
""".replace("<motion", "<motion").replace("</motion>", "</motion>").replace(
        "    </motion>\n  </section>", "    </motion>\n  </section>"
    ).replace("<motion", "<div").replace("</motion>", "</motion>").replace(
        "    </motion>", "    </div>"
    ),
)

# Fix type_demo - the replace chain is messy, write clean version
write(
    "templates/marketing/pages/type_demo.html",
    V3_HEAD
    + """{% block marketing_page_stack_class %} mkt-page-type-demo{% endblock %}
{% block marketing_page_inner %}
<article class="mkt-v3-page mkt-v3-page--demo">
  <header class="mkt-v3-page__hero mkt-edt-container rmc-reveal">
    <p class="mkt-v3-eyebrow">{% trans "Demo" %}</p>
    <h1 class="mkt-v3-section-headline">{{ page.headline }}</h1>
    <p class="mkt-v3-lead">{{ page.subheadline }}</p>
  </header>
  {% if page.segments %}
  <section class="mkt-edt-container mkt-v3-page__section rmc-reveal">
    <div class="mkt-v3-segment-grid">
      {% for seg in page.segments %}
      <article class="mkt-v3-segment-card">
        <h2 class="h5">{{ seg.title }}</h2>
        <p>{{ seg.body }}</p>
      </article>
      {% endfor %}
    </div>
  </section>
  {% endif %}
  <section class="mkt-edt-container rmc-reveal">
    {% include "marketing/components/_marketing_demo_form.html" %}
  </section>
</article>
{% endblock %}
""",
)

write(
    "templates/marketing/pages/type_company.html",
    V3_HEAD
    + """{% block marketing_page_stack_class %} mkt-page-type-company{% endblock %}
{% block marketing_page_inner %}
<article class="mkt-v3-page mkt-v3-page--company">
  <header class="mkt-v3-page__hero mkt-edt-container rmc-reveal">
    <p class="mkt-v3-eyebrow">{% trans "Company" %}</p>
    <h1 class="mkt-v3-section-headline">{{ page.headline }}</h1>
    <p class="mkt-v3-lead">{{ page.subheadline }}</p>
    {% if page_extras.trust_strip %}
    <ul class="mkt-v3-trust-strip">
      {% for item in page_extras.trust_strip %}
      <li>{{ item }}</li>
      {% endfor %}
    </ul>
    {% endif %}
  </header>
  {% if page_extras.company_pillars %}
  <section class="mkt-edt-container mkt-v3-page__section rmc-reveal">
    <div class="mkt-v3-segment-grid">
      {% for pillar in page_extras.company_pillars %}
      <article class="mkt-v3-segment-card">
        <h2 class="h5">{{ pillar.title }}</h2>
        <p>{{ pillar.body }}</p>
      </article>
      {% endfor %}
    </div>
  </section>
  {% elif page.segments %}
  <section class="mkt-edt-container mkt-v3-page__section rmc-reveal">
    <motion class="mkt-v3-segment-grid">
      {% for seg in page.segments %}
      <article class="mkt-v3-segment-card">
        <h2 class="h5">{{ seg.title }}</h2>
        <p>{{ seg.body }}</p>
      </article>
      {% endfor %}
    </motion>
  </section>
  {% endif %}
  <section class="mkt-edt-container mkt-v3-page__close rmc-reveal">
    <a href="{% url 'marketing_contact' %}" class="mkt-edt-cta">{% trans "Talk to us" %}</a>
    <a href="{% url 'marketing_demo' %}" class="mkt-edt-link ms-3">{% trans "Book a demo →" %}</a>
  </section>
</article>
{% endblock %}
""".replace("<motion", "<div").replace("</motion>", "</div>"),
)

write(
    "templates/marketing/pages/type_resources_hub.html",
    V3_HEAD
    + """{% block marketing_page_stack_class %} mkt-page-type-resources{% endblock %}
{% block marketing_page_inner %}
<article class="mkt-v3-page mkt-v3-page--resources">
  <header class="mkt-v3-page__hero mkt-edt-container rmc-reveal">
    <p class="mkt-v3-eyebrow">{% trans "Resources" %}</p>
    <h1 class="mkt-v3-section-headline">{{ page.headline }}</h1>
    <p class="mkt-v3-lead">{{ page.subheadline }}</p>
  </header>
  {% if page.segments %}
  <section class="mkt-edt-container mkt-v3-page__section rmc-reveal">
    <div class="mkt-v3-segment-grid">
      {% for seg in page.segments %}
      <article class="mkt-v3-segment-card">
        <h2 class="h5">{{ seg.title }}</h2>
        <p>{{ seg.body }}</p>
      </article>
      {% endfor %}
    </div>
  </section>
  {% endif %}
  <section class="mkt-edt-container mkt-v3-page__section rmc-reveal">
    <h2 class="mkt-v3-section-headline">{% trans "Explore" %}</h2>
    <ul class="mkt-v3-link-list">
      <li><a href="{% url 'marketing_blog' %}">{% trans "Blog" %}</a></li>
      <li><a href="{% url 'marketing_guides' %}">{% trans "Guides" %}</a></li>
      <li><a href="{% url 'marketing_case_studies' %}">{% trans "Case studies" %}</a></li>
      <li><a href="{% url 'marketing_help_center' %}">{% trans "Help center" %}</a></li>
    </ul>
  </section>
</article>
{% endblock %}
""",
)

write(
    "templates/marketing/pages/type_developers.html",
    V3_HEAD
    + """{% block marketing_page_stack_class %} mkt-page-type-developers{% endblock %}
{% block marketing_page_inner %}
<article class="mkt-v3-page mkt-v3-page--developers">
  <header class="mkt-v3-page__hero mkt-edt-container rmc-reveal">
    <p class="mkt-v3-eyebrow">{% trans "Developers" %}</p>
    <h1 class="mkt-v3-section-headline">{{ page.headline }}</h1>
    <p class="mkt-v3-lead">{{ page.subheadline }}</p>
    <div class="mkt-v3-archetype__ctas">
      <a href="{% url 'marketing_developer_api' %}" class="mkt-edt-cta">{% trans "API reference" %}</a>
      <a href="{% url 'developer_hub' %}" class="mkt-edt-link">{% trans "Developer hub →" %}</a>
    </div>
  </header>
  {% if page.segments %}
  <section class="mkt-edt-container mkt-v3-page__section rmc-reveal">
    <div class="mkt-v3-segment-grid">
      {% for seg in page.segments %}
      <article class="mkt-v3-segment-card">
        <h2 class="h5">{{ seg.title }}</h2>
        <p>{{ seg.body }}</p>
      </article>
      {% endfor %}
    </div>
  </section>
  {% endif %}
</article>
{% endblock %}
""",
)

PLATFORM_ARCHETYPE = """{% extends "schools/marketing_page_layout.html" %}
{% load i18n static %}
{% block extrastyle %}{{ block.super }}<link rel="stylesheet" href="{% static 'marketing/css/marketing-v3-pages.css' %}"><link rel="stylesheet" href="{% static 'marketing/css/marketing-platform-themes.css' %}">{% endblock %}
{% block marketing_page_stack_class %} mkt-page-type-platform-detail mkt-platform-theme--{{ page.slug|default:'platform'|slugify }}{% endblock %}
{% block marketing_page_inner %}
<article class="mkt-v3-archetype">
  <header class="mkt-v3-archetype__hero mkt-edt-container rmc-reveal">
    <p class="mkt-v3-eyebrow">{{ eyebrow }}</p>
    <h1 class="mkt-v3-section-headline">{{ page.headline }}</h1>
    <p class="mkt-v3-lead">{{ page.subheadline }}</p>
    <div class="mkt-v3-archetype__ctas">
      <a href="{% url 'marketing_demo' %}" class="mkt-edt-cta" data-cta="demo">{% trans "Book a demo" %}</a>
      <a href="{% url 'marketing_platform' %}" class="mkt-edt-link">{% trans "Platform hub →" %}</a>
    </div>
  </header>
  {% if page.segments %}
  <section class="mkt-edt-container mkt-v3-archetype__wins rmc-reveal">
    <div class="mkt-v3-segment-grid">
      {% for seg in page.segments %}
      <article class="mkt-v3-segment-card">
        <h2 class="h5">{{ seg.title }}</h2>
        <p>{{ seg.body }}</p>
      </article>
      {% endfor %}
    </div>
  </section>
  {% endif %}
</article>
{% endblock %}
"""

for slug, eyebrow in (
    ("integrations", "Integrations"),
    ("runtime", "Runtime configuration"),
    ("control_plane", "Control plane"),
    ("education_os", "Education OS"),
):
    write(
        f"templates/marketing/pages/type_platform_{slug}.html",
        PLATFORM_ARCHETYPE.replace("{{ eyebrow }}", "{% trans \"" + eyebrow + "\" %}"),
    )

write(
    "templates/marketing/pages/type_solutions_persona.html",
    V3_HEAD
    + """{% block marketing_page_stack_class %} mkt-page-type-solutions-persona mkt-persona--{{ persona.slug }}{% endblock %}
{% block marketing_page_inner %}
<article class="mkt-v3-page mkt-v3-page--persona">
  <header class="mkt-v3-page__hero mkt-edt-container rmc-reveal">
    <p class="mkt-v3-eyebrow">{% trans "Solutions" %}</p>
    <h1 class="mkt-v3-section-headline">{{ persona.name }}</h1>
    <p class="mkt-v3-lead">{{ persona.lead }}</p>
    <div class="mkt-v3-archetype__ctas">
      <a href="{% url 'marketing_demo' %}" class="mkt-edt-cta" data-cta="demo">{% trans "Book a demo" %}</a>
      <a href="{% url 'marketing_solutions' %}" class="mkt-edt-link">{% trans "All solutions →" %}</a>
    </motion>
  </header>
  {% if persona.dashboard_partial %}
  {% include "marketing/components/_dashboard_frame.html" with frame_title=persona.name dashboard_partial=persona.dashboard_partial %}
  {% endif %}
  {% if persona.bullets %}
  <section class="mkt-edt-container mkt-v3-archetype__wins rmc-reveal">
    <ul>
      {% for item in persona.bullets %}
      <li>{{ item }}</li>
      {% endfor %}
    </ul>
  </section>
  {% endif %}
</article>
{% endblock %}
""".replace("<motion", "<div").replace("</motion>", "</div>"),
)

print("done")
