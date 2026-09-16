class InventoryClient:
    def __init__(self, endpoint):
        self.endpoint = endpoint

    def reserve(self, sku):
        return self.transport.post(self.endpoint + '/reserve', json={'sku': sku})


class Database:
    def execute(self, statement, params):
        return self.driver.execute(statement, params)


class EventBus:
    def publish(self, topic, event):
        return self.broker.publish(topic, event)


class Cache:
    def get(self, key):
        return self.redis.get(key)


class Storage:
    def put(self, key, body):
        return self.bucket.put_object(Key=key, Body=body)
