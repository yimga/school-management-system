"""
Photo upload by token: capture on another device (e.g. phone) and attach to registration or profile.
"""
import logging
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie

from apps.platform_runtime.helpers import get_effective_site_settings
from .models import PhotoUploadToken

try:
    from django_ratelimit.decorators import ratelimit
except ImportError:
    def ratelimit(*args, **kwargs):
        def dec(f):
            return f
        return dec

logger = logging.getLogger(__name__)

TOKEN_EXPIRY_HOURS = 48


def _token_expired(token_obj):
    if not token_obj.created_at:
        return False
    delta = timezone.now() - token_obj.created_at
    return delta.total_seconds() > (TOKEN_EXPIRY_HOURS * 3600)


def _photo_upload_remote_enabled(request=None):
    site = get_effective_site_settings(request=request)
    return bool((site.portal_features or {}).get("photo_upload_remote", True))


@ratelimit(key="ip", rate="20/h", method="GET", block=True)
@require_GET
def photo_upload_generate(request):
    if not _photo_upload_remote_enabled(request):
        raise Http404("Photo upload from another device is disabled.")
    purpose = request.GET.get("purpose", PhotoUploadToken.Purpose.REGISTRATION)
    if purpose not in (PhotoUploadToken.Purpose.REGISTRATION, PhotoUploadToken.Purpose.PROFILE_UPDATE):
        purpose = PhotoUploadToken.Purpose.REGISTRATION
    token_obj = PhotoUploadToken.objects.create(purpose=purpose)
    base_url = request.build_absolute_uri("/").rstrip("/")
    upload_path = f"/portal/photo-upload/{token_obj.token}/"
    full_url = base_url + upload_path
    return JsonResponse({
        "token": str(token_obj.token),
        "upload_url": upload_path,
        "full_url": full_url,
    })


@login_required
@require_POST
def photo_upload_generate_for_profile(request):
    if not _photo_upload_remote_enabled(request):
        raise Http404("Photo upload from another device is disabled.")
    student_id = request.POST.get("student_id")
    teacher_id = request.POST.get("teacher_id")
    if not student_id and not teacher_id:
        return JsonResponse({"error": "Provide student_id or teacher_id"}, status=400)
    if student_id and not request.user.has_perm("people.view_studentprofile"):
        raise PermissionDenied
    if teacher_id and not request.user.has_perm("people.view_teacherprofile"):
        raise PermissionDenied
    student = None
    teacher = None
    if student_id:
        from apps.people.models import StudentProfile
        student = get_object_or_404(StudentProfile, id=student_id)
    if teacher_id:
        from apps.people.models import TeacherProfile
        teacher = get_object_or_404(TeacherProfile, id=teacher_id)
    token_obj = PhotoUploadToken.objects.create(
        purpose=PhotoUploadToken.Purpose.PROFILE_UPDATE,
        student=student,
        teacher=teacher,
    )
    full_url = request.build_absolute_uri(f"/portal/photo-upload/{token_obj.token}/")
    return JsonResponse({
        "token": str(token_obj.token),
        "full_url": full_url,
        "upload_url": f"/portal/photo-upload/{token_obj.token}/",
    })


@login_required
@require_GET
def photo_upload_send_link_page(request, student_id=None, teacher_id=None):
    if not _photo_upload_remote_enabled(request):
        return render(request, "portal/photo_upload_disabled.html", status=404)
    if student_id and not request.user.has_perm("people.view_studentprofile"):
        raise PermissionDenied
    if teacher_id and not request.user.has_perm("people.view_teacherprofile"):
        raise PermissionDenied
    student = None
    teacher = None
    if student_id:
        from apps.people.models import StudentProfile
        student = get_object_or_404(StudentProfile, id=student_id)
    if teacher_id:
        from apps.people.models import TeacherProfile
        teacher = get_object_or_404(TeacherProfile, id=teacher_id)
    if not student and not teacher:
        raise Http404("Student or teacher required")
    token_obj = PhotoUploadToken.objects.create(
        purpose=PhotoUploadToken.Purpose.PROFILE_UPDATE,
        student=student,
        teacher=teacher,
    )
    full_url = request.build_absolute_uri(f"/portal/photo-upload/{token_obj.token}/")
    qr_url = request.build_absolute_uri(f"/portal/photo-upload/{token_obj.token}/qr/")
    if student:
        name = student.get_full_name()
    elif teacher and getattr(teacher, "user", None):
        name = teacher.user.get_full_name() or "Teacher"
    elif teacher:
        name = "Teacher"
    else:
        name = "Profile"
    return render(request, "portal/photo_upload_send_link.html", {
        "token": token_obj.token,
        "full_url": full_url,
        "qr_url": qr_url,
        "profile_name": name,
        "is_student": bool(student),
    })


