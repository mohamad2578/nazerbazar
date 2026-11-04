from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser

# تنها نشانی‌هایی که بدنه‌ی JSONِ «فهرست» می‌پذیرند؛ بقیه فقط شیء JSON ({...}) می‌گیرند
LIST_BODY_PATHS = ("/api/store/offers/",)


class StrictJSONParser(JSONParser):
    """بدنه JSON باید شیء باشد؛ رشته/عدد/فهرست (که منطق ما با `.get` انتظارش را ندارد) خطای ۴۰۰ می‌دهد نه ۵۰۰."""

    def parse(self, stream, media_type=None, parser_context=None):
        data = super().parse(stream, media_type, parser_context)
        if isinstance(data, dict):
            return data
        request = (parser_context or {}).get("request")
        path = getattr(request, "path", "")
        if isinstance(data, list) and path.startswith(LIST_BODY_PATHS):
            return data
        raise ParseError("بدنه درخواست باید یک شیء JSON باشد.")
