import os
import httpx
from client import get_order

get_order(os.getenv("ORDERS_API") + "orders/42")

with httpx.Client(base_url=os.getenv("PAYMENTS_API")) as payments:
    payments.post("/charges")


def notify_customer(customer_id):
    import requests
    requests.post("https://notifications.example/customers/" + customer_id)


def call_dynamic_partner(url):
    import requests
    requests.get(url)
