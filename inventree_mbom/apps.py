"""Django app configuration for the inventree_mbom plugin."""

from django.apps import AppConfig


class ManufacturingBOMConfig(AppConfig):
    """App configuration for the Manufacturing BOM & Routings plugin."""

    name = "inventree_mbom"
    label = "inventree_mbom"
    verbose_name = "Manufacturing BOM & Routings"

    def ready(self):
        """Perform startup tasks when the app is ready."""
        import inventree_mbom.signals  # noqa: F401
