"""REST API views for the inventree-mbom plugin."""

import logging
from decimal import Decimal

logger = logging.getLogger("inventree_mbom")

from django.db import transaction
from django.urls import path
from rest_framework import filters, permissions, status
from rest_framework.renderers import (
    StaticHTMLRenderer,
    TemplateHTMLRenderer,
    JSONRenderer,
)
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from InvenTree.mixins import ListCreateAPI, RetrieveUpdateDestroyAPI

import part.models as inventree_part

from .models import (
    LaborRate,
    MachineCenter,
    ProcessTemplate,
    ProcessTemplateStep,
    PartRouting,
    RoutingOperation,
)
from .serializers import (
    LaborRateSerializer,
    MachineCenterSerializer,
    ProcessTemplateSerializer,
    ProcessTemplateStepSerializer,
    PartRoutingSerializer,
    RoutingOperationSerializer,
    ApplyTemplateSerializer,
)

# ---------------------------------------------------------------------------
# Permission mixin
# ---------------------------------------------------------------------------


class MBomPermissionMixin:
    """Base permission mixin for mBOM API endpoints."""

    permission_classes = [permissions.IsAuthenticated]
    role_required = "part"


# ---------------------------------------------------------------------------
# LaborRate endpoints
# ---------------------------------------------------------------------------


class LaborRateList(MBomPermissionMixin, ListCreateAPI):
    """List and create LaborRate instances."""

    serializer_class = LaborRateSerializer
    queryset = LaborRate.objects.all()
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ["pk", "name", "hourly_rate"]
    search_fields = ["name", "description"]


class LaborRateDetail(MBomPermissionMixin, RetrieveUpdateDestroyAPI):
    """Retrieve, update, and delete a LaborRate."""

    serializer_class = LaborRateSerializer
    queryset = LaborRate.objects.all()

    def perform_update(self, serializer):
        instance = serializer.save()
        try:
            from .pricing import MbomPricingService

            MbomPricingService.schedule_for_affected_parts(instance, "labor_rate")
        except Exception as exc:
            logger.warning(
                "mBOM: Error scheduling pricing updates for labor rate: %s", exc
            )


# ---------------------------------------------------------------------------
# MachineCenter endpoints
# ---------------------------------------------------------------------------


class MachineCenterList(MBomPermissionMixin, ListCreateAPI):
    """List and create MachineCenter instances."""

    serializer_class = MachineCenterSerializer
    queryset = MachineCenter.objects.all()
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ["pk", "name", "hourly_rate"]
    search_fields = ["name", "description"]


class MachineCenterDetail(MBomPermissionMixin, RetrieveUpdateDestroyAPI):
    """Retrieve, update, and delete a MachineCenter."""

    serializer_class = MachineCenterSerializer
    queryset = MachineCenter.objects.all()

    def perform_update(self, serializer):
        instance = serializer.save()
        try:
            from .pricing import MbomPricingService

            MbomPricingService.schedule_for_affected_parts(instance, "machine_center")
        except Exception as exc:
            logger.warning(
                "mBOM: Error scheduling pricing updates for machine center: %s", exc
            )


# ---------------------------------------------------------------------------
# ProcessTemplate endpoints
# ---------------------------------------------------------------------------


class ProcessTemplateList(MBomPermissionMixin, ListCreateAPI):
    """List and create ProcessTemplate instances."""

    serializer_class = ProcessTemplateSerializer
    queryset = ProcessTemplate.objects.all()
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ["pk", "name"]
    search_fields = ["name", "description"]


class ProcessTemplateDetail(MBomPermissionMixin, RetrieveUpdateDestroyAPI):
    """Retrieve, update, and delete a ProcessTemplate."""

    serializer_class = ProcessTemplateSerializer
    queryset = ProcessTemplate.objects.all()


class ProcessTemplateStepList(MBomPermissionMixin, ListCreateAPI):
    """List and create ProcessTemplateStep instances."""

    serializer_class = ProcessTemplateStepSerializer
    queryset = ProcessTemplateStep.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        template_id = self.request.query_params.get("template", None)
        if template_id:
            qs = qs.filter(template_id=template_id, parent_step__isnull=True)
        return qs


