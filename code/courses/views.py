"""
Views untuk Simple LMS - Lab 05: Optimasi Database

Berisi 3 pasang endpoint baseline vs optimized:
  1. course_list_baseline / course_list_optimized
  2. course_members_baseline / course_members_optimized
  3. course_dashboard_baseline / course_dashboard_optimized
"""

from django.db.models import Avg, Count, Max, Min, Prefetch
from django.http import JsonResponse

from .models import Comment, Course, CourseContent, CourseMember


# =============================================================================
# ENDPOINT 1: Daftar Course + Teacher
# =============================================================================

def course_list_baseline(request):
    """
    BASELINE - N+1 Problem pada ForeignKey teacher.
    Query 1: SELECT * FROM courses_course
    Query N: SELECT * FROM auth_user WHERE id=<teacher_id>  (per course)
    Total: 1 + N query
    """
    courses = Course.objects.all()
    data = []
    for c in courses:
        data.append({
            'id': c.id,
            'course': c.name,
            'price': c.price,
            'teacher': c.teacher.username,   # <-- N+1 trigger
            'teacher_email': c.teacher.email,
        })
    return JsonResponse({'data': data, 'count': len(data)})


def course_list_optimized(request):
    """
    OPTIMIZED - select_related('teacher') untuk ForeignKey.
    Django melakukan INNER JOIN sehingga data teacher ikut dalam 1 query.
    Total: selalu 1 query berapapun jumlah course.
    """
    courses = Course.objects.select_related('teacher').all()
    data = []
    for c in courses:
        data.append({
            'id': c.id,
            'course': c.name,
            'price': c.price,
            'teacher': c.teacher.username,   # tidak ada query tambahan
            'teacher_email': c.teacher.email,
        })
    return JsonResponse({'data': data, 'count': len(data)})


# =============================================================================
# ENDPOINT 2: Daftar Course + Members + Konten + Jumlah Komentar
# =============================================================================

def course_members_baseline(request):
    """
    BASELINE - Multiple N+1 Problems.
    Untuk setiap course: query members, query contents, query count comment.
    Total: 1 + N + N + (M*N) query — sangat boros.
    """
    courses = Course.objects.all()
    data = []
    for c in courses:
        members = CourseMember.objects.filter(course_id=c)
        contents = CourseContent.objects.filter(course_id=c)
        content_list = []
        for content in contents:
            comment_count = Comment.objects.filter(content_id=content).count()
            content_list.append({
                'content_name': content.name,
                'comment_count': comment_count,
            })
        data.append({
            'id': c.id,
            'course': c.name,
            'teacher': c.teacher.username,   # N+1
            'member_count': members.count(),
            'contents': content_list,
        })
    return JsonResponse({'data': data, 'count': len(data)})


def course_members_optimized(request):
    """
    OPTIMIZED - select_related + prefetch_related kombinasi.
    Hanya 4 query total berapapun jumlah data:
      Q1: course + JOIN teacher
      Q2: coursemember WHERE course_id IN (...)
      Q3: coursecontent WHERE course_id IN (...)
      Q4: comment WHERE content_id IN (...)
    """
    comment_prefetch = Prefetch(
        'coursecontent_set__comment_set',
        queryset=Comment.objects.all()
    )
    courses = Course.objects.select_related('teacher').prefetch_related(
        'coursemember_set',
        'coursecontent_set',
        comment_prefetch,
    ).all()

    data = []
    for c in courses:
        content_list = []
        for content in c.coursecontent_set.all():
            content_list.append({
                'content_name': content.name,
                'comment_count': content.comment_set.count(),  # dari prefetch cache
            })
        data.append({
            'id': c.id,
            'course': c.name,
            'teacher': c.teacher.username,
            'member_count': c.coursemember_set.count(),
            'contents': content_list,
        })
    return JsonResponse({'data': data, 'count': len(data)})


# =============================================================================
# ENDPOINT 3: Statistik Dashboard Dosen
# =============================================================================

