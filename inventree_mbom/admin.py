"""Django admin registration for inventree-mbom models."""

from django.contrib import admin

from .models import (
    LaborRate,
    MachineCenter,
    ProcessTemplate,
    ProcessTemplateStep,
    PartRouting,
    RoutingOperation,
)


def _safe_register(model, admin_class):
    try:
        admin.site.unregister(model)
    except Exception:
        pass
    admin.site.register(model, admin_class)


class LaborRateAdmin(admin.ModelAdmin):
    list_display = ["name", "hourly_rate", "currency", "is_active"]
    search_fields = ["name", "description"]
    list_filter = ["is_active", "currency"]


class MachineCenterAdmin(admin.ModelAdmin):
    list_display = ["name", "hourly_rate", "currency", "co2_factor_per_minute", "is_active"]
    search_fields = ["name", "description"]
    list_filter = ["is_active", "currency"]


class ProcessTemplateStepInline(admin.TabularInline):
    model = ProcessTemplateStep
    extra = 1
    fields = [
        "sequence_number",
        "name",
        "parent_step",
        "labor_rate",
        "machine_center",
        "setup_time_minutes",
        "run_time_per_unit_minutes",
    ]


class ProcessTemplateAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created", "updated"]
    search_fields = ["name", "description"]
    list_filter = ["is_active"]
    inlines = [ProcessTemplateStepInline]


class RoutingOperationInline(admin.TabularInline):
    model = RoutingOperation
    extra = 1
    fields = [
        "sequence_number",
        "name",
        "parent_operation",
        "labor_rate",
        "machine_center",
        "setup_time_minutes",
        "run_time_per_unit_minutes",
        "is_active",
    ]


class PartRoutingAdmin(admin.ModelAdmin):
    list_display = ["part", "source_template", "standard_batch_size", "created"]
    search_fields = ["part__name", "part__IPN"]
    inlines = [RoutingOperationInline]


class RoutingOperationAdmin(admin.ModelAdmin):
    list_display = [
        "sequence_number",
        "name",
        "routing",
        "labor_rate",
        "machine_center",
        "setup_time_minutes",
        "run_time_per_unit_minutes",
        "is_active",
    ]
    search_fields = ["name", "routing__part__name"]
    list_filter = ["is_active", "labor_rate", "machine_center"]


_safe_register(LaborRate, LaborRateAdmin)
_safe_register(MachineCenter, MachineCenterAdmin)
_safe_register(ProcessTemplate, ProcessTemplateAdmin)
_safe_register(PartRouting, PartRoutingAdmin)
_safe_register(RoutingOperation, RoutingOperationAdmin)