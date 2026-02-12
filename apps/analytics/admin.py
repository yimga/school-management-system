from django.contrib import admin
from config.admin import admin_site

from unfold.admin import ModelAdmin

from .models import BenchmarkAggregate


@admin.register(BenchmarkAggregate, site=admin_site)
class BenchmarkAggregateAdmin(ModelAdmin):
    list_display = ("region_code", "sub_system", "subject_id", "term_id", "metric", "value", "sample_size")
    list_filter = ("region_code", "sub_system", "metric")
