from typing import List

from django.contrib.auth.models import User
from ninja import NinjaAPI
from ninja.errors import HttpError

from ninja_simple_jwt.auth.views.api import mobile_auth_router
from ninja_simple_jwt.auth.ninja_auth import HttpJwtAuth

from courses.models import Course, CourseMember, CourseContent, Comment
from core.schemas import (
    UserOut,
    UserUpdate,
    Register,
    CourseIn,
    CourseOut,
    DetailCourseOut,
    CourseMemberOut,
    CommentIn,
    CommentUpdate,
    ProgressIn,
    MessageOut,
)


apiv1 = NinjaAPI(
    title="Simple LMS API",
    version="1.0.0",
)

apiv1.add_router("/auth/", mobile_auth_router)

apiAuth = HttpJwtAuth()


# ================= AUTHENTICATION =================

@apiv1.post(
    "/register/",
    response={201: UserOut},
    tags=["Authentication"],
    summary="Register User"
)
def register(request, data: Register):
    if User.objects.filter(username=data.username).exists():
        raise HttpError(400, "Username sudah digunakan")

    if User.objects.filter(email=data.email).exists():
        raise HttpError(400, "Email sudah digunakan")

    user = User.objects.create_user(**data.dict())
    return 201, user


@apiv1.get(
    "/profile/",
    auth=apiAuth,
    response=UserOut,
    tags=["Authentication"],
    summary="Profile User"
)
def profile(request):
    return request.user


@apiv1.put(
    "/profile/",
    auth=apiAuth,
    response=UserOut,
    tags=["Authentication"],
    summary="Update Profile"
)
def update_profile(request, data: UserUpdate):
    user = request.user

    if User.objects.filter(email=data.email).exclude(id=user.id).exists():
        raise HttpError(400, "Email sudah digunakan")

    user.first_name = data.first_name
    user.last_name = data.last_name
    user.email = data.email
    user.save()

    return user


@apiv1.get(
    "/auth/me/",
    auth=apiAuth,
    response=UserOut,
    tags=["Authentication"],
    summary="Auth Me"
)
def auth_me(request):
    return request.user


@apiv1.put(
    "/auth/me/",
    auth=apiAuth,
    response=UserOut,
    tags=["Authentication"],
    summary="Auth Update Me"
)
def auth_update_me(request, data: UserUpdate):
    user = request.user

    if User.objects.filter(email=data.email).exclude(id=user.id).exists():
        raise HttpError(400, "Email sudah digunakan")

    user.first_name = data.first_name
    user.last_name = data.last_name
    user.email = data.email
    user.save()

    return user


# ================= COURSES =================

@apiv1.get(
    "/courses/",
    response=List[CourseOut],
    tags=["Courses"],
    summary="Daftar Course"
)
def listCourses(request):
    return Course.objects.select_related("teacher").all()


@apiv1.get(
    "/courses/{id}",
    response=DetailCourseOut,
    tags=["Courses"],
    summary="Detail Course"
)
def detailCourse(request, id: int):
    course = (
        Course.objects.filter(id=id)
        .prefetch_related("coursecontent_set")
        .select_related("teacher")
        .first()
    )

    if not course:
        raise HttpError(404, "Course tidak ditemukan")

    return course


@apiv1.post(
    "/courses/",
    auth=apiAuth,
    response={201: CourseOut},
    tags=["Courses"],
    summary="Create Course"
)
def createCourse(request, data: CourseIn):
    if data.price < 0:
        raise HttpError(400, "Harga tidak boleh negatif")

    course = Course.objects.create(
        **data.dict(),
        teacher=request.user
    )

    return 201, course


@apiv1.put(
    "/courses/{id}",
    auth=apiAuth,
    response=CourseOut,
    tags=["Courses"],
    summary="Update Course"
)
def updateCourse(request, id: int, data: CourseIn):
    if data.price < 0:
        raise HttpError(400, "Harga tidak boleh negatif")

    course = Course.objects.filter(id=id).first()

    if not course:
        raise HttpError(404, "Course tidak ditemukan")

    if course.teacher != request.user:
        raise HttpError(403, "Bukan pemilik course")

    for key, value in data.dict().items():
        setattr(course, key, value)

    course.save()
    return course


