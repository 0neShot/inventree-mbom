"""Django models for the inventree-mbom plugin.

Data model hierarchy:
  Central Tariff Catalog:
    LaborRate           - Named hourly labor rate (Assembler, Machinist, etc.)
    MachineCenter       - Named machine with hourly rate + CO2 factor

  Process Templates (reusable blueprints):
    ProcessTemplate     - Top-level template (e.g. "SMT Assembly Standard")
    ProcessTemplateStep - Hierarchical step within a template (Op 10 -> 10.1, 10.2)

  Part Routings (instantiated for a specific assembly):
    PartRouting         - One routing per assembly part
    RoutingOperation    - Individual operation on a part routing (parent + children)
"""

from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

import part.models as inventree_part

# ---------------------------------------------------------------------------
# Central Tariff Catalog
# ---------------------------------------------------------------------------


class LaborRate(models.Model):
    """A named labor classification with an hourly (or per-minute) rate.

    Examples: Assembler @ 28 EUR/hr, Engineer @ 95 EUR/hr, Welder @ 42 EUR/hr
    """

    class Meta:
        app_label = "inventree_mbom"
        verbose_name = _("Labor Rate")
        verbose_name_plural = _("Labor Rates")
        ordering = ["name"]

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("Name"),
        help_text=_("Labor classification name (e.g. Assembler, Engineer)"),
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
    )

    # Rate stored as EUR (or configured currency) per hour
    hourly_rate = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Hourly Rate"),
        help_text=_("Labor cost per hour in the configured currency"),
    )

    currency = models.CharField(
        max_length=10,
        default="EUR",
        verbose_name=_("Currency"),
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.hourly_rate} {self.currency}/hr)"

    @property
    def rate_per_minute(self) -> Decimal:
        """Return the per-minute rate."""
        return self.hourly_rate / Decimal("60")

    @staticmethod
    def get_api_url():
        return "/plugin/inventree-mbom/labor-rate/"


class MachineCenter(models.Model):
    """A named machine workcenter with an hourly operating rate and CO2 factor.

    Examples: 5-Axis CNC @ 120 EUR/hr, Reflow Oven @ 35 EUR/hr
    """

    class Meta:
        app_label = "inventree_mbom"
        verbose_name = _("Machine Center")
        verbose_name_plural = _("Machine Centers")
        ordering = ["name"]

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("Name"),
        help_text=_("Machine center name (e.g. 5-Axis CNC, Reflow Oven)"),
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
    )

    hourly_rate = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Hourly Rate"),
        help_text=_("Machine operating cost per hour (power, depreciation, tooling)"),
    )

    currency = models.CharField(
        max_length=10,
        default="EUR",
        verbose_name=_("Currency"),
    )

    # CO2 emission factor in kg CO2e per minute of operation
    co2_factor_per_minute = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=Decimal("0.000000"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("CO₂ Factor (kg/min)"),
        help_text=_("CO₂ equivalent emissions per minute of machine operation"),
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.hourly_rate} {self.currency}/hr)"

    @property
    def rate_per_minute(self) -> Decimal:
        """Return the per-minute rate."""
        return self.hourly_rate / Decimal("60")

    @staticmethod
    def get_api_url():
        return "/plugin/inventree-mbom/machine-center/"


# ---------------------------------------------------------------------------
# Process Templates (Reusable Blueprints)
# ---------------------------------------------------------------------------