class ProcessTemplateStepDetail(MBomPermissionMixin, RetrieveUpdateDestroyAPI):
    """Retrieve, update, and delete a ProcessTemplateStep."""

    serializer_class = ProcessTemplateStepSerializer
    queryset = ProcessTemplateStep.objects.all()


# ---------------------------------------------------------------------------
# PartRouting endpoints
# ---------------------------------------------------------------------------


def touch_routing(routing, user=None):
    """Touch a routing's updated timestamp and record the modifying user."""
    if not routing:
        return
    from django.utils import timezone

    routing.updated = timezone.now()
    if user and user.is_authenticated:
        routing.updated_by = user
    try:
        routing.save(update_fields=["updated", "updated_by"])
    except Exception:
        routing.save()


class PartRoutingList(MBomPermissionMixin, ListCreateAPI):
    """List and create PartRouting instances."""

    serializer_class = PartRoutingSerializer
    queryset = PartRouting.objects.all()
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ["pk", "part__name"]
    search_fields = ["part__name", "part__IPN", "notes"]

    def get_queryset(self):
        qs = super().get_queryset().select_related("part", "source_template")
        part_id = self.request.query_params.get("part", None)
        if part_id:
            qs = qs.filter(part_id=part_id)
        return qs

    def create(self, request, *args, **kwargs):
        part_id = request.data.get("part")
        if part_id:
            part = inventree_part.Part.objects.filter(pk=part_id).first()
            if part and part.locked:
                return Response(
                    {"error": "Part is locked. Routing creation is prohibited."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            existing = PartRouting.objects.filter(part_id=part_id).first()
            if existing:
                serializer = self.get_serializer(existing)
                return Response(serializer.data, status=status.HTTP_200_OK)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        part = serializer.validated_data.get("part")
        if part and part.locked:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("Part is locked. Routing creation is prohibited.")
        user = (
            self.request.user
            if (self.request and self.request.user.is_authenticated)
            else None
        )
        instance = serializer.save(updated_by=user)
        from .pricing import MbomPricingService

        MbomPricingService.sync_part_pricing(
            instance.part, instance.standard_batch_size
        )


class PartRoutingDetail(MBomPermissionMixin, RetrieveUpdateDestroyAPI):
    """Retrieve, update, and delete a PartRouting."""

    serializer_class = PartRoutingSerializer
    queryset = PartRouting.objects.all()

    def perform_update(self, serializer):
        if serializer.instance.part.locked:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "Part is locked. Routing modifications are prohibited."
            )
        user = (
            self.request.user
            if (self.request and self.request.user.is_authenticated)
            else None
        )
        instance = serializer.save(updated_by=user)
        from .pricing import MbomPricingService

        MbomPricingService.sync_part_pricing(
            instance.part, instance.standard_batch_size
        )

    def perform_destroy(self, instance):
        if instance.part.locked:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "Part is locked. Routing modifications are prohibited."
            )
        part = instance.part
        instance.delete()
        from .pricing import MbomPricingService

        MbomPricingService.sync_part_pricing(part)


# ---------------------------------------------------------------------------
# RoutingOperation endpoints
# ---------------------------------------------------------------------------


class RoutingOperationList(MBomPermissionMixin, ListCreateAPI):
    """List and create RoutingOperation instances."""

    serializer_class = RoutingOperationSerializer
    queryset = RoutingOperation.objects.all()
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["pk", "sequence_number"]

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("routing", "labor_rate", "machine_center")
        )
        routing_id = self.request.query_params.get("routing", None)
        if routing_id:
            qs = qs.filter(routing_id=routing_id, parent_operation__isnull=True)
        return qs

    def perform_create(self, serializer):
        routing = serializer.validated_data.get("routing")
        if routing and routing.part.locked:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "Part is locked. Routing operations cannot be modified."
            )
        instance = serializer.save()
        user = (
            self.request.user
            if (self.request and self.request.user.is_authenticated)
            else None
        )
        touch_routing(instance.routing, user)
        from .pricing import MbomPricingService

        MbomPricingService.sync_part_pricing(instance.routing.part)


