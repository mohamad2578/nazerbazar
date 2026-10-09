from django.shortcuts import get_object_or_404
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.permissions import role_permission

from .models import NewsItem


class NewsSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")
    # فیلد قابل‌نوشتن: آپلود عکس از پنل ذخیره می‌شود و آدرس مطلق (با schema درست) برمی‌گردد
    image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = NewsItem
        fields = ["id", "title", "body", "image", "is_published", "published_at", "created_by_name"]


class NewsAdminViewSet(viewsets.ModelViewSet):
    """مدیریت اخبار در پنل؛ مدیر کل و اداره صمت ثبت، ویرایش و حذف می‌کنند."""

    queryset = NewsItem.objects.select_related("created_by")
    serializer_class = NewsSerializer
    pagination_class = None
    search_fields = ["title", "body"]

    def get_permissions(self):
        return [role_permission("samt")()]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_news(request):
    qs = NewsItem.objects.filter(is_published=True)[:60]
    return Response(NewsSerializer(qs, many=True, context={"request": request}).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def public_news_detail(request, pk):
    item = get_object_or_404(NewsItem, pk=pk, is_published=True)
    return Response(NewsSerializer(item, context={"request": request}).data)
