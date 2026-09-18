"""Django signal handlers for the inventree-mbom plugin.

Pricing Bridge:
    When a LaborRate or MachineCenter rate is changed, we need all affected
    assembly parts (and their parents) to have their pricing recalculated.

    Uses MbomPricingService.schedule_for_affected_parts() which:
    1. Finds all RoutingOperations referencing the changed rate
    2. Calls PartPricing.schedule_for_update() on each affected part
    3. Cascades UP to parent assemblies via BomItem relationships
       (so a sub-assembly rate change bubbles up to top-level assemblies)

    Also hooks RoutingOperation.save/delete to keep individual part pricing fresh.
"""

import logging
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger('inventree_mbom')


# =========================================================
# Rate change signals → cascade pricing update
# =========================================================

@receiver(post_save, sender='inventree_mbom.LaborRate')
def on_labor_rate_saved(sender, instance, created, **kwargs):
    """Recalculate pricing for all parts using this labor rate."""
    if created:
        return  # New rate has no operations yet

    _check_and_schedule(instance, 'labor_rate')


@receiver(post_save, sender='inventree_mbom.MachineCenter')
def on_machine_center_saved(sender, instance, created, **kwargs):
    """Recalculate pricing for all parts using this machine center."""
    if created:
        return

    _check_and_schedule(instance, 'machine_center')


def _check_and_schedule(rate_instance, rate_field: str):
    """Check plugin setting and schedule pricing updates if auto-recalc is on."""
    try:
        from plugin.registry import registry
        from . import PLUGIN_SLUG

        plugin = registry.get_plugin(PLUGIN_SLUG)
        if plugin and not plugin.get_setting('AUTO_RECALCULATE'):
            logger.debug('mBOM: AUTO_RECALCULATE is off; skipping update for %s', rate_instance)
            return

    except Exception:
        pass  # Plugin not loaded yet; proceed anyway

    try:
        from .pricing import MbomPricingService
        count = MbomPricingService.schedule_for_affected_parts(rate_instance, rate_field)
        if count:
            logger.info(
                'mBOM: %s "%s" changed → %d part pricing schedules updated',
                rate_field, rate_instance, count
            )
    except Exception as exc:
        logger.error('mBOM: Error scheduling pricing updates: %s', exc, exc_info=True)


# =========================================================
# RoutingOperation save/delete → update this part's pricing
# =========================================================

@receiver(post_save, sender='inventree_mbom.RoutingOperation')
def on_routing_operation_saved(sender, instance, **kwargs):
    """Invalidate pricing when an operation is added or updated."""
    _schedule_routing_part(instance)


@receiver(post_delete, sender='inventree_mbom.RoutingOperation')
def on_routing_operation_deleted(sender, instance, **kwargs):
    """Invalidate pricing when an operation is removed."""
    _schedule_routing_part(instance)


def _schedule_routing_part(operation):
    """Schedule pricing update for the part that owns this operation."""
    try:
        part_id = operation.routing.part_id
        from .pricing import MbomPricingService
        MbomPricingService.schedule_for_update(part_id)

        # Also cascade to parent assemblies
        try:
            from part.models import BomItem
            parent_ids = list(
                BomItem.objects
                .filter(sub_part_id=part_id)
                .values_list('part_id', flat=True)
                .distinct()
            )
            for pid in parent_ids:
                MbomPricingService.schedule_for_update(pid)
        except Exception:
            pass

    except Exception as exc:
        logger.debug('mBOM: Could not schedule part pricing update: %s', exc)


# =========================================================
# PartRouting save → try to write extra cost immediately
# =========================================================

@receiver(post_save, sender='inventree_mbom.PartRouting')
def on_part_routing_saved(sender, instance, **kwargs):
    """When a routing is saved, attempt to push costs to InvenTree pricing."""
    try:
        from .pricing import MbomPricingService
        MbomPricingService.schedule_for_update(instance.part_id)
        # Best-effort extra cost write
        MbomPricingService.write_extra_cost(instance.part)
    except Exception as exc:
        logger.debug('mBOM: post_save on PartRouting pricing update: %s', exc)
