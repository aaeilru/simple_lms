## 1. Setup Profiling (Django Silk)

### Konfigurasi yang Dilakukan

**`code/requirements.txt`** — Dependensi sudah include:
```
django-silk==5.1.0
```

**`code/lms/settings.py`** — Sudah dikonfigurasi (dari starter):
```python
INSTALLED_APPS = [
    ...
    'silk',
    'courses',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'silk.middleware.SilkyMiddleware',  # posisi setelah Security
    ...
]

SILKY_PYTHON_PROFILER = True
SILKY_META = True
```

**`code/lms/urls.py`** — Route silk sudah ada:
```python
path('silk/', include('silk.urls', namespace='silk')),
```

### Perintah Setup
```bash
docker-compose exec app pip install django-silk
docker-compose exec app python manage.py migrate
docker-compose exec app python manage.py seed_data
```

Verifikasi: akses `http://localhost:8000/silk/` → tab Requests dan SQL muncul.

---

## 2. Daftar Endpoint yang Dibuat

| Endpoint | Path |
|----------|------|
| Course List Baseline | `GET /lab/course-list/baseline/` |
| Course List Optimized | `GET /lab/course-list/optimized/` |
| Course Members Baseline | `GET /lab/course-members/baseline/` |
| Course Members Optimized | `GET /lab/course-members/optimized/` |
| Course Dashboard Baseline | `GET /lab/course-dashboard/baseline/` |
| Course Dashboard Optimized | `GET /lab/course-dashboard/optimized/` |
| Bulk Create Demo | `GET /lab/bulk-create/` |
| Bulk Update Demo | `GET /lab/bulk-update/` |

---

## 3. Identifikasi N+1 Problem (Latihan Inti A)

### Analisis `course_list_baseline`

```python
courses = Course.objects.all()          # Query 1: SELECT * FROM courses_course
for c in courses:
    c.teacher.username                  # Query N: SELECT * FROM auth_user WHERE id=?
```

**Pola N+1:** Setiap iterasi memicu query baru ke tabel `auth_user` karena Django
tidak otomatis meng-JOIN data relasi yang tidak diminta secara eksplisit.

### Jawaban Pertanyaan Analisis

| Pertanyaan | Jawaban |
|------------|---------|
| Berapa query untuk N=100? | **101 query** (1 untuk course + 100 untuk teacher) |
| Query mana yang berulang? | `SELECT * FROM auth_user WHERE id = ?` |
| Dampak bila N=1000? | **1001 query** — waktu respons naik linear, beban DB meningkat drastis |

---

## 4. Tabel Perbandingan Silk (Estimasi)

> **Catatan:** Angka berikut adalah estimasi berdasarkan pola query yang dianalisis.
> Angka aktual akan terlihat di Silk setelah endpoint dijalankan dengan data seed.

### Kasus 1: Course + Teacher

| Metrik | Baseline | Optimized | Peningkatan |
|--------|----------|-----------|-------------|
| Jumlah Query | 101 | 1 | **-99%** |
| Duplicate Query | Ya (100x) | Tidak | ✅ |
| Total Time (est.) | ~250ms | ~15ms | **~94%** lebih cepat |
| Teknik | — | `select_related('teacher')` | |

**Penjelasan:** `select_related` melakukan SQL `INNER JOIN` sehingga data teacher
ikut dalam satu query yang sama. Django men-cache hasilnya sehingga loop berikutnya
tidak memerlukan query tambahan.

### Kasus 2: Course + Members + Konten + Komentar

| Metrik | Baseline | Optimized | Peningkatan |
|--------|----------|-----------|-------------|
| Jumlah Query | 300+ | 4 | **>98%** |
| Duplicate Query | Ya (banyak) | Tidak | ✅ |
| Total Time (est.) | ~500ms | ~30ms | **~94%** lebih cepat |
| Teknik | — | `select_related` + `prefetch_related` + `Prefetch()` | |

**Penjelasan:** `prefetch_related` mengirim query terpisah (bukan JOIN) untuk relasi
reverse FK, lalu men-cache hasilnya per objek. Loop berikutnya mengambil dari cache
Python, bukan dari database.

### Kasus 3: Statistik Dashboard

| Metrik | Baseline | Optimized | Peningkatan |
|--------|----------|-----------|-------------|
| Jumlah Query | 1+3N | 2 | **>95%** |
| Kalkulasi di Python loop | Ya | Tidak | ✅ |
| Total Time (est.) | ~400ms | ~20ms | **>95%** lebih cepat |
| Teknik | — | `aggregate()` + `annotate()` | |

**Penjelasan:** `aggregate()` menghitung statistik global (MAX, MIN, AVG, COUNT)
dalam satu SQL query. `annotate()` menambahkan kolom hitungan per baris tanpa
memerlukan loop Python tambahan.

---

## 5. Penjelasan Teknik Optimasi

### 5.1 `select_related` — untuk ForeignKey / OneToOne

```python
# BURUK: N+1
courses = Course.objects.all()
for c in courses:
    print(c.teacher.username)  # query baru tiap iterasi

# BAIK: 1 query dengan JOIN
courses = Course.objects.select_related('teacher').all()
for c in courses:
    print(c.teacher.username)  # dari cache, tidak ada query
```

**Kapan dipakai:** Relasi ForeignKey atau OneToOne (many-to-one, one-to-one).

### 5.2 `prefetch_related` — untuk Reverse FK / ManyToMany

