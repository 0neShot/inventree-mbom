"""REST API views for the inventree-mbom plugin."""

from decimal import Decimal

from django.db import transaction
from django.urls import path
from rest_framework import filters, permissions, status
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


class PartRoutingDetail(MBomPermissionMixin, RetrieveUpdateDestroyAPI):
    """Retrieve, update, and delete a PartRouting."""
    serializer_class = PartRoutingSerializer
    queryset = PartRouting.objects.all()


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
        qs = super().get_queryset().select_related(
            "routing", "labor_rate", "machine_center"
        )
        routing_id = self.request.query_params.get("routing", None)
        if routing_id:
            qs = qs.filter(routing_id=routing_id, parent_operation__isnull=True)
        return qs


class RoutingOperationDetail(MBomPermissionMixin, RetrieveUpdateDestroyAPI):
    """Retrieve, update, and delete a RoutingOperation."""
    serializer_class = RoutingOperationSerializer
    queryset = RoutingOperation.objects.all()


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
        overwrite = data["overwrite"]
        batch_size = data["batch_size"]

        try:
            part = inventree_part.Part.objects.get(pk=part_id)
        except inventree_part.Part.DoesNotExist:
            return Response(
                {"error": f"Part {part_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
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

        if not created and not overwrite:
            return Response(
                {
                    "error": "Routing already exists. Pass overwrite=true to replace.",
                    "routing_id": routing.pk,
                },
                status=status.HTTP_409_CONFLICT,
            )

        if not created and overwrite:
            routing.operations.all().delete()
            routing.source_template = template
            routing.standard_batch_size = batch_size
            routing.save()

        # Copy template steps -> RoutingOperations
        def copy_steps(steps, parent_op=None):
            for step in steps.order_by("sequence_number"):
                op = RoutingOperation.objects.create(
                    routing=routing,
                    parent_operation=parent_op,
                    sequence_number=step.sequence_number,
                    name=step.name,
                    description=step.description,
                    labor_rate=step.labor_rate,
                    machine_center=step.machine_center,
                    setup_time_minutes=step.setup_time_minutes,
                    run_time_per_unit_minutes=step.run_time_per_unit_minutes,
                )
                copy_steps(step.sub_steps.all(), parent_op=op)

        copy_steps(template.steps.filter(parent_step__isnull=True))

        return Response(
            PartRoutingSerializer(routing).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Cost summary endpoint for a part
# ---------------------------------------------------------------------------

class PartCostSummaryView(APIView):
    """Return a full cost breakdown for an assembly part.

    GET /plugin/inventree-mbom/cost-summary/<part_pk>/

    Returns:
        material_cost  - native eBOM cost from InvenTree pricing
        labor_cost     - mBOM labor cost
        machine_cost   - mBOM machine cost
        total_cost     - sum of all three
        per_unit_cost  - total / batch_size
        co2_kg         - total CO2 for the routing
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        try:
            part = inventree_part.Part.objects.get(pk=pk)
        except inventree_part.Part.DoesNotExist:
            return Response({"error": "Part not found"}, status=404)

        # Material cost from InvenTree's native pricing
        material_cost = Decimal("0.00")
        try:
            pricing = part.pricing
            if pricing and pricing.overall_min is not None:
                material_cost = pricing.overall_min.amount
        except Exception:
            pass

        # mBOM costs
        try:
            routing = part.mbom_routing
            labor_cost = routing.total_labor_cost()
            machine_cost = routing.total_machine_cost()
            mfg_cost = routing.total_manufacturing_cost()
            per_unit_mfg = routing.per_unit_manufacturing_cost()
            co2 = routing.total_co2_kg()
            batch_size = routing.standard_batch_size
        except PartRouting.DoesNotExist:
            labor_cost = machine_cost = mfg_cost = per_unit_mfg = co2 = Decimal("0.00")
            batch_size = 1

        total = material_cost + mfg_cost
        per_unit_total = (
            material_cost + per_unit_mfg
        )

        return Response({
            "part_id": pk,
            "part_name": part.name,
            "batch_size": batch_size,
            "material_cost": str(material_cost),
            "labor_cost": str(labor_cost),
            "machine_cost": str(machine_cost),
            "manufacturing_cost": str(mfg_cost),
            "per_unit_manufacturing_cost": str(per_unit_mfg),
            "total_cost": str(total),
            "per_unit_total_cost": str(per_unit_total),
            "co2_kg": str(co2),
        })


# ---------------------------------------------------------------------------
# Panel view (renders the mBOM routing tab HTML)
# ---------------------------------------------------------------------------

class MBomPanelView(APIView):
    """Returns the HTML content for the mBOM panel on a part detail page."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        from django.template.loader import render_to_string

        try:
            part = inventree_part.Part.objects.get(pk=pk)
        except inventree_part.Part.DoesNotExist:
            return Response({"error": "Part not found"}, status=404)

        try:
            routing = part.mbom_routing
        except PartRouting.DoesNotExist:
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
# URL construction
# ---------------------------------------------------------------------------

def construct_urls():
    """Build and return URL patterns for the mBOM plugin."""
    return [
        # LaborRate
        path("labor-rate/", LaborRateList.as_view(), name="mbom-labor-rate-list"),
        path("labor-rate/<int:pk>/", LaborRateDetail.as_view(), name="mbom-labor-rate-detail"),
        # MachineCenter
        path("machine-center/", MachineCenterList.as_view(), name="mbom-machine-center-list"),
        path("machine-center/<int:pk>/", MachineCenterDetail.as_view(), name="mbom-machine-center-detail"),
        # ProcessTemplate
        path("process-template/", ProcessTemplateList.as_view(), name="mbom-process-template-list"),
        path("process-template/<int:pk>/", ProcessTemplateDetail.as_view(), name="mbom-process-template-detail"),
        path("process-template-step/", ProcessTemplateStepList.as_view(), name="mbom-template-step-list"),
        path("process-template-step/<int:pk>/", ProcessTemplateStepDetail.as_view(), name="mbom-template-step-detail"),
        # PartRouting
        path("routing/", PartRoutingList.as_view(), name="mbom-routing-list"),
        path("routing/<int:pk>/", PartRoutingDetail.as_view(), name="mbom-routing-detail"),
        # RoutingOperation
        path("operation/", RoutingOperationList.as_view(), name="mbom-operation-list"),
        path("operation/<int:pk>/", RoutingOperationDetail.as_view(), name="mbom-operation-detail"),
        # Actions
        path("apply-template/", ApplyTemplateView.as_view(), name="mbom-apply-template"),
        path("cost-summary/<int:pk>/", PartCostSummaryView.as_view(), name="mbom-cost-summary"),
        # Panel HTML
        path("panel/part/<int:pk>/", MBomPanelView.as_view(), name="mbom-panel"),
    ]
