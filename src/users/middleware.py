from django.utils import translation

from users.languages import LANGUAGE_CODES


class UserLanguageMiddleware:
    """Activate the language saved in the signed-in user's preferences."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = "en"
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            selected = getattr(user, "language", "") or "en"
            if selected in LANGUAGE_CODES:
                language = selected
        translation.activate(language)
        request.LANGUAGE_CODE = language
        try:
            return self.get_response(request)
        finally:
            translation.deactivate()