@require_GET
@ensure_csrf_cookie
def photo_upload_phone_page(request, token):
    if not _photo_upload_remote_enabled(request):
        return render(request, "portal/photo_upload_disabled.html", status=404)
    token_obj = get_object_or_404(PhotoUploadToken, token=token)
    if _token_expired(token_obj):
        return render(request, "portal/photo_upload_expired.html", {"token": token})
    full_url = request.build_absolute_uri(request.path)
    return render(request, "portal/photo_upload_phone.html", {
        "token": token,
        "full_url": full_url,
        "upload_endpoint": request.build_absolute_uri(f"/portal/photo-upload/{token}/upload/"),
    })


@ratelimit(key="ip", rate="30/h", method="POST", block=True)
@require_POST
def photo_upload_upload(request, token):
    if not _photo_upload_remote_enabled(request):
        raise Http404("Photo upload from another device is disabled.")
    token_obj = get_object_or_404(PhotoUploadToken, token=token)
    if _token_expired(token_obj):
        return JsonResponse({"error": "Link expired"}, status=410)

    file_obj = None
    if request.FILES.get("photo"):
        file_obj = request.FILES["photo"]
    elif request.FILES.get("profile_photo"):
        file_obj = request.FILES["profile_photo"]
    elif request.content_type and "application/json" in request.content_type:
        import base64
        import json
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        b64 = data.get("photo_base64") or data.get("profile_photo_base64")
        if b64:
            try:
                if "," in b64:
                    b64 = b64.split(",", 1)[1]
                raw = base64.b64decode(b64)
                from django.core.files.base import ContentFile
                file_obj = ContentFile(raw, name="photo.jpg")
            except Exception as e:
                logger.warning("Photo upload base64 decode failed: %s", e)
                return JsonResponse({"error": "Invalid image data"}, status=400)

    if not file_obj:
        return JsonResponse({"error": "No photo provided (use 'photo' or 'profile_photo' file, or photo_base64 in JSON)"}, status=400)

    if hasattr(file_obj, "content_type") and file_obj.content_type:
        if not file_obj.content_type.startswith("image/"):
            return JsonResponse({"error": "File must be an image"}, status=400)
    if hasattr(file_obj, "size") and file_obj.size and file_obj.size > 10 * 1024 * 1024:
        return JsonResponse({"error": "Image too large (max 10MB)"}, status=400)

    token_obj.photo = file_obj
    token_obj.save(update_fields=["photo"])

    if token_obj.purpose == PhotoUploadToken.Purpose.PROFILE_UPDATE:
        from django.core.files.base import ContentFile
        name = getattr(token_obj.photo, "name", None) or "photo.jpg"
        if "/" in name:
            name = name.split("/")[-1]
        content = ContentFile(token_obj.photo.read())
        if token_obj.student_id:
            token_obj.student.profile_photo.save(name, content, save=True)
        elif token_obj.teacher_id:
            token_obj.teacher.profile_photo.save(name, content, save=True)
        token_obj.delete()

    return JsonResponse({"ok": True, "message": "Photo received"})


@require_GET
def photo_upload_status(request, token):
    if not _photo_upload_remote_enabled():
        raise Http404("Photo upload from another device is disabled.")
    token_obj = get_object_or_404(PhotoUploadToken, token=token)
    if _token_expired(token_obj):
        return JsonResponse({"has_photo": False, "expired": True})
    has_photo = bool(token_obj.photo)
    thumbnail_url = None
    if has_photo and token_obj.photo:
        thumbnail_url = request.build_absolute_uri(token_obj.photo.url)
    return JsonResponse({
        "has_photo": has_photo,
        "thumbnail_url": thumbnail_url,
        "expired": False,
    })


@require_GET
def photo_upload_qr(request, token):
    if not _photo_upload_remote_enabled():
        raise Http404("Photo upload from another device is disabled.")
    token_obj = get_object_or_404(PhotoUploadToken, token=token)
    full_url = request.build_absolute_uri(f"/portal/photo-upload/{token}/")
    try:
        import qrcode
        import qrcode.image.pil
        img = qrcode.make(full_url, image_factory=qrcode.image.pil.PilImage)
        response = HttpResponse(content_type="image/png")
        img.save(response, "PNG")
        return response
    except ImportError:
        return HttpResponse(
            f"<html><body><p>QR not available. Use this link:</p><a href='{full_url}'>{full_url}</a></body></html>",
            content_type="text/html",
        )