class ProcessTemplate(models.Model):
    """A reusable process routing template.

    Templates are applied to assemblies to seed a PartRouting with
    pre-configured operations, which engineers can then customise.

    Examples: "SMT Assembly Standard", "CNC 5-Axis Turning"
    """

    class Meta:
        app_label = "inventree_mbom"
        verbose_name = _("Process Template")
        verbose_name_plural = _("Process Templates")
        ordering = ["name"]

    name = models.CharField(
        max_length=200,
        unique=True,
        verbose_name=_("Template Name"),
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description"),
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @staticmethod
    def get_api_url():
        return "/plugin/inventree-mbom/process-template/"


class ProcessTemplateStep(models.Model):
    """A hierarchical step within a ProcessTemplate.

    Steps support parent/child nesting to model:
      Op 10: SMT Assembly
        10.1: Stencil Paste
        10.2: Pick & Place
        10.3: Reflow

    Each step independently specifies labor and machine resources
    with fixed setup time and per-unit cycle time.
    """

    class Meta:
        app_label = "inventree_mbom"
        verbose_name = _("Process Template Step")
        verbose_name_plural = _("Process Template Steps")
        ordering = ["template", "sequence_number"]

    template = models.ForeignKey(
        ProcessTemplate,
        on_delete=models.CASCADE,
        related_name="steps",
        verbose_name=_("Process Template"),
    )

    parent_step = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="sub_steps",
        verbose_name=_("Parent Step"),
        help_text=_("Leave blank for top-level operations"),
    )

    # e.g. "1", "1.1", "1.2", "2"
    sequence_number = models.CharField(
        max_length=20,
        verbose_name=_("Sequence Number"),
        help_text=_("Operation sequence (e.g. 1, 1.1, 2)"),
    )

    name = models.CharField(
        max_length=200,
        verbose_name=_("Step Name"),
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description / Tool Notes"),
    )

    # Labor resource
    labor_rate = models.ForeignKey(
        LaborRate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_steps",
        verbose_name=_("Labor Rate"),
    )

    # Machine resource
    machine_center = models.ForeignKey(
        MachineCenter,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="template_steps",
        verbose_name=_("Machine Center"),
    )

    # Times in decimal minutes
    setup_time_minutes = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Setup Time (min)"),
        help_text=_("Fixed setup time in minutes (charged once per batch)"),
    )

    run_time_per_unit_minutes = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Run Time per Unit (min)"),
        help_text=_("Cycle time per unit in minutes"),
    )

    def __str__(self):
        return f"[{self.sequence_number}] {self.name}"


# ---------------------------------------------------------------------------
# Part Routings (Per-Assembly Instances)
# ---------------------------------------------------------------------------


