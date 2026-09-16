from company_clients import InventoryClient, Database, EventBus, Cache, Storage
from company_audit import AuditClient  # implementation intentionally unavailable


def register(config):
    inventory = InventoryClient(config['INVENTORY_ENDPOINT'])
    audit = AuditClient(config['AUDIT_DESTINATION'])  # registration only
    return inventory, audit


def checkout(inventory, database: Database, events: EventBus, cache: Cache, storage: Storage):
    inventory.reserve('sku')
    database.execute('INSERT INTO orders VALUES (?)', ['order'])
    events.publish('orders.created', {'id': 'order'})
    cache.get('catalog')
    storage.put('receipts/order', b'receipt')