def course_dashboard_baseline(request):
    """
    BASELINE - Statistik dihitung dalam Python loop.
    Masalah: 1 + 3N query (member, content, comment per course).
    Agregasi dilakukan di Python, bukan di database.
    """
    courses = Course.objects.all()
    total_courses = 0
    total_price = 0
    max_price = 0
    min_price = float('inf')
    course_stats = []

    for c in courses:
        total_courses += 1
        total_price += c.price
        if c.price > max_price:
            max_price = c.price
        if c.price < min_price:
            min_price = c.price

        # Setiap baris = 1 query database
        member_count = CourseMember.objects.filter(course_id=c).count()
        content_count = CourseContent.objects.filter(course_id=c).count()
        comment_count = Comment.objects.filter(content_id__course_id=c).count()

        course_stats.append({
            'id': c.id,
            'course': c.name,
            'price': c.price,
            'teacher': c.teacher.username,   # N+1
            'member_count': member_count,
            'content_count': content_count,
            'comment_count': comment_count,
        })

    avg_price = total_price / total_courses if total_courses else 0

    return JsonResponse({
        'global_stats': {
            'total_courses': total_courses,
            'max_price': max_price,
            'min_price': min_price if min_price != float('inf') else 0,
            'avg_price': round(avg_price, 2),
        },
        'courses': course_stats,
    })


def course_dashboard_optimized(request):
    """
    OPTIMIZED - aggregate() + annotate() — semua kalkulasi di database.
    Hanya 2 query total berapapun jumlah data:
      Q1: Global stats dengan aggregate()
      Q2: Per-course stats dengan annotate() + select_related
    """
    # Query 1: Statistik global dalam 1 query
    global_stats = Course.objects.aggregate(
        total_courses=Count('id'),
        max_price=Max('price'),
        min_price=Min('price'),
        avg_price=Avg('price'),
    )

    # Query 2: Statistik per course dalam 1 query
    courses = Course.objects.select_related('teacher').annotate(
        member_count=Count('coursemember', distinct=True),
        content_count=Count('coursecontent', distinct=True),
        comment_count=Count('coursecontent__comment', distinct=True),
    ).order_by('-member_count')

    course_stats = []
    for c in courses:
        course_stats.append({
            'id': c.id,
            'course': c.name,
            'price': c.price,
            'teacher': c.teacher.username,
            'member_count': c.member_count,
            'content_count': c.content_count,
            'comment_count': c.comment_count,
        })

    return JsonResponse({
        'global_stats': {
            'total_courses': global_stats['total_courses'],
            'max_price': global_stats['max_price'],
            'min_price': global_stats['min_price'],
            'avg_price': round(global_stats['avg_price'] or 0, 2),
        },
        'courses': course_stats,
    })


# =============================================================================
# BONUS: Bulk Operations Demo
# =============================================================================

def bulk_create_demo(request):
    """
    Demo bulk_create: insert 50 konten dalam 2 query (batch_size=25).
    Tanpa bulk_create butuh 50 query INSERT terpisah.
    """
    try:
        course = Course.objects.first()
        if not course:
            return JsonResponse(
                {'error': 'Tidak ada course. Jalankan seed_data dulu.'}, status=400
            )
        contents = [
            CourseContent(
                name=f'Bulk Content {i}',
                description=f'Konten hasil bulk_create nomor {i}',
                course_id=course,
            )
            for i in range(1, 51)
        ]
        created = CourseContent.objects.bulk_create(contents, batch_size=25)
        return JsonResponse({
            'message': f'Berhasil bulk_create {len(created)} konten',
            'course': course.name,
            'note': 'Cek SQL tab di Silk — hanya 2 query INSERT (batch_size=25)',
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def bulk_update_demo(request):
    """
    Demo bulk update() — satu query UPDATE untuk semua baris.
    Tanpa update() butuh N query save() terpisah.
    """
    from django.db.models import F
    updated_count = Course.objects.all().update(price=F('price') * 1)
    return JsonResponse({
        'message': f'bulk update selesai: {updated_count} course diproses',
        'note': 'Cek SQL tab di Silk — hanya 1 query UPDATE meskipun banyak baris',
    })
