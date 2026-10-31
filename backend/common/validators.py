from django.core.exceptions import ValidationError
from phonenumber_field.phonenumber import PhoneNumber


def validate_phone_number(value):
    try:
        phone = PhoneNumber.from_string(
            str(value),
            region="IN",
        )

        if not phone.is_valid():
            raise ValidationError("Enter a valid phone number.")

    except Exception as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("Enter a valid phone number.")