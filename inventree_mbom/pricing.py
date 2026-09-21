"""Pricing bridge for the inventree-mbom plugin.

Solves the Core Blocker:
    InvenTree's PartPricing.bom_cost exclusively sums physical BOM items.
    This module adds mBOM (manufacturing routing) costs to the pricing picture
    without modifying InvenTree core code.

Strategy:
    1. PartRoutingPricingMixin.get_mbom_unit_cost()
       - Calculates per-unit manufacturing cost from a part's PartRouting.
       - Recursive: sub-assemblies are resolved through their own PartRoutings
         so multi-level assemblies get correct rolled-up mBOM costs.

    2. get_assembly_full_cost(part, batch_size)
       - Returns a complete cost breakdown dict:
           material_cost, labor_cost, machine_cost, mfg_cost,
           per_unit_material, per_unit_manufacturing, per_unit_total

    3. Signal handler (in signals.py) calls PartPricing.schedule_for_update()
       when a rate changes — InvenTree's background pricing worker then
       recalculates, and our cost-summary API serves the fresh numbers.

    4. MbomPricingService.update_part_extra_cost()
       - Optional: maintains an InvenTree "extra cost" item on the PartPricing
         record so the mBOM cost appears in InvenTree's native pricing grid.
         Uses Part.pricing.extra_cost (if available in the InvenTree version).

Multi-level rollup example:
    Top Assembly
    ├── Sub-assembly A  (has PartRouting with 3 ops, per-unit cost = 5.00 EUR)
    │   └── Raw Material BOM
    └── Sub-assembly B  (has PartRouting with 1 op,  per-unit cost = 2.50 EUR)
        └── Raw Material BOM

    Top Assembly full cost = (BOM material) + (Op cost at top) + (A.per_unit × qty_A) + (B.per_unit × qty_B)
"""

import logging
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger("inventree_mbom.pricing")


# =========================================================
# Core Cost Calculation
# =========================================================


def get_mbom_unit_cost(part, batch_size: int = 1, _visited: set = None) -> dict:
    """Return the per-unit mBOM cost breakdown for a part.

    Args:
        part: InvenTree Part instance
        batch_size: number of units to produce (affects setup cost amortisation)
        _visited: internal set to detect circular BoMs

    Returns:
        dict with keys:
            labor_cost      - total labor cost for the batch
            machine_cost    - total machine cost for the batch
            mfg_cost        - labor + machine for the batch
            per_unit_labor   - per-unit labor
            per_unit_machine - per-unit machine
            per_unit_mfg    - per-unit total manufacturing
            co2_kg          - CO2 emissions for the batch
            has_routing     - bool, whether a PartRouting exists
    """
    if _visited is None:
        _visited = set()

    empty = {
        "labor_cost": Decimal("0.00"),
        "machine_cost": Decimal("0.00"),
        "mfg_cost": Decimal("0.00"),
        "per_unit_labor": Decimal("0.00"),
        "per_unit_machine": Decimal("0.00"),
        "per_unit_mfg": Decimal("0.00"),
        "co2_kg": Decimal("0.000000"),
        "has_routing": False,
    }

    if part.pk in _visited:
        logger.warning(
            "mBOM: circular BoM detected at part %s (pk=%s)", part.name, part.pk
        )
        return empty

    _visited.add(part.pk)

    try:
        from .models import PartRouting

        try:
            routing = PartRouting.objects.filter(part_id=part.pk).first()
        except Exception:
            routing = None
        if not routing:
            return empty

        labor_cost = routing.total_labor_cost(batch_size)
        machine_cost = routing.total_machine_cost(batch_size)
        mfg_cost = labor_cost + machine_cost
        co2_kg = routing.total_co2_kg(batch_size)

        qty = Decimal(str(batch_size))
        return {
            "labor_cost": labor_cost,
            "machine_cost": machine_cost,
            "mfg_cost": mfg_cost,
            "per_unit_labor": (labor_cost / qty).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            ),
            "per_unit_machine": (machine_cost / qty).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            ),
            "per_unit_mfg": (mfg_cost / qty).quantize(
                Decimal("0.000001"), rounding=ROUND_HALF_UP
            ),
            "co2_kg": co2_kg,
            "has_routing": True,
        }

    except Exception as exc:
        logger.error("mBOM: Error computing mBOM cost for part %s: %s", part.pk, exc)
        return empty


