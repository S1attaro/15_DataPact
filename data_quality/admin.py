"""
Django Admin configuration for DataPact.

Rules are edited inline on their contract, and violations inline on their run,
because in both cases the child records have no meaning apart from the parent.
This also makes the foreign-key relationships visible on a single page rather
than requiring navigation between flat list views.
"""

from django.contrib import admin

from .models import Contract, Dataset, ValidationRule, ValidationRun, Violation


class ContractInline(admin.TabularInline):
    """Contract versions shown on the Dataset page, newest first."""

    model = Contract
    extra = 0
    fields = ("version_number", "status", "change_note", "created_at")
    readonly_fields = ("created_at",)
    show_change_link = True


class ValidationRuleInline(admin.TabularInline):
    """Rules edited in place on the contract version they belong to."""

    model = ValidationRule
    extra = 1
    fields = ("column_name", "rule_type", "parameters")


class ViolationInline(admin.TabularInline):
    """Violations shown on the run that produced them."""

    model = Violation
    extra = 0
    fields = ("rule", "failed_row_count", "message", "resolution")
    show_change_link = True


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("name", "source_team", "owner", "contract_count", "created_at")
    list_filter = ("source_team", "owner")
    search_fields = ("name", "source_team", "description")
    inlines = [ContractInline]

    @admin.display(description="Contract versions")
    def contract_count(self, obj):
        return obj.contracts.count()


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("dataset", "version_number", "status", "rule_count", "run_count", "change_note")
    list_filter = ("status", "dataset")
    search_fields = ("dataset__name", "change_note")
    inlines = [ValidationRuleInline]

    @admin.display(description="Rules")
    def rule_count(self, obj):
        return obj.rules.count()

    @admin.display(description="Runs")
    def run_count(self, obj):
        return obj.runs.count()


@admin.register(ValidationRule)
class ValidationRuleAdmin(admin.ModelAdmin):
    list_display = ("column_name", "rule_type", "parameters", "contract")
    list_filter = ("rule_type", "contract__dataset")
    search_fields = ("column_name",)


@admin.register(ValidationRun)
class ValidationRunAdmin(admin.ModelAdmin):
    list_display = ("file_name", "dataset_name", "contract", "status", "row_count",
                    "violation_count", "submitted_by", "started_at")
    list_filter = ("status", "contract__dataset", "submitted_by")
    search_fields = ("file_name", "contract__dataset__name")
    date_hierarchy = "started_at"
    inlines = [ViolationInline]

    @admin.display(description="Dataset", ordering="contract__dataset__name")
    def dataset_name(self, obj):
        return obj.contract.dataset.name

    @admin.display(description="Violations")
    def violation_count(self, obj):
        return obj.violations.count()


@admin.register(Violation)
class ViolationAdmin(admin.ModelAdmin):
    list_display = ("rule", "run", "failed_row_count", "resolution", "message")
    list_filter = ("resolution", "rule__rule_type", "run__contract__dataset")
    search_fields = ("message", "rule__column_name")