class PartRouting(models.Model):
    """The manufacturing routing assigned to a specific assembly part.

    One PartRouting per part. Contains RoutingOperations that may be
    seeded from a ProcessTemplate or built from scratch.
    """

    class Meta:
        app_label = "inventree_mbom"
        verbose_name = _("Part Routing")
        verbose_name_plural = _("Part Routings")

    part = models.OneToOneField(
        inventree_part.Part,
        on_delete=models.CASCADE,
        related_name="mbom_routing",
        verbose_name=_("Part"),
        limit_choices_to={"assembly": True},
    )

    source_template = models.ForeignKey(
        ProcessTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applied_routings",
        verbose_name=_("Source Template"),
        help_text=_("Template this routing was seeded from (informational)"),
    )

    # Standard batch size used to amortise fixed setup costs
    standard_batch_size = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name=_("Standard Batch Size"),
        help_text=_("Used to amortise setup costs into per-unit cost"),
    )

    # General overhead percentage applied to labor and machine costs
    overhead_percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Overhead Percentage"),
        help_text=_("General overhead percentage applied to labor and machine costs"),
    )

    notes = models.TextField(
        blank=True,
        verbose_name=_("Notes"),
    )

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("Updated By"),
    )

    def __str__(self):
        return f"Routing: {self.part}"

    @staticmethod
    def get_api_url():
        return "/plugin/inventree-mbom/routing/"

    # ------------------------------------------------------------------
    # Cost computation helpers
    # ------------------------------------------------------------------

    @property
    def top_level_operations(self):
        """Top-level operations (excluding nested sub-steps), ordered by sequence."""
        return self.operations.filter(parent_operation__isnull=True).order_by(
            "sequence_number"
        )

    def _get_top_level_operations(self):
        return self.top_level_operations

    @property
    def all_operations(self):
        """All operations (including nested sub-steps), ordered by sequence."""
        return self.operations.all().order_by("sequence_number")

    @property
    def total_setup_time_minutes(self) -> Decimal:
        """Total setup time in minutes across all operations (excluding parent description steps)."""
        return sum(
            (
                op.setup_time_minutes
                for op in self.operations.all()
                if not op.sub_operations.exists()
            ),
            Decimal("0.0000"),
        )

    @property
    def total_run_time_per_unit_minutes(self) -> Decimal:
        """Total run time in minutes per unit across all operations (excluding parent description steps)."""
        return sum(
            (
                op.run_time_per_unit_minutes
                for op in self.operations.all()
                if not op.sub_operations.exists()
            ),
            Decimal("0.0000"),
        )

    @property
    def used_labor_rates(self):
        """Distinct LaborRate objects referenced across all operations in this routing."""
        rate_ids = (
            self.operations.filter(labor_rate__isnull=False)
            .values_list("labor_rate_id", flat=True)
            .distinct()
        )
        return LaborRate.objects.filter(id__in=rate_ids).order_by("name")

    @property
    def used_machine_centers(self):
        """Distinct MachineCenter objects referenced across all operations in this routing."""
        mc_ids = (
            self.operations.filter(machine_center__isnull=False)
            .values_list("machine_center_id", flat=True)
            .distinct()
        )
        return MachineCenter.objects.filter(id__in=mc_ids).order_by("name")

    def total_labor_cost(self, batch_size: int = None) -> Decimal:
        """Sum of labor costs for all operations at all levels."""
        qty = batch_size or self.standard_batch_size
        total = Decimal("0.00")
        for op in self.operations.all():
            total += op.labor_cost(qty)
        return total

    def total_machine_cost(self, batch_size: int = None) -> Decimal:
        """Sum of machine costs for all operations at all levels."""
        qty = batch_size or self.standard_batch_size
        total = Decimal("0.00")
        for op in self.operations.all():
            total += op.machine_cost(qty)
        return total

    @property
    def overhead_factor(self) -> Decimal:
        """Multiplicative factor: 1 + (overhead_percent / 100)."""
        return Decimal("1.00") + (self.overhead_percent / Decimal("100.00"))

    def total_overhead_cost(self, batch_size: int = None) -> Decimal:
        """Overhead cost applied to labor + machine: (labor + machine) * (overhead_percent / 100)."""
        qty = batch_size or self.standard_batch_size
        base = self.total_labor_cost(qty) + self.total_machine_cost(qty)
        return base * (self.overhead_percent / Decimal("100.00"))

    def total_base_cost(self, batch_size: int = None) -> Decimal:
        """Total base manufacturing cost (labor + machine before overhead)."""
        qty = batch_size or self.standard_batch_size
        return self.total_labor_cost(qty) + self.total_machine_cost(qty)

    def per_unit_base_cost(self) -> Decimal:
        """Per-unit base manufacturing cost (labor + machine before overhead)."""
        total = self.total_base_cost()
        return total / Decimal(str(self.standard_batch_size))

    def per_unit_overhead_cost(self) -> Decimal:
        """Per-unit overhead cost."""
        total = self.total_overhead_cost()
        return total / Decimal(str(self.standard_batch_size))

    def total_manufacturing_cost(self, batch_size: int = None) -> Decimal:
        """Total labor + machine + overhead cost for this routing."""
        qty = batch_size or self.standard_batch_size
        base = self.total_labor_cost(qty) + self.total_machine_cost(qty)
        return base * self.overhead_factor

    def total_co2_kg(self, batch_size: int = None) -> Decimal:
        """Total CO₂ emissions in kg for this routing."""
        qty = batch_size or self.standard_batch_size
        total = Decimal("0.000000")
        for op in self.operations.all():
            total += op.co2_kg(qty)
        return total

    def per_unit_manufacturing_cost(self) -> Decimal:
        """Per-unit manufacturing cost (total divided by batch size)."""
        total = self.total_manufacturing_cost()
        return total / Decimal(str(self.standard_batch_size))


