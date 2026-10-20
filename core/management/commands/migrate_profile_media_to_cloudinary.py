"""Move legacy database-stored profile pictures to Cloudinary without data loss.

Run with: python manage.py migrate_profile_media_to_cloudinary
Use --dry-run to inspect eligible records without uploading or changing rows.
"""
from io import BytesIO

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import UserProfile


class Command(BaseCommand):
    help = "Migrate legacy profile picture blobs to Cloudinary"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report eligible records without changing them")
        parser.add_argument("--limit", type=int, default=0, help="Maximum profiles to process (0 means all)")

    def handle(self, *args, **options):
        cloudinary_url = str(getattr(settings, "CLOUDINARY_URL", "") or "").strip()
        if not options["dry_run"] and not cloudinary_url:
            raise CommandError("CLOUDINARY_URL must be configured before migrating profile media.")
        queryset = UserProfile.objects.exclude(profile_picture_data=b"").order_by("pk")
        if options["limit"] > 0:
            queryset = queryset[:options["limit"]]

        if not options["dry_run"]:
            try:
                from cloudinary import config as cloudinary_config
                from cloudinary.uploader import upload as cloudinary_upload
                cloudinary_config(cloudinary_url=cloudinary_url, secure=True)
            except ImportError as exc:
                raise CommandError("Install the cloudinary dependency before migrating media.") from exc

        scanned = uploaded = skipped = failed = 0
        for profile in queryset.iterator() if not options["limit"] else queryset:
            scanned += 1
            blob = bytes(profile.profile_picture_data or b"")
            if not blob:
                skipped += 1
                continue
            if options["dry_run"]:
                self.stdout.write(f"Would migrate profile_id={profile.pk} user_id={profile.user_id} bytes={len(blob)}")
                continue
            try:
                from PIL import Image, UnidentifiedImageError
                image = Image.open(BytesIO(blob))
                image.verify()
                image = Image.open(BytesIO(blob))
                image.load()
                image.thumbnail((512, 512), Image.Resampling.LANCZOS)
                normalized = image.convert("RGBA" if image.mode in {"RGBA", "LA"} or "transparency" in image.info else "RGB")
                buffer = BytesIO()
                normalized.save(buffer, format="WEBP", quality=85, method=6)
                result = cloudinary_upload(
                    buffer.getvalue(), resource_type="image",
                    folder="algobot/profile-pictures",
                    public_id=f"user-{profile.user_id}", overwrite=True,
                    invalidate=True, format="webp",
                )
                url = str(result.get("secure_url") or "")
                if not url.startswith("https://res.cloudinary.com/"):
                    raise ValueError("Cloudinary returned an untrusted URL")
                # Clear the old blob only after the remote upload has succeeded.
                profile.avatar_url = url
                profile.profile_picture_data = b""
                profile.profile_picture_content_type = ""
                profile.save(update_fields=["avatar_url", "profile_picture_data", "profile_picture_content_type", "updated_at"])
                uploaded += 1
                self.stdout.write(f"Migrated profile_id={profile.pk}")
            except Exception as exc:
                failed += 1
                self.stderr.write(f"Failed profile_id={profile.pk}: {type(exc).__name__}")
        self.stdout.write(self.style.SUCCESS(
            f"Finished: scanned={scanned}, uploaded={uploaded}, skipped={skipped}, failed={failed}, dry_run={options['dry_run']}"
        ))
        if failed:
            raise CommandError(f"{failed} profile picture(s) failed; their original database blobs were retained.")
