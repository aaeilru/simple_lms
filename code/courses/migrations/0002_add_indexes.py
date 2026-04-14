"""
Migration: Tambah database indexes untuk optimasi performa query.

Index yang ditambahkan:
  Course:
    - idx_course_price            → filter/order berdasarkan harga
    - idx_course_teacher_price    → query "course milik teacher, urut harga"
    - idx_course_created_at       → order by terbaru

  CourseMember:
    - idx_coursemember_course     → filter member berdasarkan course
    - idx_coursemember_user       → filter course berdasarkan user
    - idx_coursemember_course_role → filter role dalam course

  CourseContent:
    - idx_coursecontent_course    → filter konten berdasarkan course

  Comment:
    - idx_comment_content         → filter komentar berdasarkan konten
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0001_initial'),
    ]

    operations = [
        # Index untuk model Course
        migrations.AddIndex(
            model_name='course',
            index=models.Index(fields=['price'], name='idx_course_price'),
        ),
        migrations.AddIndex(
            model_name='course',
            index=models.Index(fields=['teacher', 'price'], name='idx_course_teacher_price'),
        ),
        migrations.AddIndex(
            model_name='course',
            index=models.Index(fields=['created_at'], name='idx_course_created_at'),
        ),
        # Index untuk model CourseMember
        migrations.AddIndex(
            model_name='coursemember',
            index=models.Index(fields=['course_id'], name='idx_coursemember_course'),
        ),
        migrations.AddIndex(
            model_name='coursemember',
            index=models.Index(fields=['user_id'], name='idx_coursemember_user'),
        ),
        migrations.AddIndex(
            model_name='coursemember',
            index=models.Index(fields=['course_id', 'roles'], name='idx_coursemember_course_role'),
        ),
        # Index untuk model CourseContent
        migrations.AddIndex(
            model_name='coursecontent',
            index=models.Index(fields=['course_id'], name='idx_coursecontent_course'),
        ),
        # Index untuk model Comment
        migrations.AddIndex(
            model_name='comment',
            index=models.Index(fields=['content_id'], name='idx_comment_content'),
        ),
    ]
