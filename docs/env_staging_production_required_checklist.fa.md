# چک‌لیست اجباری `.env` برای Staging/Production

این چک‌لیست را قبل از اجرای `docker compose up -d --build` در محیط staging یا production بررسی کنید.

## کلیدهای اجباری

- [ ] `APP_ENV=staging` یا `APP_ENV=production`
- [ ] `DEBUG=false`
- [ ] `API_PREFIX=/api/v1`
- [ ] `MDR_DOMAIN=<دامنه عمومی>`
- [ ] `MDR_DATA_ROOT=<مسیر داده سرور>` (مثال: `/opt/mdr_data`)
- [ ] `STORAGE_ALLOWED_ROOTS=<CSV مسیرهای absolute>` (مثال: `/app/archive_storage,/app/data_store`)
- [ ] `STORAGE_REQUIRE_ABSOLUTE_PATHS=true`
- [ ] `STORAGE_VALIDATE_WRITABLE_ON_SAVE=true`
- [ ] `POSTGRES_PORT_BIND=127.0.0.1:5432:5432`
- [ ] `WEB_PORT_BIND=127.0.0.1:8000:8000`
- [ ] `POSTGRES_DB=<نام دیتابیس>`
- [ ] `POSTGRES_USER=<کاربر دیتابیس>`
- [ ] `POSTGRES_PASSWORD=<رمز قوی>`
- [ ] `DATABASE_URL=postgresql+psycopg://<user>:<password>@postgres:5432/<db-name>`
- [ ] `COMPOSE_DATABASE_URL` دقیقاً برابر با `DATABASE_URL`
- [ ] `SECRET_KEY=<رشته تصادفی طولانی>` (حداقل ۳۲ کاراکتر)
- [ ] `ADMIN_EMAIL=<ایمیل ادمین>`
- [ ] `ADMIN_PASSWORD=<رمز قوی ادمین>`
- [ ] `ADMIN_FULL_NAME=<نام کامل ادمین>`
- [ ] `APP_UID=1000`
- [ ] `APP_GID=1000`
- [ ] `WEB_CONCURRENCY=2` (یا بیشتر متناسب با منابع سرور)

## یکپارچه‌سازی‌های اختیاری (فقط در صورت استفاده)

- [ ] `GDRIVE_SERVICE_ACCOUNT_JSON`
- [ ] `GDRIVE_SHARED_DRIVE_ID`
- [ ] `OPENPROJECT_BASE_URL`
- [ ] `OPENPROJECT_API_TOKEN`
- [ ] `OPENPROJECT_TLS_VERIFY=true` (پیش‌فرض امن)
- [ ] (اختیاری) `OPENPROJECT_TLS_VERIFY_FORCE=<true|false>` برای override مرکزی
- [ ] `OPENPROJECT_DEFAULT_WORK_PACKAGE_ID`
- [ ] (اختیاری، legacy) `OPENPROJECT_DEFAULT_PROJECT_ID`
- [ ] `NEXTCLOUD_BASE_URL` (اگر mirror provider روی `nextcloud` است)
- [ ] `NEXTCLOUD_USERNAME` (اگر mirror provider روی `nextcloud` است)
- [ ] `NEXTCLOUD_APP_PASSWORD` (اگر mirror provider روی `nextcloud` است)
- [ ] `NEXTCLOUD_ROOT_PATH` (اگر mirror provider روی `nextcloud` است)
- [ ] `NEXTCLOUD_TLS_VERIFY=true` (پیش‌فرض امن)
- [ ] (اختیاری) `NEXTCLOUD_TLS_VERIFY_FORCE=<true|false>`

## گیت ذخیره‌سازی شبکه

- [ ] شبکه‌درایو روی خود سرور (CIFS/NFS) mount شده باشد.
- [ ] mount با bind وارد کانتینر شود و مسیر canonical ثابت داشته باشد (مثال: `/app/archive_storage`).
- [ ] مالکیت/مجوز mount با `APP_UID:APP_GID` هم‌راستا باشد.
- [ ] مسیرهای ذخیره‌شده در UI absolute باشند و زیر `STORAGE_ALLOWED_ROOTS` قرار بگیرند.

## اعتبارسنجی سریع

1. `docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml config`
2. `docker compose -f docker-compose.yml -f docker-compose.windows.prod.yml up -d --build`
