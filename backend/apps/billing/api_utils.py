"""
API response and error helpers for billing.
"""
from functools import wraps
from typing import Any, Dict, Optional

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from .models import IllegalStatusTransitionError, Invoice


def success_response(
    data: Any = None,
    message: str = "Success",
    status_code: int = status.HTTP_200_OK,
) -> Response:
    """Return a standard success response envelope."""
    return Response(
        {
            "success": True,
            "message": message,
            "data": data,
        },
        status=status_code,
    )


def error_response(
    message: str = "Request failed",
    errors: Optional[Dict[str, Any]] = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    """Return a standard error response envelope."""
    return Response(
        {
            "success": False,
            "message": message,
            "errors": errors if errors is not None else {},
        },
        status=status_code,
    )


def validation_error_to_response(
    exc: DjangoValidationError,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    """
    Convert a Django ValidationError into a standard error response envelope.
    Handles both dict-style (exc.message_dict) and plain-string (exc.messages) shapes.
    """
    if hasattr(exc, "message_dict"):
        errors = exc.message_dict
        msg = "; ".join(f"{k}: {', '.join(v)}" for k, v in errors.items())
    elif hasattr(exc, "messages"):
        errors = {"non_field_errors": list(exc.messages)}
        msg = "; ".join(exc.messages)
    else:
        errors = {"non_field_errors": [str(exc)]}
        msg = str(exc)

    return error_response(
        message=msg,
        errors=errors,
        status_code=status_code,
    )


def handle_billing_errors(func):
    """
    Decorator for billing view action methods:
    - IllegalStatusTransitionError -> 409 Conflict (checked first as it subclasses ValidationError)
    - DjangoValidationError -> 400 Bad Request
    - DRFValidationError -> 400 Bad Request
    - Invoice.DoesNotExist / Http404 -> 404 Not Found
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except IllegalStatusTransitionError as exc:
            return validation_error_to_response(exc, status_code=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            return validation_error_to_response(exc, status_code=status.HTTP_400_BAD_REQUEST)
        except DRFValidationError as exc:
            detail = exc.detail
            if isinstance(detail, dict):
                errs = detail
                msg = str(detail)
            elif isinstance(detail, list):
                errs = {"non_field_errors": [str(d) for d in detail]}
                msg = "; ".join(str(d) for d in detail)
            else:
                errs = {"detail": str(detail)}
                msg = str(detail)
            return error_response(message=msg, errors=errs, status_code=status.HTTP_400_BAD_REQUEST)
        except (Invoice.DoesNotExist, Http404) as exc:
            msg = str(exc) or "Invoice not found."
            return error_response(
                message=msg,
                errors={"detail": msg},
                status_code=status.HTTP_404_NOT_FOUND,
            )

    return wrapper

