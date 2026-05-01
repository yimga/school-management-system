from config.admin import register_tenant_admin

from unfold.admin import ModelAdmin

from .models import BenchmarkAggregate, GovernedSavedReport


class BenchmarkAggregateAdmin(ModelAdmin):
    list_display = (
        "region_code",
        "sub_system",
        "subject_id",
        "term_id",
        "metric",
        "value",
        "sample_size",
    )
    list_filter = ("region_code", "sub_system", "metric")


register_tenant_admin(BenchmarkAggregate, BenchmarkAggregateAdmin)


class GovernedSavedReportAdmin(ModelAdmin):
    list_display = ("name", "school", "updated_at", "created_by")
    list_filter = ("school",)
    search_fields = ("name",)


register_tenant_admin(GovernedSavedReport, GovernedSavedReportAdmin)