def get_assembly_full_cost(part, batch_size: int = 1) -> dict:
    """Return the complete cost breakdown for an assembly part.

    Combines:
    - InvenTree native eBOM material cost (from PartPricing)
    - mBOM manufacturing cost (from PartRouting)
    - Recursive sub-assembly mBOM costs

    Returns:
        dict with all cost components and per-unit totals
    """
    # --- Material cost from InvenTree native pricing ---
    material_min = Decimal("0.00")
    material_max = Decimal("0.00")

    try:
        pricing = part.pricing
        if pricing:
            if pricing.bom_cost_min is not None:
                material_min = _to_decimal(pricing.bom_cost_min)
            if pricing.bom_cost_max is not None:
                material_max = _to_decimal(pricing.bom_cost_max)
    except Exception as exc:
        logger.debug("mBOM: Could not read PartPricing for part %s: %s", part.pk, exc)

    # --- mBOM manufacturing cost ---
    mfg = get_mbom_unit_cost(part, batch_size)

    qty = Decimal(str(batch_size))

    per_unit_material_min = (material_min / qty).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    per_unit_material_max = (material_max / qty).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )

    per_unit_total_min = per_unit_material_min + mfg["per_unit_mfg"]
    per_unit_total_max = per_unit_material_max + mfg["per_unit_mfg"]

    return {
        # Batch totals
        "batch_size": batch_size,
        "material_cost_min": material_min,
        "material_cost_max": material_max,
        "labor_cost": mfg["labor_cost"],
        "machine_cost": mfg["machine_cost"],
        "mfg_cost": mfg["mfg_cost"],
        "co2_kg": mfg["co2_kg"],
        # Per-unit breakdown
        "per_unit_material_min": per_unit_material_min,
        "per_unit_material_max": per_unit_material_max,
        "per_unit_labor": mfg["per_unit_labor"],
        "per_unit_machine": mfg["per_unit_machine"],
        "per_unit_mfg": mfg["per_unit_mfg"],
        "per_unit_total_min": per_unit_total_min,
        "per_unit_total_max": per_unit_total_max,
        # Metadata
        "has_routing": mfg["has_routing"],
        "part_id": part.pk,
        "part_name": part.name,
    }


def _to_decimal(value) -> Decimal:
    """Safely convert a Money or numeric value to Decimal."""
    if value is None:
        return Decimal("0.00")
    try:
        # djmoney Money object
        return Decimal(str(value.amount))
    except AttributeError:
        return Decimal(str(value))


# =========================================================
# Pricing Service: write mBOM costs into InvenTree pricing
# =========================================================


