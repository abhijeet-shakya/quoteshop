"""CONTRACTS §7.1 image pipeline (quoteshop_catalog/images.py).

TEST_MATRIX CAT-12 (3 WebP sizes), CAT-13 (enqueued once per photo), CAT-14 (unchanged photos not reprocessed).
Source images are generated in memory with Pillow (factories.make_photo); jobs never run through a worker:
frappe.enqueue is patched and generate_photo_sizes is called directly (CONTRACTS §5.1).
"""

import io
import os
from unittest.mock import patch

import frappe
from PIL import Image

from quoteshop.quoteshop_catalog.tests.base import CatalogTestCase
from quoteshop.quoteshop_enquiry.tests.factories import make_photo, make_published_item

JOB = "quoteshop.quoteshop_catalog.images.generate_photo_sizes"
ITEM = "_QS-IMG"
SIZES = {"thumb": 400, "medium": 1000, "large": 1800}


def generate(item_code=ITEM):
	from quoteshop.quoteshop_catalog.images import generate_photo_sizes

	return generate_photo_sizes(item_code)


def queue(doc):
	from quoteshop.quoteshop_catalog.images import queue_photo_sizes

	return queue_photo_sizes(doc)


def image_jobs(enqueue_mock):
	"""kwargs of every frappe.enqueue call that targets the image job."""
	jobs = []
	for call in enqueue_mock.call_args_list:
		method = call.args[0] if call.args else call.kwargs.get("method")
		if method == JOB:
			jobs.append(call.kwargs)
	return jobs


def rows(item_code=ITEM):
	return frappe.get_all(
		"QS Item Photo",
		filters={"parent": item_code, "parentfield": "qs_photos"},
		fields=["name", "image", "thumb", "medium", "large", "alt_text"],
		order_by="idx asc",
	)


def webp_files(item_code=ITEM):
	return frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Item",
			"attached_to_name": item_code,
			"file_name": ("like", "%.webp"),
		},
		fields=["name", "file_name", "file_url", "is_private", "modified"],
		order_by="file_name asc",
	)


def open_image(file_url):
	content = frappe.get_doc("File", {"file_url": file_url}).get_content()
	return Image.open(io.BytesIO(content))


def stem_of(file_url):
	return os.path.splitext(os.path.basename(file_url))[0]


class ImageTestCase(CatalogTestCase):
	def setUp(self):
		super().setUp()
		make_published_item(ITEM)
		self.addCleanup(
			self._remove_files
		)  # runs before the savepoint rollback registered by super().setUp()

	def _remove_files(self):
		for name in frappe.get_all("File", filters={"attached_to_name": ("like", "_QS-IMG%")}, pluck="name"):
			frappe.delete_doc("File", name, force=1, ignore_permissions=True)

	def photo(self, width=2400, height=1200, **kwargs):
		return make_photo(ITEM, width, height, **kwargs)


