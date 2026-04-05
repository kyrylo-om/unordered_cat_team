import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import NetworkDefinition
from .store_account_service import StoreAccountService
from .json_parser import parse_network_json

logger = logging.getLogger(__name__)


@receiver(post_save, sender=NetworkDefinition)
def on_network_definition_save(sender, instance, created, **kwargs):
    """
    Signal handler triggered when a NetworkDefinition is saved.

    Parses the JSON file and creates warehouse/shop accounts with shared password.

    Args:
            sender: The NetworkDefinition model class
            instance: The NetworkDefinition instance being saved
            created: Boolean indicating if this is a new instance
            **kwargs: Additional arguments from the signal
    """
    # Refresh instance from database
    instance.refresh_from_db()

    # Skip if not active
    if not instance.is_active:
        logger.debug(f"Skipping account creation for {instance.name}: not active")
        return

    try:
        logger.info(f"Parsing network definition: {instance.name}")

        # Parse the JSON file
        parsed_definition = parse_network_json(instance.json_file.path)
        instance.definition = parsed_definition
        instance.parse_error = ""

        # Create accounts from warehouses and shops
        credentials = StoreAccountService.create_accounts_from_json(
            instance, parsed_definition
        )

        logger.info(
            f"Successfully created {len(credentials)} accounts for network: {instance.name}"
        )

        # Update the database with parsed definition
        type(instance).objects.filter(pk=instance.pk).update(
            definition=parsed_definition,
            parse_error=""
        )

    except Exception as e:
        logger.error(f"Failed to parse network definition {instance.name}: {e}", exc_info=True)
        # Update the parse_error field to inform admin of the issue
        instance.parse_error = f"Parse error: {str(e)}"
        type(instance).objects.filter(pk=instance.pk).update(
            parse_error=instance.parse_error
        )

