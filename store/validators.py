"""Application-specific security validators."""

import re

from django.core.exceptions import ValidationError


class StrongPasswordValidator:
    """Require a password with mixed character classes."""

    def validate(self, password, user=None):
        checks = [
            (r"[a-z]", "حرف إنجليزي صغير واحد على الأقل."),
            (r"[A-Z]", "حرف إنجليزي كبير واحد على الأقل."),
            (r"\d", "رقم واحد على الأقل."),
            (r"[^A-Za-z0-9]", "رمز خاص واحد على الأقل."),
        ]
        missing = [message for pattern, message in checks if not re.search(pattern, password)]
        if missing:
            raise ValidationError("كلمة المرور يجب أن تحتوي على: " + "، ".join(missing))

    def get_help_text(self):
        return "استخدم 12 حرفًا أو أكثر مع أحرف كبيرة وصغيرة وأرقام ورمز خاص."