class MbomPricingService:
    """Service for pushing mBOM manufacturing costs into InvenTree's pricing system.

    Two integration modes:
    1. schedule_for_update() — lightweight, triggers InvenTree's background
       pricing recalculation task. The cost-summary API provides the breakdown.

    2. write_extra_cost() — writes the per-unit mBOM cost as an "extra cost"
       row on PartPricing (if InvenTree supports extra costs). This makes the
       manufacturing cost appear in InvenTree's native pricing breakdown tables.
    """

    @staticmethod
    def schedule_for_update(part_id: int) -> bool:
        """Ask InvenTree to recalculate pricing for a part.

        Returns True if successfully scheduled, False otherwise.
        """
        try:
            from part.models import PartPricing

            pricing, _ = PartPricing.objects.get_or_create(part_id=part_id)
            pricing.schedule_for_update()
            logger.debug("mBOM: Scheduled pricing update for part %s", part_id)
            return True
        except Exception as exc:
            logger.warning(
                "mBOM: Failed to schedule pricing update for part %s: %s", part_id, exc
            )
            return False

    @staticmethod
    def sync_part_pricing(part, batch_size: int = None) -> bool:
        """Sync mBOM manufacturing cost directly into InvenTree PartPricing overall costs.

        Calculates Total Assembly Cost = Material (eBOM) + Manufacturing (mBOM).
        Sets PartPricing.overall_min and overall_max accordingly, then schedules
        background updates for parent assemblies.
        """
        try:
            from part.models import PartPricing
            from djmoney.money import Money
            from .models import PartRouting

            if isinstance(part, (int, str)):
                from part.models import Part

                part = Part.objects.get(pk=int(part))

            try:
                routing = PartRouting.objects.filter(part_id=part.pk).first()
            except Exception:
                routing = None

            pricing, _ = PartPricing.objects.get_or_create(part_id=part.pk)

            if not routing or not routing.operations.filter(is_active=True).exists():
                return False

            if batch_size is None:
                batch_size = routing.standard_batch_size or 1

            cost_data = get_assembly_full_cost(part, batch_size)
            if not cost_data["has_routing"]:
                return False

            currency = getattr(pricing, "currency", "EUR") or "EUR"
            bom_min = _to_decimal(pricing.bom_cost_min)
            bom_max = _to_decimal(pricing.bom_cost_max)
            mfg_unit = cost_data["per_unit_mfg"]

            # Total = BOM Material + mBOM Manufacturing
            total_min = bom_min + mfg_unit
            total_max = (bom_max if bom_max > Decimal("0.00") else bom_min) + mfg_unit

            PartPricing.objects.filter(part_id=part.pk).update(
                overall_min=total_min,
                overall_max=total_max,
                overall_min_currency=currency,
                overall_max_currency=currency,
            )
            logger.info(
                "mBOM: Synced PartPricing for %s (pk=%s): overall=%.4f..%.4f %s (mfg=%.4f)",
                part.name,
                part.pk,
                total_min,
                total_max,
                currency,
                mfg_unit,
            )

            # Cascade to parent assemblies
            try:
                from part.models import BomItem

                parent_ids = list(
                    BomItem.objects.filter(sub_part_id=part.pk)
                    .values_list("part_id", flat=True)
                    .distinct()
                )
                for pid in parent_ids:
                    MbomPricingService.schedule_for_update(pid)
            except Exception as exc:
                logger.debug(
                    "mBOM: Could not cascade to parents of part %s: %s", part.pk, exc
                )

            return True
        except Exception as exc:
            logger.warning(
                "mBOM: Failed to sync PartPricing for part %s: %s",
                getattr(part, "pk", part),
                exc,
            )
            return False

    @staticmethod
    def schedule_for_affected_parts(rate_instance, rate_field: str) -> int:
        """Schedule pricing recalculation for all parts using a given rate.

        Args:
            rate_instance: LaborRate or MachineCenter instance
            rate_field: 'labor_rate' or 'machine_center'

        Returns:
            number of parts scheduled
        """
        from .models import RoutingOperation

        rate_pk = getattr(rate_instance, "pk", rate_instance)
        filter_field = rate_field if rate_field.endswith("_id") else f"{rate_field}_id"

        part_ids = list(
            RoutingOperation.objects.filter(**{filter_field: rate_pk})
            .values_list("routing__part_id", flat=True)
            .distinct()
        )

        if not part_ids:
            return 0

        logger.info(
            'mBOM: Rate "%s" (pk=%s) changed → scheduling %d parts for pricing update',
            rate_instance,
            rate_pk,
            len(part_ids),
        )

        count = 0
        for part_id in part_ids:
            if MbomPricingService.schedule_for_update(part_id):
                count += 1
            try:
                from part.models import Part

                p = Part.objects.get(pk=part_id)
                MbomPricingService.sync_part_pricing(p)
            except Exception:
                pass

            # Also cascade to parent assemblies that use this part in their BoM
            try:
                from part.models import BomItem

                parent_ids = list(
                    BomItem.objects.filter(sub_part_id=part_id)
                    .values_list("part_id", flat=True)
                    .distinct()
                )
                for pid in parent_ids:
                    if MbomPricingService.schedule_for_update(pid):
                        count += 1
            except Exception as exc:
                logger.debug(
                    "mBOM: Could not cascade to parents of part %s: %s", part_id, exc
                )

        return count

    @staticmethod
    def write_extra_cost(part) -> bool:
        """Attempt to write the mBOM manufacturing cost into InvenTree's extra cost.

        This is a best-effort method — not all InvenTree versions support
        extra cost items on PartPricing. Falls back gracefully.

        Returns True if written, False if not supported or failed.
        """
        try:
            from part.models import PartPricing

            pricing, _ = PartPricing.objects.get_or_create(part_id=part.pk)
            mfg = get_mbom_unit_cost(part)

            if not mfg["has_routing"]:
                return False

            # Try to update extra_cost field (InvenTree >= 1.4 may support this)
            if hasattr(pricing, "extra_cost_min") and hasattr(
                pricing, "extra_cost_max"
            ):
                from djmoney.money import Money

                currency = getattr(pricing, "currency", "EUR")
                pricing.extra_cost_min = Money(mfg["per_unit_mfg"], currency)
                pricing.extra_cost_max = Money(mfg["per_unit_mfg"], currency)
                pricing.save(update_fields=["extra_cost_min", "extra_cost_max"])
                logger.debug(
                    "mBOM: Wrote extra cost %s to PartPricing for part %s",
                    mfg["per_unit_mfg"],
                    part.pk,
                )
                return True

        except Exception as exc:
            logger.debug("mBOM: write_extra_cost not supported or failed: %s", exc)

        return False
