"""Django signals for the inventree-mbom plugin.

Pricing Bridge:
    When a LaborRate or MachineCenter hourly_rate changes, we need to
    invalidate and recalculate InvenTree PartPricing for all affected parts.

    Strategy: post_save signals on LaborRate/MachineCenter trigger
    PartPricing.schedule_for_update() on all parts with routings
    that reference the changed rate.

    This is non-invasive - no InvenTree core files are modified.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger("inventree_mbom")


@receiver(post_save, sender="inventree_mbom.LaborRate")
def on_labor_rate_saved(sender, instance, **kwargs):
    """Trigger pricing recalculation for all parts using this labor rate."""
    _schedule_pricing_update_for_rate(instance, "labor_rate")


@receiver(post_save, sender="inventree_mbom.MachineCenter")
def on_machine_center_saved(sender, instance, **kwargs):
    """Trigger pricing recalculation for all parts using this machine center."""
    _schedule_pricing_update_for_rate(instance, "machine_center")


def _schedule_pricing_update_for_rate(rate_instance, rate_field: str):
    """Schedule pricing recalculation for all parts with routing operations
    referencing the given rate instance.
    """
    try:
        from plugin.registry import registry
        from . import PLUGIN_SLUG

        plugin = registry.get_plugin(PLUGIN_SLUG)
        if not plugin:
            return

        if not plugin.get_setting("AUTO_RECALCULATE"):
            return

        from .models import RoutingOperation

        filter_kwargs = {rate_field: rate_instance}
        affected_routings = set(
            RoutingOperation.objects.filter(**filter_kwargs)
            .values_list("routing__part_id", flat=True)
            .distinct()
        )

        if not affected_routings:
            return

        logger.info(
            "inventree-mbom: Rate '%s' (pk=%s) changed; scheduling pricing "
            "recalculation for %d parts.",
            rate_instance,
            rate_instance.pk,
            len(affected_routings),
        )

        try:
            from part.models import PartPricing

            for part_id in affected_routings:
                try:
                    pricing = PartPricing.objects.get(part_id=part_id)
                    pricing.schedule_for_update()
                except PartPricing.DoesNotExist:
                    pass
                except Exception as exc:
                    logger.warning(
                        "inventree-mbom: Failed to schedule pricing update "
                        "for part %s: %s",
                        part_id,
                        exc,
                    )
        except ImportError:
            logger.warning(
                "inventree-mbom: PartPricing model not available; "
                "skipping auto-recalculation."
            )

    except Exception as exc:
        logger.error(
            "inventree-mbom: Error in pricing update signal handler: %s", exc
        )