@apiv1.delete(
    "/courses/{id}",
    auth=apiAuth,
    tags=["Courses"],
    summary="Delete Course"
)
def deleteCourse(request, id: int):
    course = Course.objects.filter(id=id).first()

    if not course:
        raise HttpError(404, "Course tidak ditemukan")

    if course.teacher != request.user and not request.user.is_superuser:
        raise HttpError(403, "Tidak punya akses")

    course.delete()
    return {"message": "Course berhasil dihapus"}


# ================= ENROLLMENTS =================

@apiv1.get(
    "/enrollments/my-courses/",
    auth=apiAuth,
    response=List[CourseMemberOut],
    tags=["Enrollments"],
    summary="My Courses"
)
def my_courses(request):
    return CourseMember.objects.filter(
        user_id=request.user
    ).select_related("course_id", "user_id")


@apiv1.post(
    "/course/{id}/enroll/",
    auth=apiAuth,
    response=CourseMemberOut,
    tags=["Enrollments"],
    summary="Enroll Course"
)
def enroll(request, id: int):
    course = Course.objects.filter(id=id).first()

    if not course:
        raise HttpError(404, "Course tidak ditemukan")

    if CourseMember.objects.filter(user_id=request.user, course_id=course).exists():
        raise HttpError(400, "Sudah enroll")

    return CourseMember.objects.create(
        user_id=request.user,
        course_id=course,
        roles="std"
    )


@apiv1.post(
    "/enrollments/{id}/progress/",
    auth=apiAuth,
    response=MessageOut,
    tags=["Enrollments"],
    summary="Mark Progress"
)
def mark_progress(request, id: int, data: ProgressIn):
    enrollment = CourseMember.objects.filter(
        id=id,
        user_id=request.user
    ).first()

    if not enrollment:
        raise HttpError(404, "Enrollment tidak ditemukan")

    content = CourseContent.objects.filter(
        id=data.content_id,
        course_id=enrollment.course_id
    ).first()

    if not content:
        raise HttpError(404, "Konten tidak ditemukan di course ini")

    return {"message": "Progress berhasil ditandai selesai"}


# ================= COMMENTS =================

@apiv1.post(
    "/comments/",
    auth=apiAuth,
    tags=["Comments"],
    summary="Post Comment"
)
def postComment(request, data: CommentIn):
    content = CourseContent.objects.filter(id=data.content_id).first()

    if not content:
        raise HttpError(404, "Content tidak ditemukan")

    Comment.objects.create(
        comment=data.comment,
        user_id=request.user,
        content_id=content
    )

    return {"message": "Komentar berhasil"}


@apiv1.put(
    "/comments/{id}",
    auth=apiAuth,
    tags=["Comments"],
    summary="Update Comment"
)
def updateComment(request, id: int, data: CommentUpdate):
    comment = Comment.objects.filter(id=id).first()

    if not comment:
        raise HttpError(404, "Komentar tidak ditemukan")

    if comment.user_id != request.user:
        raise HttpError(403, "Bukan pemilik komentar")

    comment.comment = data.comment
    comment.save()

    return {"message": "Komentar diupdate"}


@apiv1.delete(
    "/comments/{id}",
    auth=apiAuth,
    tags=["Comments"],
    summary="Delete Comment"
)
def deleteComment(request, id: int):
    comment = (
        Comment.objects.select_related("content_id__course_id")
        .filter(id=id)
        .first()
    )

    if not comment:
        raise HttpError(404, "Komentar tidak ditemukan")

    if (
        comment.user_id == request.user
        or comment.content_id.course_id.teacher == request.user
        or request.user.is_superuser
    ):
        comment.delete()
        return {"message": "Komentar dihapus"}

    raise HttpError(403, "Tidak punya akses")