class RoutingOperationDetail(MBomPermissionMixin, RetrieveUpdateDestroyAPI):
    """Retrieve, update, and delete a RoutingOperation."""

    serializer_class = RoutingOperationSerializer
    queryset = RoutingOperation.objects.all()

    def perform_update(self, serializer):
        if serializer.instance.routing.part.locked:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "Part is locked. Routing operations cannot be modified."
            )
        instance = serializer.save()
        user = (
            self.request.user
            if (self.request and self.request.user.is_authenticated)
            else None
        )
        touch_routing(instance.routing, user)
        from .pricing import MbomPricingService

        MbomPricingService.sync_part_pricing(instance.routing.part)

    def perform_destroy(self, instance):
        if instance.routing.part.locked:
            from rest_framework.exceptions import ValidationError

            raise ValidationError(
                "Part is locked. Routing operations cannot be modified."
            )
        part = instance.routing.part
        routing = instance.routing
        instance.delete()
        user = (
            self.request.user
            if (self.request and self.request.user.is_authenticated)
            else None
        )
        touch_routing(routing, user)
        from .pricing import MbomPricingService

        MbomPricingService.sync_part_pricing(part)


# ---------------------------------------------------------------------------
# Apply Template action
# ---------------------------------------------------------------------------


class ApplyTemplateView(APIView):
    """Apply a ProcessTemplate to a part, seeding a PartRouting.

    POST /plugin/inventree-mbom/apply-template/
    {
        "part_id": 42,
        "template_id": 3,
        "overwrite": false,
        "batch_size": 50
    }
    """

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = ApplyTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        part_id = data["part_id"]
        template_id = data["template_id"]
        mode = data.get("mode") or ("overwrite" if data.get("overwrite") else "skip")
        batch_size = data["batch_size"]

        try:
            part = inventree_part.Part.objects.get(pk=part_id)
        except inventree_part.Part.DoesNotExist:
            return Response(
                {"error": f"Part {part_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if part.locked:
            return Response(
                {"error": "Part is locked. Routing modifications are prohibited."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not part.assembly:
            return Response(
                {"error": "Part is not an assembly"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            template = ProcessTemplate.objects.get(pk=template_id)
        except ProcessTemplate.DoesNotExist:
            return Response(
                {"error": f"Template {template_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get or create routing
        routing, created = PartRouting.objects.get_or_create(
            part=part,
            defaults={
                "source_template": template,
                "standard_batch_size": batch_size,
            },
        )

        if not created and mode == "skip":
            return Response(
                {
                    "error": "Routing already exists. Select 'Overwrite' to replace or 'Add' to combine.",
                    "routing_id": routing.pk,
                },
                status=status.HTTP_409_CONFLICT,
            )

        if not created and mode == "overwrite":
            routing.operations.all().delete()
            routing.source_template = template
            routing.standard_batch_size = batch_size
            routing.save()

        # Determine sequence numbering offset for 'add' mode if colliding
        existing_root_ops = list(
            routing.operations.filter(parent_operation__isnull=True).order_by(
                "sequence_number"
            )
        )
        existing_root_seqs = {op.sequence_number.strip() for op in existing_root_ops}
        incoming_root_steps = list(
            template.steps.filter(parent_step__isnull=True).order_by("sequence_number")
        )

        offset = 0
        if mode == "add" and existing_root_ops:
            has_collision = any(
                s.sequence_number.strip() in existing_root_seqs
                for s in incoming_root_steps
            )
            if has_collision:
                nums = []
                for op in existing_root_ops:
                    try:
                        nums.append(float(op.sequence_number.strip()))
                    except ValueError:
                        pass
                max_val = max(nums) if nums else len(existing_root_ops) * 10
                inc_nums = []
                for s in incoming_root_steps:
                    try:
                        inc_nums.append(float(s.sequence_number.strip()))
                    except ValueError:
                        pass
                min_inc = min(inc_nums) if inc_nums else 10.0

                if max_val >= 10:
                    next_slot = ((int(max_val) // 10) + 1) * 10
                else:
                    next_slot = int(max_val) + 1
                offset = max(0, int(next_slot - min_inc))

        def get_seq(original_seq, parent_seq=None):
            if offset == 0:
                return original_seq
            if parent_seq is not None:
                parts = str(original_seq).split(".")
                suffix = ".".join(parts[1:]) if len(parts) > 1 else parts[0]
                return f"{parent_seq}.{suffix}"
            try:
                val = float(original_seq)
                new_val = val + offset
                return str(int(new_val)) if new_val.is_integer() else str(new_val)
            except ValueError:
                return f"{original_seq}_{offset}"

        # Copy template steps -> RoutingOperations
        def copy_steps(steps, parent_op=None):
            for step in steps.order_by("sequence_number"):
                parent_seq = parent_op.sequence_number if parent_op else None
                seq = get_seq(step.sequence_number, parent_seq)
                op = RoutingOperation.objects.create(
                    routing=routing,
                    parent_operation=parent_op,
                    sequence_number=seq,
                    name=step.name,
                    description=step.description,
                    labor_rate=step.labor_rate,
                    machine_center=step.machine_center,
                    setup_time_minutes=step.setup_time_minutes,
                    run_time_per_unit_minutes=step.run_time_per_unit_minutes,
                )
                copy_steps(step.sub_steps.all(), parent_op=op)

        copy_steps(template.steps.filter(parent_step__isnull=True))

        user = request.user if (request and request.user.is_authenticated) else None
        touch_routing(routing, user)

        from .pricing import MbomPricingService

        MbomPricingService.sync_part_pricing(part, batch_size)

        return Response(
            PartRoutingSerializer(routing).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Cost summary endpoint for a part
# ---------------------------------------------------------------------------


class PartCostSummaryView(APIView):
    """Return a full cost breakdown for an assembly part including setup/run split.

    GET /plugin/inventree-mbom/cost-summary/<part_pk>/
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            part = inventree_part.Part.objects.get(pk=pk)
        except inventree_part.Part.DoesNotExist:
            return Response({"error": "Part not found"}, status=404)

        from .pricing import get_assembly_full_cost

        try:
            routing = getattr(part, "mbom_routing", None)
            batch_size = (routing.standard_batch_size or 1) if routing else 1
        except Exception:
            routing = None
            batch_size = 1

        cost = get_assembly_full_cost(part, batch_size)

        labor_setup = Decimal("0.00")
        labor_run = Decimal("0.00")
        machine_setup = Decimal("0.00")
        machine_run = Decimal("0.00")
        operations_data = []

        if routing:
            for op in routing.operations.filter(
                parent_operation__isnull=True, is_active=True
            ).order_by("sequence_number"):
                op_l_setup = op.labor_setup_cost()
                op_l_run = op.labor_run_cost_per_unit() * batch_size
                op_m_setup = op.machine_setup_cost()
                op_m_run = op.machine_run_cost_per_unit() * batch_size
                labor_setup += op_l_setup
                labor_run += op_l_run
                machine_setup += op_m_setup
                machine_run += op_m_run

                sub_ops_data = []
                for sub in op.sub_operations.filter(is_active=True).order_by(
                    "sequence_number"
                ):
                    sub_l_setup = sub.labor_setup_cost()
                    sub_l_run = sub.labor_run_cost_per_unit() * batch_size
                    sub_m_setup = sub.machine_setup_cost()
                    sub_m_run = sub.machine_run_cost_per_unit() * batch_size
                    labor_setup += sub_l_setup
                    labor_run += sub_l_run
                    machine_setup += sub_m_setup
                    machine_run += sub_m_run

                    sub_ops_data.append(
                        {
                            "pk": sub.pk,
                            "sequence_number": sub.sequence_number,
                            "name": sub.name,
                            "labor_rate_name": (
                                sub.labor_rate.name if sub.labor_rate else "—"
                            ),
                            "machine_name": (
                                sub.machine_center.name if sub.machine_center else "—"
                            ),
                            "setup_min": float(sub.setup_time_minutes),
                            "cycle_min": float(sub.run_time_per_unit_minutes),
                            "per_unit_cost": str(sub.per_unit_cost(batch_size)),
                        }
                    )

                operations_data.append(
                    {
                        "pk": op.pk,
                        "sequence_number": op.sequence_number,
                        "name": op.name,
                        "labor_rate_name": op.labor_rate.name if op.labor_rate else "—",
                        "machine_name": (
                            op.machine_center.name if op.machine_center else "—"
                        ),
                        "setup_min": float(op.setup_time_minutes),
                        "cycle_min": float(op.run_time_per_unit_minutes),
                        "per_unit_cost": str(op.per_unit_cost(batch_size)),
                        "sub_operations": sub_ops_data,
                    }
                )

        if cost["has_routing"]:
            from .pricing import MbomPricingService

            MbomPricingService.sync_part_pricing(part, batch_size=batch_size)

        return Response(
            {
                "part_id": pk,
                "part_name": cost["part_name"],
                "batch_size": cost["batch_size"],
                # Batch totals
                "material_cost": str(cost["material_cost_min"]),
                "material_cost_max": str(cost["material_cost_max"]),
                "labor_cost": str(cost["labor_cost"]),
                "machine_cost": str(cost["machine_cost"]),
                "overhead_percent": str(cost.get("overhead_percent", Decimal("0.00"))),
                "overhead_cost": str(cost.get("overhead_cost", Decimal("0.00"))),
                "manufacturing_cost": str(cost["mfg_cost"]),
                "co2_kg": str(cost["co2_kg"]),
                # Setup vs Run split
                "labor_setup_cost": str(labor_setup.quantize(Decimal("0.0001"))),
                "labor_run_cost": str(labor_run.quantize(Decimal("0.0001"))),
                "machine_setup_cost": str(machine_setup.quantize(Decimal("0.0001"))),
                "machine_run_cost": str(machine_run.quantize(Decimal("0.0001"))),
                "setup_total": str(
                    (labor_setup + machine_setup).quantize(Decimal("0.0001"))
                ),
                "run_total": str((labor_run + machine_run).quantize(Decimal("0.0001"))),
                # Per-unit
                "per_unit_material": str(cost["per_unit_material_min"]),
                "per_unit_labor": str(cost["per_unit_labor"]),
                "per_unit_machine": str(cost["per_unit_machine"]),
                "per_unit_overhead": str(
                    cost.get("per_unit_overhead", Decimal("0.00"))
                ),
                "per_unit_manufacturing_cost": str(cost["per_unit_mfg"]),
                "per_unit_total_cost": str(cost["per_unit_total_min"]),
                "per_unit_total_cost_max": str(cost["per_unit_total_max"]),
                # Metadata & operations
                "has_routing": cost["has_routing"],
                "operations": operations_data,
            }
        )


# ---------------------------------------------------------------------------
# Panel view (renders the mBOM routing tab HTML)
# ---------------------------------------------------------------------------


class MBomPanelView(APIView):
    """Returns the HTML content for the mBOM panel on a part detail page."""

    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [StaticHTMLRenderer, TemplateHTMLRenderer, JSONRenderer]

    def get(self, request, pk):
        from django.template.loader import render_to_string

        try:
            part = inventree_part.Part.objects.get(pk=pk)
        except inventree_part.Part.DoesNotExist:
            return Response({"error": "Part not found"}, status=404)

        try:
            routing = getattr(part, "mbom_routing", None)
        except Exception:
            routing = None

        templates = ProcessTemplate.objects.filter(is_active=True).order_by("name")
        labor_rates = LaborRate.objects.filter(is_active=True).order_by("name")
        machine_centers = MachineCenter.objects.filter(is_active=True).order_by("name")

        ctx = {
            "part": part,
            "routing": routing,
            "templates": templates,
            "labor_rates": labor_rates,
            "machine_centers": machine_centers,
            "plugin_slug": "inventree-mbom",
        }

        html = render_to_string("inventree_mbom/mbom_panel.html", ctx, request=request)
        from django.http import HttpResponse

        return HttpResponse(html)


# ---------------------------------------------------------------------------
# Pricing Overview Panel (SA4 addition)
# ---------------------------------------------------------------------------


class MBomPricingPanelView(APIView):
    """Renders an enriched pricing breakdown panel fragment.

    GET /plugin/inventree-mbom/pricing-panel/<part_pk>/

    Shows:
     - Material eBOM cost (min/max)
     - Labor cost (setup + run breakdown)
     - Machine cost (setup + run breakdown)
     - CO2 estimate
     - Per-unit totals and grand total
    """

    permission_classes = [permissions.IsAuthenticated]
    renderer_classes = [StaticHTMLRenderer, TemplateHTMLRenderer, JSONRenderer]

    def get(self, request, pk):
        from django.template.loader import render_to_string
        from django.http import HttpResponse
        from .pricing import get_assembly_full_cost

        try:
            part = inventree_part.Part.objects.get(pk=pk)
        except inventree_part.Part.DoesNotExist:
            return Response({"error": "Part not found"}, status=404)

        try:
            routing = part.mbom_routing
            batch_size = routing.standard_batch_size
        except PartRouting.DoesNotExist:
            routing = None
            batch_size = 1

        cost_data = get_assembly_full_cost(part, batch_size)

        # Build per-operation breakdown for display
        op_breakdown = []
        if routing:
            for op in routing.operations.filter(
                parent_operation__isnull=True, is_active=True
            ).order_by("sequence_number"):
                op_breakdown.append(
                    {
                        "sequence_number": op.sequence_number,
                        "name": op.name,
                        "labor_rate_name": op.labor_rate.name if op.labor_rate else "—",
                        "machine_name": (
                            op.machine_center.name if op.machine_center else "—"
                        ),
                        "setup_time": float(op.setup_time_minutes),
                        "cycle_time": float(op.run_time_per_unit_minutes),
                        "labor_cost": float(op.labor_cost(batch_size)),
                        "machine_cost": float(op.machine_cost(batch_size)),
                        "total_cost": float(op.total_cost(batch_size)),
                        "per_unit_cost": float(op.per_unit_cost(batch_size)),
                        "sub_count": op.sub_operations.count(),
                    }
                )

        ctx = {
            "part": part,
            "routing": routing,
            "cost": cost_data,
            "op_breakdown": op_breakdown,
            "plugin_slug": "inventree-mbom",
        }
        html = render_to_string(
            "inventree_mbom/pricing_panel.html", ctx, request=request
        )
        return HttpResponse(html)


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


def construct_urls():
    """Build and return URL patterns for the mBOM plugin."""
    return [
        # LaborRate
        path("labor-rate/", LaborRateList.as_view(), name="mbom-labor-rate-list"),
        path(
            "labor-rate/<int:pk>/",
            LaborRateDetail.as_view(),
            name="mbom-labor-rate-detail",
        ),
        # MachineCenter
        path(
            "machine-center/",
            MachineCenterList.as_view(),
            name="mbom-machine-center-list",
        ),
        path(
            "machine-center/<int:pk>/",
            MachineCenterDetail.as_view(),
            name="mbom-machine-center-detail",
        ),
        # ProcessTemplate (supports both process-template and template aliases)
        path(
            "process-template/",
            ProcessTemplateList.as_view(),
            name="mbom-process-template-list",
        ),
        path(
            "process-template/<int:pk>/",
            ProcessTemplateDetail.as_view(),
            name="mbom-process-template-detail",
        ),
        path(
            "process-template-step/",
            ProcessTemplateStepList.as_view(),
            name="mbom-template-step-list",
        ),
        path(
            "process-template-step/<int:pk>/",
            ProcessTemplateStepDetail.as_view(),
            name="mbom-template-step-detail",
        ),
        path(
            "template/", ProcessTemplateList.as_view(), name="mbom-template-alias-list"
        ),
        path(
            "template/<int:pk>/",
            ProcessTemplateDetail.as_view(),
            name="mbom-template-alias-detail",
        ),
        path(
            "template-step/",
            ProcessTemplateStepList.as_view(),
            name="mbom-template-step-alias-list",
        ),
        path(
            "template-step/<int:pk>/",
            ProcessTemplateStepDetail.as_view(),
            name="mbom-template-step-alias-detail",
        ),
        # PartRouting
        path("routing/", PartRoutingList.as_view(), name="mbom-routing-list"),
        path(
            "routing/<int:pk>/", PartRoutingDetail.as_view(), name="mbom-routing-detail"
        ),
        # RoutingOperation
        path("operation/", RoutingOperationList.as_view(), name="mbom-operation-list"),
        path(
            "operation/<int:pk>/",
            RoutingOperationDetail.as_view(),
            name="mbom-operation-detail",
        ),
        # Actions
        path(
            "apply-template/", ApplyTemplateView.as_view(), name="mbom-apply-template"
        ),
        path(
            "cost-summary/<int:pk>/",
            PartCostSummaryView.as_view(),
            name="mbom-cost-summary",
        ),
        # Panel HTML
        path("panel/part/<int:pk>/", MBomPanelView.as_view(), name="mbom-panel"),
        # Pricing overview panel (retained for backward-compat API calls)
        path(
            "pricing-panel/<int:pk>/",
            MBomPricingPanelView.as_view(),
            name="mbom-pricing-panel",
        ),
    ]
