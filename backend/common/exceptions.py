from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return response

    if isinstance(response.data, dict):
        errors = response.data
    else:
        errors = {"detail": response.data}

    response.data = {
        "success": False,
        "message": "Request failed",
        "errors": errors,
    }

    return response