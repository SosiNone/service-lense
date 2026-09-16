SERVICE_ORIGIN = 'https://inventory.internal'


def register_routes(app):
    app.post('/reserve', reserve)


def reserve(request):
    return {'reserved': True}
