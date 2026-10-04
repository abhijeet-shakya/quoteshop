import hashlib
import io
import os
from urllib.parse import unquote, urlsplit

import frappe
from frappe.model.document import Document

from quoteshop.quoteshop_catalog.cache import clear_catalog_cache
from quoteshop.quoteshop_catalog.catalog import file_path

SIZES = {"thumb": 400, "medium": 1000, "large": 1800}
JOB = "quoteshop.quoteshop_catalog.images.generate_photo_sizes"


def queue_photo_sizes(doc: Document, method: str | None = None) -> None:
	"""doc_event Item.on_update: enqueue size generation when a photo lacks sizes or its source changed."""
	if any(_needs_sizes(row) for row in doc.get("qs_photos")):
		frappe.enqueue(
			JOB,
			item_code=doc.name,
			enqueue_after_commit=True,
			job_id=f"qs-img-{doc.name}",
			deduplicate=True,
		)


def _needs_sizes(row) -> bool:
	# Generated names start with the source stem; a new source file has a new stem.
	prefix = f"/files/{_stem(row.image)}-"
	return bool(file_path(row.image)) and not all((row.get(size) or "").startswith(prefix) for size in SIZES)


def generate_photo_sizes(item_code: str) -> None:
	"""Write WebP thumb/medium/large for every QS Item Photo of the item; rows already holding sizes of the
	current source (sha1 in the file name) are skipped."""
	rows = frappe.get_all(
		"QS Item Photo",
		filters={"parent": item_code, "parenttype": "Item", "parentfield": "qs_photos"},
		fields=["name", "image", *SIZES],
	)
	changed = False
	for row in rows:
		path = file_path(row.image)
		if not path:
			continue
		with open(path, "rb") as f:
			content = f.read()
		digest = hashlib.sha1(content).hexdigest()[:10]
		missing = {size: width for size, width in SIZES.items() if f"-{digest}-" not in (row[size] or "")}
		if not missing:
			continue
		urls = _make_sizes(content, f"{_stem(row.image)}-{digest}", missing, item_code)
		frappe.db.set_value("QS Item Photo", row.name, urls)
		changed = True
	if changed:
		clear_catalog_cache()


def _make_sizes(content: bytes, name: str, sizes: dict[str, int], item_code: str) -> dict[str, str]:
	from PIL import Image, ImageOps

	with Image.open(io.BytesIO(content)) as source:
		image = ImageOps.exif_transpose(source)
		image = image.convert("RGBA" if image.has_transparency_data else "RGB")
	urls = {}
	for size, target in sizes.items():
		width = min(target, image.width)
		resized = image.resize((width, max(round(image.height * width / image.width), 1)), Image.LANCZOS)
		buffer = io.BytesIO()
		resized.save(buffer, format="WEBP", quality=82, method=6)
		urls[size] = (
			frappe.get_doc(
				{
					"doctype": "File",
					"file_name": f"{name}-{target}.webp",
					"content": buffer.getvalue(),
					"is_private": 0,
					"attached_to_doctype": "Item",
					"attached_to_name": item_code,
				}
			)
			.insert(ignore_permissions=True)
			.file_url
		)
	return urls


def _stem(url: str | None) -> str:
	return os.path.splitext(os.path.basename(unquote(urlsplit(url or "").path)))[0]
