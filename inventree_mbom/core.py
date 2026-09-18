"""Core plugin definition for inventree-mbom.

Provides a Manufacturing BOM & Routings tab on assembly parts,
with hierarchical process steps, central labor/machine rates,
and pricing integration via InvenTree's signal system.
"""

from django.utils.translation import gettext_lazy as _

from plugin import InvenTreePlugin
from plugin.mixins import AppMixin, SettingsMixin, UrlsMixin, UserInterfaceMixin

from . import PLUGIN_VERSION, PLUGIN_SLUG


class ManufacturingBOMPlugin(
    AppMixin, SettingsMixin, UrlsMixin, UserInterfaceMixin, InvenTreePlugin
):
    """ManufacturingBOMPlugin - Manufacturing BOM & Routings for InvenTree.

    Key capabilities:
    - Hierarchical operations with parent/child steps (Op 10 -> 10.1, 10.2 ...)
    - Central LaborRate and MachineCenter tariff catalog
    - Reusable ProcessTemplates that can be applied to any assembly
    - Setup Time (fixed) + Run Time (per-unit) tracked separately
    - CO2 emission factor tracking per machine center
    - Pricing bridge: manufacturing costs roll up into InvenTree PartPricing
    - Native UI panel on assembly parts (no standalone SPA required)
    - Parent-assembly cascaded cost recalculation on rate changes
    """

    # Plugin metadata
    TITLE = "Manufacturing BOM & Routings"
    NAME = "ManufacturingBOMPlugin"
    DESCRIPTION = (
        "Adds hierarchical process routing (mBOM) with labor/machine rates "
        "and full cost roll-up into InvenTree assembly pricing."
    )
    VERSION = PLUGIN_VERSION
    SLUG = PLUGIN_SLUG

    # Attribution
    AUTHOR = "Tim"
    WEBSITE = "https://github.com/yourusername/inventree-mbom"
    LICENSE = "MIT"

    # Minimum InvenTree version required
    MIN_VERSION = "1.3.1"

    # ------------------------------------------------------------------
    # Plugin settings (SettingsMixin)
    # ------------------------------------------------------------------
    SETTINGS = {
        "DEFAULT_CURRENCY": {
            "name": _("Default Currency"),
            "description": _("Currency used for manufacturing cost calculations"),
            "default": "EUR",
        },
        "COST_DECIMAL_PLACES": {
            "name": _("Cost Decimal Places"),
            "description": _("Number of decimal places for cost display"),
            "validator": int,
            "default": 4,
        },
        "AUTO_RECALCULATE": {
            "name": _("Auto-Recalculate on Rate Change"),
            "description": _(
                "Automatically recalculate part pricing when a labor or machine rate is updated"
            ),
            "validator": bool,
            "default": True,
        },
        "INCLUDE_SETUP_IN_UNIT_COST": {
            "name": _("Include Setup Cost in Unit Cost"),
            "description": _(
                "If enabled, setup (fixed) costs are amortised into the per-unit cost "
                "using the standard batch size defined on the routing."
            ),
            "validator": bool,
            "default": True,
        },
    }

    # ------------------------------------------------------------------
    # URL configuration (UrlsMixin)
    # ------------------------------------------------------------------
    def setup_urls(self):
        """Configure custom REST API URL endpoints for this plugin."""
        from .views import construct_urls
        return construct_urls()

    # ------------------------------------------------------------------
    # UI panel / extension (UserInterfaceMixin)
    # ------------------------------------------------------------------
    def get_ui_panels(self, request, context=None, **kwargs):
        """Return UI panels to inject into InvenTree pages.

        Registers panels on assembly part detail pages:
        1. 'Manufacturing Routing (mBOM)' - the full routing management tab
        2. 'Manufacturing Costs' - compact pricing breakdown card
        """
        panels = []
        target_model = context.get("model", "") if context else ""
        target_id = context.get("id", None) if context else None

        if target_model == "part" and target_id:
            try:
                from part.models import Part
                part = Part.objects.get(pk=target_id)
                if part.assembly:
                    plugin_slug = PLUGIN_SLUG
                    # Main routing management tab
                    panels.append({
                        "name": "mbom_routing",
                        "label": _("Manufacturing Routing (mBOM)"),
                        "icon": "fas fa-cogs",
                        "content_url": f"/plugin/{plugin_slug}/panel/part/{target_id}/",
                    })
                    # Cost breakdown card
                    panels.append({
                        "name": "mbom_pricing",
                        "label": _("Manufacturing Costs"),
                        "icon": "fas fa-calculator",
                        "content_url": f"/plugin/{plugin_slug}/pricing-panel/{target_id}/",
                    })
            except Exception:
                pass

        return panels
