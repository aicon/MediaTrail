from django.utils import translation

from users.languages import LANGUAGE_AUTO, resolve_interface_language


class UserLanguageMiddleware:
    """Activate the signed-in user's language. Auto follows the browser."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if getattr(user, "is_authenticated", False):
            selected = getattr(user, "language", "") or LANGUAGE_AUTO
        else:
            selected = LANGUAGE_AUTO
        language = resolve_interface_language(request, selected)
        translation.activate(language)
        request.LANGUAGE_CODE = language
        try:
            return self.get_response(request)
        finally:
            translation.deactivate()