```python
# BURUK: N+1
courses = Course.objects.all()
for c in courses:
    members = c.coursemember_set.all()  # query baru tiap iterasi

# BAIK: 2 query total
courses = Course.objects.prefetch_related('coursemember_set').all()
for c in courses:
    members = c.coursemember_set.all()  # dari prefetch cache
```

**Kapan dipakai:** Relasi reverse FK (one-to-many) atau ManyToMany.

### 5.3 `aggregate()` — Statistik Global

```python
# BURUK: hitung di Python
courses = Course.objects.all()
total = len(courses)
avg = sum(c.price for c in courses) / total

# BAIK: kalkulasi di database
stats = Course.objects.aggregate(
    total=Count('id'),
    avg_price=Avg('price'),
    max_price=Max('price'),
    min_price=Min('price'),
)
```

### 5.4 `annotate()` — Statistik Per Baris

```python
# BURUK: query count per course dalam loop
for c in courses:
    count = CourseMember.objects.filter(course_id=c).count()  # N query

# BAIK: hitung semua sekaligus di database
courses = Course.objects.annotate(
    member_count=Count('coursemember', distinct=True)
)
# c.member_count tersedia tanpa query tambahan
```

### 5.5 Bulk Operations

```python
# BURUK: save() dalam loop = N query INSERT
for i in range(1000):
    CourseContent(name=f'Content {i}', course_id=course).save()

# BAIK: bulk_create = ceil(N/batch_size) query INSERT
contents = [CourseContent(name=f'Content {i}', course_id=course) for i in range(1000)]
CourseContent.objects.bulk_create(contents, batch_size=500)

# BURUK: update satu per satu = N query UPDATE
for c in courses:
    c.price = c.price * 1.1
    c.save()

# BAIK: satu query UPDATE
Course.objects.all().update(price=F('price') * 1.1)
```

---

## 6. Database Indexing (Latihan Inti E)

### Index yang Ditambahkan

**File:** `code/courses/models.py`  
**Migration:** `code/courses/migrations/0002_add_indexes.py`

| Model | Index Name | Fields | Alasan |
|-------|-----------|--------|--------|
| Course | `idx_course_price` | `price` | Filter/sort berdasarkan harga di dashboard |
| Course | `idx_course_teacher_price` | `teacher, price` | Query "course milik teacher X, urut harga" |
| Course | `idx_course_created_at` | `created_at` | Order by terbaru (paling sering dipakai) |
| CourseMember | `idx_coursemember_course` | `course_id` | Filter semua member dari course tertentu |
| CourseMember | `idx_coursemember_user` | `user_id` | Filter semua course yang diikuti satu user |
| CourseMember | `idx_coursemember_course_role` | `course_id, roles` | Filter role (siswa/asisten) dalam course |
| CourseContent | `idx_coursecontent_course` | `course_id` | Filter semua konten dari course tertentu |
| Comment | `idx_comment_content` | `content_id` | Filter semua komentar pada satu konten |

### Perintah Migrasi

```bash
docker-compose exec app python manage.py makemigrations
docker-compose exec app python manage.py migrate
```

### Justifikasi Pemilihan Index

Index dipilih berdasarkan pola query yang terjadi pada endpoint lab:
- Kolom `course_id` di tabel `CourseMember`, `CourseContent`, dan `Comment`
  selalu dipakai dalam klausa `WHERE` saat filter per course → **wajib diindex**.
- Kolom `price` di `Course` dipakai untuk `ORDER BY` dan `FILTER` di dashboard → diindex.
- Kolom `teacher` di `Course` dipakai dalam `select_related` join + dashboard filter → diindex
  bersama `price` sebagai composite index.

---

## 7. File yang Dimodifikasi

| File | Perubahan |
|------|-----------|
| `code/courses/views.py` | Tambah 6 endpoint baseline+optimized + 2 bulk demo |
| `code/courses/urls.py` | Daftarkan semua 8 route endpoint lab |
| `code/courses/models.py` | Tambah `Meta.indexes` pada semua 4 model |
| `code/courses/migrations/0002_add_indexes.py` | File migrasi baru untuk indexes |

---

## 8. Cara Menjalankan

```bash
# 1. Jalankan container
docker-compose up -d

# 2. Install dependency (jika belum)
docker-compose exec app pip install -r requirements.txt

# 3. Jalankan migrasi
docker-compose exec app python manage.py migrate

# 4. Isi data seed (100+ course, member, konten, komentar)
docker-compose exec app python manage.py seed_data

# 5. Akses endpoint baseline (catat query count di Silk)
curl http://localhost:8000/lab/course-list/baseline/
curl http://localhost:8000/lab/course-members/baseline/
curl http://localhost:8000/lab/course-dashboard/baseline/

# 6. Buka Silk dan catat hasilnya
# http://localhost:8000/silk/

# 7. Akses endpoint optimized (bandingkan di Silk)
curl http://localhost:8000/lab/course-list/optimized/
curl http://localhost:8000/lab/course-members/optimized/
curl http://localhost:8000/lab/course-dashboard/optimized/

# 8. Bonus: test bulk operations
curl http://localhost:8000/lab/bulk-create/
curl http://localhost:8000/lab/bulk-update/
```

---

*Laporan ini disusun sebagai bagian dari Lab 05 Optimasi Database*  
*Mata Kuliah Pemrograman Sisi Server - Universitas Dian Nuswantoro - April 2026*
