"""DRF serializers for the inventree-mbom plugin."""

from rest_framework import serializers

from .models import (
    LaborRate,
    MachineCenter,
    ProcessTemplate,
    ProcessTemplateStep,
    PartRouting,
    RoutingOperation,
)


class LaborRateSerializer(serializers.ModelSerializer):
    """Serializer for LaborRate model."""

    rate_per_minute = serializers.DecimalField(
        max_digits=12, decimal_places=6, read_only=True
    )

    class Meta:
        model = LaborRate
        fields = [
            "pk",
            "name",
            "description",
            "hourly_rate",
            "currency",
            "rate_per_minute",
            "is_active",
            "created",
            "updated",
        ]
        read_only_fields = ["pk", "created", "updated"]


class MachineCenterSerializer(serializers.ModelSerializer):
    """Serializer for MachineCenter model."""

    rate_per_minute = serializers.DecimalField(
        max_digits=12, decimal_places=6, read_only=True
    )

    class Meta:
        model = MachineCenter
        fields = [
            "pk",
            "name",
            "description",
            "hourly_rate",
            "currency",
            "rate_per_minute",
            "co2_factor_per_minute",
            "is_active",
            "created",
            "updated",
        ]
        read_only_fields = ["pk", "created", "updated"]


class ProcessTemplateStepSerializer(serializers.ModelSerializer):
    """Serializer for ProcessTemplateStep."""

    sub_steps = serializers.SerializerMethodField()

    class Meta:
        model = ProcessTemplateStep
        fields = [
            "pk",
            "template",
            "parent_step",
            "sequence_number",
            "name",
            "description",
            "labor_rate",
            "machine_center",
            "setup_time_minutes",
            "run_time_per_unit_minutes",
            "sub_steps",
        ]
        read_only_fields = ["pk"]

    def get_sub_steps(self, obj):
        """Return nested sub-steps for this step."""
        children = obj.sub_steps.all().order_by("sequence_number")
        return ProcessTemplateStepSerializer(children, many=True).data


class ProcessTemplateSerializer(serializers.ModelSerializer):
    """Serializer for ProcessTemplate with nested steps."""

    steps = serializers.SerializerMethodField()
    step_count = serializers.IntegerField(source="steps.count", read_only=True)

    class Meta:
        model = ProcessTemplate
        fields = [
            "pk",
            "name",
            "description",
            "is_active",
            "step_count",
            "steps",
            "created",
            "updated",
        ]
        read_only_fields = ["pk", "created", "updated"]

    def get_steps(self, obj):
        """Return only top-level steps; sub-steps are nested within them."""
        top_level = obj.steps.filter(parent_step__isnull=True).order_by(
            "sequence_number"
        )
        return ProcessTemplateStepSerializer(top_level, many=True).data


class RoutingOperationSerializer(serializers.ModelSerializer):
    """Serializer for RoutingOperation with computed costs."""

    sub_operations = serializers.SerializerMethodField()

    # Read-only computed cost fields
    labor_setup_cost = serializers.SerializerMethodField()
    labor_run_cost_per_unit = serializers.SerializerMethodField()
    machine_setup_cost = serializers.SerializerMethodField()
    machine_run_cost_per_unit = serializers.SerializerMethodField()
    per_unit_cost = serializers.SerializerMethodField()

    class Meta:
        model = RoutingOperation
        fields = [
            "pk",
            "routing",
            "parent_operation",
            "sequence_number",
            "name",
            "description",
            "labor_rate",
            "machine_center",
            "setup_time_minutes",
            "run_time_per_unit_minutes",
            "is_active",
            # Computed
            "sub_operations",
            "labor_setup_cost",
            "labor_run_cost_per_unit",
            "machine_setup_cost",
            "machine_run_cost_per_unit",
            "per_unit_cost",
        ]
        read_only_fields = ["pk"]

    def get_sub_operations(self, obj):
        children = obj.sub_operations.all().order_by("sequence_number")
        return RoutingOperationSerializer(children, many=True).data

    def _batch_size(self, obj):
        try:
            return obj.routing.standard_batch_size or 1
        except Exception:
            return 1

    def get_labor_setup_cost(self, obj):
        return str(obj.labor_setup_cost())

    def get_labor_run_cost_per_unit(self, obj):
        return str(obj.labor_run_cost_per_unit())

    def get_machine_setup_cost(self, obj):
        return str(obj.machine_setup_cost())

    def get_machine_run_cost_per_unit(self, obj):
        return str(obj.machine_run_cost_per_unit())

    def get_per_unit_cost(self, obj):
        return str(obj.per_unit_cost(self._batch_size(obj)))


class PartRoutingSerializer(serializers.ModelSerializer):
    """Serializer for PartRouting with full cost summary."""

    operations = serializers.SerializerMethodField()
    part_name = serializers.CharField(source="part.name", read_only=True)
    part_ipn = serializers.CharField(source="part.IPN", read_only=True)

    # Summary cost fields
    total_labor_cost = serializers.SerializerMethodField()
    total_machine_cost = serializers.SerializerMethodField()
    total_manufacturing_cost = serializers.SerializerMethodField()
    per_unit_manufacturing_cost = serializers.SerializerMethodField()
    total_co2_kg = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PartRouting
        fields = [
            "pk",
            "part",
            "part_name",
            "part_ipn",
            "source_template",
            "standard_batch_size",
            "notes",
            "created",
            "updated",
            "updated_by",
            "updated_by_name",
            # Computed
            "operations",
            "total_labor_cost",
            "total_machine_cost",
            "total_manufacturing_cost",
            "per_unit_manufacturing_cost",
            "total_co2_kg",
        ]
        read_only_fields = ["pk", "created", "updated", "updated_by", "updated_by_name"]
        extra_kwargs = {
            "part": {
                "error_messages": {
                    "unique": "A manufacturing routing for this part already exists.",
                }
            }
        }

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            return obj.updated_by.get_full_name() or obj.updated_by.username
        return None

    def get_operations(self, obj):
        top_level = obj.operations.filter(parent_operation__isnull=True).order_by(
            "sequence_number"
        )
        return RoutingOperationSerializer(top_level, many=True).data

    def get_total_labor_cost(self, obj):
        return str(obj.total_labor_cost())

    def get_total_machine_cost(self, obj):
        return str(obj.total_machine_cost())

    def get_total_manufacturing_cost(self, obj):
        return str(obj.total_manufacturing_cost())

    def get_per_unit_manufacturing_cost(self, obj):
        return str(obj.per_unit_manufacturing_cost())

    def get_total_co2_kg(self, obj):
        return str(obj.total_co2_kg())


class ApplyTemplateSerializer(serializers.Serializer):
    """Serializer for the 'apply template to part routing' action."""

    part_id = serializers.IntegerField(required=True)
    template_id = serializers.IntegerField(required=True)
    mode = serializers.CharField(required=False, default=None)
    overwrite = serializers.BooleanField(required=False, default=False)
    batch_size = serializers.IntegerField(default=1, min_value=1)

    def validate(self, attrs):
        mode = attrs.get("mode")
        if not mode:
            attrs["mode"] = "overwrite" if attrs.get("overwrite") else "skip"
        elif mode not in ["add", "overwrite", "skip"]:
            attrs["mode"] = (
                "overwrite"
                if mode == "true"
                else ("skip" if mode == "false" else "add")
            )
        return attrs
