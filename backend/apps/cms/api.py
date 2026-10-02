from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.permissions import role_permission

from .models import Slide


class SlideSerializer(serializers.ModelSerializer):
    class Meta:
        model = Slide
        fields = ["id", "title", "subtitle", "image", "link_url", "link_label", "order", "is_active"]


class SlideViewSet(viewsets.ModelViewSet):
    """مدیریت اسلایدهای صفحه اصلی؛ فقط مدیر کل می‌تواند اضافه/ویرایش/حذف کند."""

    queryset = Slide.objects.all()
    serializer_class = SlideSerializer
    pagination_class = None

    def get_permissions(self):
        return [AllowAny()] if self.request.method == "GET" else [role_permission("admin")()]


@api_view(["GET"])
@permission_classes([AllowAny])
def public_slides(request):
    """اسلایدهای فعال صفحه اصلی سایت عمومی، به ترتیب نمایش."""
    qs = Slide.objects.filter(is_active=True).order_by("order", "-created_at")
    return Response(SlideSerializer(qs, many=True, context={"request": request}).data)