class RoutingOperation(models.Model):
    """A single operation (or sub-step) within a PartRouting.

    Supports two-level hierarchy: parent operations and child sub-steps.
    Cost = setup_cost (fixed/batch) + run_cost (per unit * qty).
    """

    class Meta:
        app_label = "inventree_mbom"
        verbose_name = _("Routing Operation")
        verbose_name_plural = _("Routing Operations")
        ordering = ["routing", "sequence_number"]

    routing = models.ForeignKey(
        PartRouting,
        on_delete=models.CASCADE,
        related_name="operations",
        verbose_name=_("Part Routing"),
    )

    parent_operation = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="sub_operations",
        verbose_name=_("Parent Operation"),
    )

    sequence_number = models.CharField(
        max_length=20,
        verbose_name=_("Sequence"),
        help_text=_("e.g. 1, 1.1, 1.2, 2"),
    )

    name = models.CharField(
        max_length=200,
        verbose_name=_("Operation Name"),
    )

    description = models.TextField(
        blank=True,
        verbose_name=_("Description / Tool Notes"),
    )

    labor_rate = models.ForeignKey(
        LaborRate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="routing_operations",
        verbose_name=_("Labor Rate"),
    )

    machine_center = models.ForeignKey(
        MachineCenter,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="routing_operations",
        verbose_name=_("Machine Center"),
    )

    # Times in decimal minutes
    setup_time_minutes = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Setup Time (min)"),
    )

    run_time_per_unit_minutes = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(Decimal("0.00"))],
        verbose_name=_("Run Time per Unit (min)"),
    )

    is_active = models.BooleanField(default=True, verbose_name=_("Active"))

    @property
    def is_parent_operation(self) -> bool:
        """True if this operation has one or more sub-operations (acting as a description tool)."""
        if self.pk:
            return self.sub_operations.exists()
        return False

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        old_seq = None
        if not is_new and not self.parent_operation_id:
            try:
                old_seq = (
                    RoutingOperation.objects.filter(pk=self.pk)
                    .values_list("sequence_number", flat=True)
                    .first()
                )
            except Exception:
                pass

        # Parent operations with sub-steps act strictly as description tools
        if self.pk and self.sub_operations.exists():
            self.labor_rate = None
            self.machine_center = None
            self.setup_time_minutes = Decimal("0.0000")
            self.run_time_per_unit_minutes = Decimal("0.0000")

        super().save(*args, **kwargs)

        # When a child operation is attached, clear any existing rates/times from the parent operation
        if self.parent_operation_id:
            try:
                parent = self.parent_operation
                if parent and (
                    parent.labor_rate_id is not None
                    or parent.machine_center_id is not None
                    or parent.setup_time_minutes > Decimal("0.0000")
                    or parent.run_time_per_unit_minutes > Decimal("0.0000")
                ):
                    RoutingOperation.objects.filter(pk=parent.pk).update(
                        labor_rate=None,
                        machine_center=None,
                        setup_time_minutes=Decimal("0.0000"),
                        run_time_per_unit_minutes=Decimal("0.0000"),
                    )
            except Exception:
                pass

        # If a top-level operation's sequence changed, cascade prefix to its child sub-operations
        if (
            old_seq
            and str(old_seq).strip() != str(self.sequence_number).strip()
            and not self.parent_operation_id
        ):
            parent_seq = str(self.sequence_number).strip()
            for sub in self.sub_operations.all():
                curr_seq = str(sub.sequence_number).strip()
                step_idx = curr_seq.split(".")[-1]
                new_sub_seq = f"{parent_seq}.{step_idx}"
                if curr_seq != new_sub_seq:
                    sub.sequence_number = new_sub_seq
                    sub.save(update_fields=["sequence_number"])

    def __str__(self):
        return f"[{self.sequence_number}] {self.name} ({self.routing.part})"

    # ------------------------------------------------------------------
    # Cost computation
    # ------------------------------------------------------------------

    def _labor_rate_per_min(self) -> Decimal:
        if self.labor_rate:
            return self.labor_rate.rate_per_minute
        return Decimal("0.00")

    def _machine_rate_per_min(self) -> Decimal:
        if self.machine_center:
            return self.machine_center.rate_per_minute
        return Decimal("0.00")

    def labor_setup_cost(self) -> Decimal:
        """Fixed labor cost for setup (once per batch). Parent description ops return 0."""
        if self.is_parent_operation:
            return Decimal("0.00")
        return self.setup_time_minutes * self._labor_rate_per_min()

    def labor_run_cost_per_unit(self) -> Decimal:
        """Labor cost per unit produced. Parent description ops return 0."""
        if self.is_parent_operation:
            return Decimal("0.00")
        return self.run_time_per_unit_minutes * self._labor_rate_per_min()

    def labor_cost(self, batch_size: int = None) -> Decimal:
        """Total labor cost for a given batch size. Parent description ops return 0."""
        if self.is_parent_operation:
            return Decimal("0.00")
        qty = batch_size or (self.routing.standard_batch_size if self.routing else 1)
        return self.labor_setup_cost() + (self.labor_run_cost_per_unit() * qty)

    def machine_setup_cost(self) -> Decimal:
        """Fixed machine cost for setup (once per batch). Parent description ops return 0."""
        if self.is_parent_operation:
            return Decimal("0.00")
        return self.setup_time_minutes * self._machine_rate_per_min()

    def machine_run_cost_per_unit(self) -> Decimal:
        """Machine cost per unit produced. Parent description ops return 0."""
        if self.is_parent_operation:
            return Decimal("0.00")
        return self.run_time_per_unit_minutes * self._machine_rate_per_min()

    def machine_cost(self, batch_size: int = None) -> Decimal:
        """Total machine cost for a given batch size. Parent description ops return 0."""
        if self.is_parent_operation:
            return Decimal("0.00")
        qty = batch_size or (self.routing.standard_batch_size if self.routing else 1)
        return self.machine_setup_cost() + (self.machine_run_cost_per_unit() * qty)

    def base_cost(self, batch_size: int = None) -> Decimal:
        """Combined labor + machine cost without overhead. Parent ops return 0."""
        if self.is_parent_operation:
            return Decimal("0.00")
        qty = batch_size or (self.routing.standard_batch_size if self.routing else 1)
        return self.labor_cost(qty) + self.machine_cost(qty)

    def base_per_unit_cost(self, batch_size: int = None) -> Decimal:
        """Base per-unit cost (labor + machine) before overhead. Parent ops return 0."""
        if self.is_parent_operation:
            return Decimal("0.00")
        qty = batch_size or (self.routing.standard_batch_size if self.routing else 1)
        return self.base_cost(qty) / Decimal(str(qty))

    def overhead_per_unit_cost(self, batch_size: int = None) -> Decimal:
        """Overhead per-unit cost. Parent ops return 0."""
        if self.is_parent_operation:
            return Decimal("0.00")
        qty = batch_size or (self.routing.standard_batch_size if self.routing else 1)
        base = self.base_per_unit_cost(qty)
        pct = self.routing.overhead_percent if self.routing else Decimal("0.00")
        return base * (pct / Decimal("100.00"))

    def total_cost(self, batch_size: int = None) -> Decimal:
        """Combined labor + machine cost, scaled by routing overhead factor. Parent ops return 0."""
        if self.is_parent_operation:
            return Decimal("0.00")
        qty = batch_size or (self.routing.standard_batch_size if self.routing else 1)
        base = self.labor_cost(qty) + self.machine_cost(qty)
        factor = self.routing.overhead_factor if self.routing else Decimal("1.00")
        return base * factor

    def per_unit_cost(self, batch_size: int = None) -> Decimal:
        """Per-unit cost amortised over batch size. Parent ops return 0."""
        if self.is_parent_operation:
            return Decimal("0.00")
        qty = batch_size or (self.routing.standard_batch_size if self.routing else 1)
        return self.total_cost(qty) / Decimal(str(qty))

    def co2_kg(self, batch_size: int = None) -> Decimal:
        """CO₂ emissions in kg for this operation. Parent ops return 0."""
        if self.is_parent_operation or not self.machine_center:
            return Decimal("0.000000")
        qty = batch_size or (self.routing.standard_batch_size if self.routing else 1)
        total_machine_minutes = self.setup_time_minutes + (
            self.run_time_per_unit_minutes * qty
        )
        return total_machine_minutes * self.machine_center.co2_factor_per_minute
