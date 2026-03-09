from django.contrib import admin
from config.admin import register_tenant_admin

from unfold.admin import ModelAdmin

from .models import BenchmarkAggregate


class BenchmarkAggregateAdmin(ModelAdmin):
    list_display = ("region_code", "sub_system", "subject_id", "term_id", "metric", "value", "sample_size")
    list_filter = ("region_code", "sub_system", "metric")


register_tenant_admin(BenchmarkAggregate, BenchmarkAggregateAdmin)
