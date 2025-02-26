from onepassword import Client, ItemCreateParams, ItemField, ItemFieldType, ItemCategory, ItemSection, Item
from onepassword import ItemShareParams, ItemShareDuration, ValidRecipient
from .misc import load_config
import logging
import asyncio

logger = logging.getLogger(__name__)

async def get_client():
    op_config = load_config().get("1password", {})
    if not op_config.get('token'):
        raise Exception("1Password token not found in config")

    return await Client.authenticate(auth=op_config['token'], integration_name="data-vault", integration_version="v1.0.0")

def save_item(vault_name: str, title, fields, notes=None, category=ItemCategory.APICREDENTIALS):
    return asyncio.run(save_item_async(vault_name, title, fields, notes, category))

async def save_item_async(vault_name: str, title, fields, notes=None, category=ItemCategory.APICREDENTIALS):
    client = await get_client()
    vault_id = None
    vaults = await client.vaults.list_all()
    async for vault in vaults:
        if vault.title == vault_name:
            vault_id = vault.id
            break
    else:
        raise Exception(f"Vault {vault} not found")
    
    field_objs = []
    sections = []
    for field in fields:
        if field.get('concealed', False):
            field['field_type'] = ItemFieldType.CONCEALED
        else:
            field['field_type'] = ItemFieldType.TEXT
        field['id'] = field['title'].lower().replace(' ', '_')
        field_objs.append(ItemField(**field))
        if section_id := field.get('section_id'):
            if section_id not in sections:
                sections.append(section_id)
    sections = [ItemSection(id=section, title=section) for section in sections]
    
    # Create item parameters with sections
    create_params = ItemCreateParams(
        title=title,
        category=category,
        vault_id=vault_id,
        fields=field_objs,
        sections=sections,
    )
    
    if notes:
        create_params.notes = notes
    
    item = await client.items.create(create_params)
    logger.info(f"Stored credentials in 1Password vault '{vault}' with title '{title}'")
    return item

def share_item(
        item: Item, 
        recipients: list[str] | None = None, 
        expire_after: ItemShareDuration | None = ItemShareDuration.SEVENDAYS, 
        one_time_only: bool = False
    ):
    return asyncio.run(share_item_async(item, recipients, expire_after, one_time_only))

async def share_item_async(
        item: Item,
        recipients: list[str] | None, 
        expire_after: ItemShareDuration | None,
        one_time_only: bool,
    ):
    client = await get_client()
    policy = await client.items.shares.get_account_policy(item.vault_id, item.id)
    valid_recipients = await client.items.shares.validate_recipients(policy, recipients)
    share_params = ItemShareParams(
        recipients=valid_recipients,
        expire_after=expire_after,
        one_time_only=one_time_only
    )
    share_link = await client.items.shares.create(item, policy, share_params)
    logger.info(f"Created share link for '{item.title}'")
    return share_link