class TestGeneratePhotoSizes(ImageTestCase):
	def test_generates_three_webp_sizes(self):
		"""CAT-12"""
		photo = self.photo(2400, 1200)
		generate()
		(row,) = rows()
		stem = stem_of(photo.file_url)
		for column, width in SIZES.items():
			expected_url = f"/files/{stem}-{photo.sha1}-{width}.webp"
			self.assertEqual(row[column], expected_url)
			image = open_image(expected_url)
			self.assertEqual(image.format, "WEBP")
			self.assertEqual(image.size, (width, width // 2))  # aspect ratio kept (2:1)
		files = webp_files()
		self.assertEqual(len(files), 3)
		self.assertTrue(all(f.is_private == 0 for f in files))
		self.assertEqual({f.file_url for f in files}, {row[c] for c in SIZES})

	def test_never_upscales(self):
		self.photo(700, 350)
		generate()
		(row,) = rows()
		widths = {column: open_image(row[column]).width for column in SIZES}
		self.assertEqual(widths, {"thumb": 400, "medium": 700, "large": 700})

	def test_source_smaller_than_thumb(self):
		self.photo(300, 150)
		generate()
		(row,) = rows()
		self.assertEqual({open_image(row[c]).width for c in SIZES}, {300})

	def test_every_row_gets_sizes(self):
		first = self.photo(2400, 1200, color=(10, 10, 200), stem="_qs_img_a")
		second = self.photo(1200, 600, color=(10, 200, 10), stem="_qs_img_b")
		generate()
		row_a, row_b = rows()
		self.assertIn(first.sha1, row_a["thumb"])
		self.assertIn(second.sha1, row_b["thumb"])
		self.assertEqual(open_image(row_b["large"]).width, 1200)

	def test_item_without_photos_is_a_noop(self):
		generate()
		self.assertEqual(webp_files(), [])

	def test_job_does_not_save_the_item_or_reenqueue(self):
		"""Sizes are written with db.set_value on the child row: no Item save, so no on_update loop."""
		self.photo()
		modified = frappe.db.get_value("Item", ITEM, "modified")
		with patch("frappe.enqueue") as enqueue:
			generate()
		self.assertEqual(frappe.db.get_value("Item", ITEM, "modified"), modified)
		enqueue.assert_not_called()


class TestIdempotent(ImageTestCase):
	def test_unchanged_photo_not_reprocessed(self):
		"""CAT-14: second run creates no File rows, rewrites nothing."""
		self.photo()
		generate()
		files_before, rows_before = webp_files(), rows()
		with patch("PIL.Image.Image.save") as save:
			generate()
		save.assert_not_called()
		self.assertEqual(webp_files(), files_before)  # same names, same modified timestamps
		self.assertEqual(rows(), rows_before)
		self.assertEqual(frappe.db.count("File", {"attached_to_name": ITEM}), 4)  # source + 3 sizes

	def test_file_content_unchanged(self):
		self.photo()
		generate()
		(row,) = rows()
		before = {c: frappe.get_doc("File", {"file_url": row[c]}).content_hash for c in SIZES}
		generate()
		after = {c: frappe.get_doc("File", {"file_url": row[c]}).content_hash for c in SIZES}
		self.assertEqual(before, after)
		self.assertTrue(all(before.values()))

	def test_changed_source_is_regenerated(self):
		old = self.photo(color=(200, 30, 30), stem="_qs_img_old")
		generate()
		(row,) = rows()
		new = make_photo(ITEM, 2400, 1200, color=(30, 30, 200), stem="_qs_img_new")
		frappe.db.set_value("QS Item Photo", row["name"], "image", new.file_url)
		self.assertNotEqual(old.sha1, new.sha1)

		generate()

		(updated,) = rows()
		for column, width in SIZES.items():
			self.assertIn(new.sha1, updated[column])
			self.assertNotIn(old.sha1, updated[column])
			self.assertEqual(open_image(updated[column]).width, width)

	def test_only_changed_row_is_regenerated(self):
		self.photo(color=(10, 10, 200), stem="_qs_img_a")
		second = self.photo(color=(10, 200, 10), stem="_qs_img_b")
		generate()
		row_a_before, row_b = rows()
		files_a_before = [f for f in webp_files() if f.file_url in {row_a_before[c] for c in SIZES}]
		new = make_photo(ITEM, 2400, 1200, color=(200, 200, 10), stem="_qs_img_c")
		frappe.db.set_value("QS Item Photo", row_b["name"], "image", new.file_url)

		generate()

		row_a, row_b_after = rows()
		self.assertEqual(row_a, row_a_before)
		self.assertEqual([f for f in webp_files() if f.file_url in {row_a[c] for c in SIZES}], files_a_before)
		self.assertIn(new.sha1, row_b_after["thumb"])
		self.assertNotIn(second.sha1, row_b_after["thumb"])


class TestQueuePhotoSizes(ImageTestCase):
	def test_enqueued_once_per_photo(self):
		"""CAT-13: method, kwargs, job_id dedupe, after commit"""
		self.photo()
		with patch("frappe.enqueue") as enqueue:
			queue(frappe.get_doc("Item", ITEM))
			queue(frappe.get_doc("Item", ITEM))
		first, second = image_jobs(enqueue)
		for job in (first, second):
			self.assertEqual(job["item_code"], ITEM)
			self.assertEqual(job["job_id"], f"qs-img-{ITEM}")
			self.assertIs(job["deduplicate"], True)
			self.assertIs(job["enqueue_after_commit"], True)

	def test_nothing_queued_without_photos(self):
		with patch("frappe.enqueue") as enqueue:
			queue(frappe.get_doc("Item", ITEM))
		self.assertEqual(image_jobs(enqueue), [])

	def test_nothing_queued_when_sizes_are_current(self):
		"""CAT-14: re-saving an Item with unchanged photos does not enqueue."""
		self.photo()
		generate()
		with patch("frappe.enqueue") as enqueue:
			queue(frappe.get_doc("Item", ITEM))
		self.assertEqual(image_jobs(enqueue), [])

	def test_queued_when_a_size_is_missing(self):
		self.photo()
		generate()
		(row,) = rows()
		frappe.db.set_value("QS Item Photo", row["name"], "medium", "")
		with patch("frappe.enqueue") as enqueue:
			queue(frappe.get_doc("Item", ITEM))
		self.assertEqual(len(image_jobs(enqueue)), 1)

	def test_queued_when_source_changed(self):
		self.photo(stem="_qs_img_old")
		generate()
		(row,) = rows()
		new = make_photo(ITEM, 2400, 1200, color=(1, 2, 3), stem="_qs_img_new")
		frappe.db.set_value("QS Item Photo", row["name"], "image", new.file_url)
		with patch("frappe.enqueue") as enqueue:
			queue(frappe.get_doc("Item", ITEM))
		self.assertEqual(len(image_jobs(enqueue)), 1)

	def test_item_on_update_enqueues(self):
		"""Hook: Item.on_update -> queue_photo_sizes."""
		self.photo()
		item = frappe.get_doc("Item", ITEM)
		item.item_name = "Image Item Edited"
		with patch("frappe.enqueue") as enqueue:
			item.save(ignore_permissions=True)
		(job,) = image_jobs(enqueue)
		self.assertEqual((job["item_code"], job["job_id"]), (ITEM, f"qs-img-{ITEM}"))

	def test_item_save_without_photos_does_not_enqueue(self):
		item = frappe.get_doc("Item", ITEM)
		item.item_name = "Image Item Edited"
		with patch("frappe.enqueue") as enqueue:
			item.save(ignore_permissions=True)
		self.assertEqual(image_jobs(enqueue), [])

	def test_item_resave_after_generation_does_not_enqueue(self):
		self.photo()
		generate()
		item = frappe.get_doc("Item", ITEM)
		item.item_name = "Image Item Edited Again"
		with patch("frappe.enqueue") as enqueue:
			item.save(ignore_permissions=True)
		self.assertEqual(image_jobs(enqueue), [])
